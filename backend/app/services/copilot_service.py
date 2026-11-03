"""Orchestration and persistence for IMPACTMAP Copilot."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.logging import logger
from app.core.security import PathValidationError, validate_repository_path
from app.engine.copilot.answers import answer_offline, strip_unknown_citations
from app.engine.copilot.context_builder import CopilotContext, build_context
from app.engine.copilot.intent import follow_up_suggestions
from app.engine.copilot.llm import LLMClient, LLMError
from app.engine.copilot.prompts import build_messages
from app.engine.copilot.secrets import redact_secrets
from app.models.models import (
    Analysis,
    CopilotConversation,
    CopilotMessage,
    CoverageSnapshot,
    TestRun,
)
from app.services.analysis_service import AnalysisService, analysis_detail_dict
from app.services.repository_service import RepositoryService


class CopilotService:
    def __init__(self) -> None:
        self.repositories = RepositoryService()
        self.analysis = AnalysisService()
        self.llm = LLMClient()

    def status(self) -> dict:
        return self.llm.status()

    async def chat(
        self,
        db: AsyncSession,
        repo_id: str,
        message: str,
        *,
        conversation_id: str | None = None,
    ) -> tuple[CopilotConversation, CopilotMessage]:
        repo = await self.repositories.get_repository(db, repo_id)
        if not repo:
            raise LookupError("Repository not found")
        try:
            validate_repository_path(repo.path)
        except PathValidationError as exc:
            raise ValueError(str(exc)) from exc

        conversation = await self._conversation(db, repo_id, conversation_id)
        # Only reference conversations loaded the relationship eagerly. A freshly
        # flushed conversation has no ``messages`` state, and touching the lazy
        # attribute inside async SQLAlchemy would raise MissingGreenlet.
        history = [
            {"role": item.role, "content": item.content}
            for item in conversation.__dict__.get("messages", [])
            if item.role in {"user", "assistant"} and item.content
        ]

        user_message = CopilotMessage(
            conversation_id=conversation.id,
            role="user",
            content=message,
            evidence=[],
            follow_ups=[],
            warnings=[],
        )
        db.add(user_message)
        if conversation.title == "New conversation":
            conversation.title = message.strip().splitlines()[0][:80]
        conversation.updated_at = datetime.now(timezone.utc)
        await db.flush()

        latest_analysis = await self._latest_analysis(db, repo_id)
        coverage = await self.analysis.latest_coverage(db, repo_id)
        historical = await self.analysis.latest_failed_tests(db, repo_id)

        started = time.monotonic()
        warnings: list[str] = []
        error: str | None = None
        model: str | None = None
        try:
            context = await run_in_threadpool(
                build_context,
                repo_id=repo.id,
                repo_name=repo.name,
                repo_path=repo.path,
                query=message,
                history=history,
                stored_analysis=analysis_detail_dict(latest_analysis)
                if latest_analysis
                else None,
                coverage=coverage.data if coverage else None,
                historical_failures=historical,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            logger.error("Copilot context build failed for %s: %s", repo.id, exc, exc_info=True)
            raise ValueError(f"Could not build repository context: {exc}") from exc

        warnings.extend(context.warnings)
        ai_enabled = False
        content = ""
        if self.llm.enabled:
            try:
                prompt = context.to_prompt()
                llm_messages = build_messages(
                    prompt=prompt,
                    history=history,
                    max_history=settings.COPILOT_MAX_HISTORY_MESSAGES,
                )
                result = await self.llm.complete(llm_messages)
                valid_ids = [item.id for item in context.evidence]
                cleaned, citation_warnings = strip_unknown_citations(
                    redact_secrets(result.content), valid_ids
                )
                if not cleaned:
                    raise LLMError("The model returned no usable answer text")
                content = cleaned
                warnings.extend(citation_warnings)
                ai_enabled = True
                model = result.model
            except LLMError as exc:
                error = str(exc)
                warnings.append(
                    "The model provider call failed, so this answer was produced from "
                    "local static evidence instead."
                )
                logger.warning("Copilot model fallback: %s", exc)
                content = answer_offline(context)
            except Exception as exc:  # noqa: BLE001 - never leak provider details
                error = "Unexpected model-provider failure"
                warnings.append(
                    "The model provider call failed, so this answer was produced from "
                    "local static evidence instead."
                )
                logger.error("Copilot model error: %s", exc, exc_info=True)
                content = answer_offline(context)
        else:
            content = answer_offline(context)

        if not ai_enabled:
            if error:
                note = (
                    "Answered from local repository evidence because the "
                    "model-provider call failed."
                )
            else:
                note = (
                    "Answered from local repository evidence; no language-model "
                    "provider is configured for this response."
                )
            content = content.rstrip() + f"\n\n---\n_{note}_"

        cited_files = context.cited_files()
        follow_ups = follow_up_suggestions(context.intent, cited_files)
        latency_ms = (time.monotonic() - started) * 1000

        assistant = CopilotMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=content,
            intent=context.intent.name,
            model=model,
            ai_enabled=1 if ai_enabled else 0,
            evidence=[item.to_dict() for item in context.evidence],
            follow_ups=follow_ups,
            warnings=list(dict.fromkeys(warnings)),
            error=error,
            latency_ms=latency_ms,
        )
        db.add(assistant)
        conversation.updated_at = datetime.now(timezone.utc)
        await db.flush()

        logger.info(
            "Copilot answer: repo=%s conversation=%s intent=%s ai=%s evidence=%d latency=%.0fms",
            repo.name,
            conversation.id,
            context.intent.name,
            ai_enabled,
            len(context.evidence),
            latency_ms,
        )
        return conversation, assistant

    # ── conversations ───────────────────────────────────────────

    async def _conversation(
        self,
        db: AsyncSession,
        repo_id: str,
        conversation_id: str | None,
    ) -> CopilotConversation:
        if conversation_id:
            stmt = (
                select(CopilotConversation)
                .where(CopilotConversation.id == conversation_id)
                .options(selectinload(CopilotConversation.messages))
            )
            result = await db.execute(stmt)
            conversation = result.scalar_one_or_none()
            if not conversation:
                raise LookupError("Conversation not found")
            if conversation.repository_id != repo_id:
                raise ValueError("Conversation belongs to a different repository")
            return conversation

        conversation = CopilotConversation(repository_id=repo_id)
        db.add(conversation)
        await db.flush()
        return conversation

    async def list_conversations(
        self, db: AsyncSession, *, repository_id: str | None = None, limit: int = 50
    ) -> list[CopilotConversation]:
        stmt = (
            select(CopilotConversation)
            .options(selectinload(CopilotConversation.messages))
            .order_by(CopilotConversation.updated_at.desc())
            .limit(limit)
        )
        if repository_id:
            stmt = stmt.where(CopilotConversation.repository_id == repository_id)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_conversation(
        self, db: AsyncSession, conversation_id: str
    ) -> CopilotConversation:
        stmt = (
            select(CopilotConversation)
            .where(CopilotConversation.id == conversation_id)
            .options(selectinload(CopilotConversation.messages))
        )
        result = await db.execute(stmt)
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise LookupError("Conversation not found")
        return conversation

    async def delete_conversation(
        self, db: AsyncSession, conversation_id: str
    ) -> None:
        conversation = await self.get_conversation(db, conversation_id)
        await db.delete(conversation)
        await db.flush()

    async def _latest_analysis(
        self, db: AsyncSession, repo_id: str
    ) -> Analysis | None:
        stmt = (
            select(Analysis)
            .where(Analysis.repository_id == repo_id)
            .order_by(Analysis.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def latest_coverage(
        self, db: AsyncSession, repo_id: str
    ) -> CoverageSnapshot | None:
        return await self.analysis.latest_coverage(db, repo_id)

    async def latest_failed_tests(
        self, db: AsyncSession, repo_id: str
    ) -> list[str]:
        return await self.analysis.latest_failed_tests(db, repo_id)

    async def latest_test_run(
        self, db: AsyncSession, repo_id: str
    ) -> TestRun | None:
        stmt = (
            select(TestRun)
            .where(TestRun.repository_id == repo_id)
            .order_by(TestRun.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


def conversation_summary(conversation: CopilotConversation) -> dict:
    messages = list(conversation.messages or [])
    last = messages[-1] if messages else None
    return {
        "id": conversation.id,
        "repository_id": conversation.repository_id,
        "title": conversation.title,
        "message_count": len(messages),
        "last_message_preview": (last.content[:160] if last and last.content else ""),
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }
