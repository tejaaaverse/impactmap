"""IMPACTMAP Copilot API routes.

The Copilot is read-only: it retrieves repository evidence, optionally calls a
configured OpenAI-compatible model, and persists conversation history. It never
executes repository code or modifies files.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.core.security import PathValidationError
from app.engine.copilot.llm import LLMError
from app.schemas.schemas import (
    CopilotChatRequest,
    CopilotChatResponse,
    CopilotConversationDetail,
    CopilotConversationList,
    CopilotConversationSummary,
    CopilotMessageResponse,
    CopilotStatusResponse,
)
from app.services.copilot_service import CopilotService, conversation_summary

router = APIRouter(prefix="/api/copilot", tags=["Copilot"])

_service = CopilotService()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (ValueError, PathValidationError, LLMError)):
        return HTTPException(status_code=400, detail=str(exc))
    logger.error("Unhandled Copilot error: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail=f"Copilot failed: {exc}")


@router.get("/status", response_model=CopilotStatusResponse)
async def copilot_status():
    """Describe provider configuration without ever returning the API key."""
    return CopilotStatusResponse.model_validate(_service.status())


@router.post(
    "/repositories/{repo_id}/chat",
    response_model=CopilotChatResponse,
    status_code=201,
)
async def copilot_chat(
    repo_id: str,
    request: CopilotChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ask a repository-scoped question.

    Retrieval, graph traversal and static review run locally. A model is used only
    when configured through environment variables. No repository code is executed
    and no file is modified.
    """
    try:
        conversation, assistant = await _service.chat(
            db,
            repo_id,
            request.message,
            conversation_id=request.conversation_id,
        )
    except Exception as exc:
        raise _http_error(exc) from exc

    message = CopilotMessageResponse.model_validate(assistant)
    return CopilotChatResponse(
        conversation_id=conversation.id,
        message=message,
        ai_enabled=message.ai_enabled,
        intent=message.intent or "general",
        evidence=message.evidence,
        follow_ups=message.follow_ups,
        warnings=message.warnings,
        model=message.model,
        latency_ms=message.latency_ms or 0.0,
    )


@router.get("/conversations", response_model=CopilotConversationList)
async def list_conversations(
    repository_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List saved Copilot threads, newest activity first."""
    conversations = await _service.list_conversations(
        db, repository_id=repository_id, limit=limit
    )
    return CopilotConversationList(
        conversations=[
            CopilotConversationSummary.model_validate(conversation_summary(item))
            for item in conversations
        ],
        total=len(conversations),
    )


@router.get(
    "/conversations/{conversation_id}", response_model=CopilotConversationDetail
)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Load one conversation with its complete evidence trail."""
    try:
        conversation = await _service.get_conversation(db, conversation_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return CopilotConversationDetail(
        conversation=CopilotConversationSummary.model_validate(
            conversation_summary(conversation)
        ),
        messages=[
            CopilotMessageResponse.model_validate(message)
            for message in conversation.messages
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and all of its messages."""
    try:
        await _service.delete_conversation(db, conversation_id)
    except Exception as exc:
        raise _http_error(exc) from exc
    return Response(status_code=204)
