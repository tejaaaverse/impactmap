# IMPACTMAP Architecture

This document describes the backend engine, persistence model, API layering and frontend structure. For metric definitions see [benchmarks.md](benchmarks.md).

---

## 1. System layers

```
app/
  main.py                 FastAPI app, CORS, lifespan DB init
  api/                    HTTP routes (repositories, analysis, benchmarks, dashboard, copilot)
  schemas/                Pydantic request/response contracts
  services/               orchestration + persistence
  engine/                 pure analysis code
    scanner/              file discovery + repository scan
    parser/               Python AST extraction
    graph/                typed dependency graph
    git/                  diff detection + entity-span mapping
    impact/               reverse dependency traversal + scoring
    test_selection/       discovery, selection, execution, coverage
    copilot/              retrieval, intent routing, static review, prompts, LLM
  models/                 SQLAlchemy ORM
  core/                   settings, DB session, logging, path/ref security
```

The engine does not import FastAPI or SQLAlchemy. Services adapt engine results to the database and HTTP schemas. This keeps analysis logic testable in isolation.

---

## 2. Scan pipeline

1. **Path validation** — resolved path must exist, be a directory, avoid system roots, and satisfy `ALLOWED_SCAN_ROOTS` when configured.
2. **Discovery** — recursively find `.py` files; skip ignored directories (`.git`, `.venv`, `node_modules`, caches, builds), oversized files and symlink escapes.
3. **Parsing** — `PythonASTParser` extracts modules, classes, functions, methods, imports, decorators, docstrings and line spans.
4. **Persistence** — repository summary plus `CodeEntity` rows are upserted. Rescanning the same path replaces entities and graph-derived counts.
5. **Graph** — built on demand from the current scan. Paths are normalized to repository-relative POSIX paths.

### Stable graph IDs

| Type | ID format |
| --- | --- |
| File | `file:<relative/path.py>` |
| Module | `module:<dotted.package>` |
| Function | `func:<relative/path.py>::<qualified_name>` |
| Class | `class:<relative/path.py>::<qualified_name>` |
| Method | `method:<relative/path.py>::<qualified_name>` |

### Edges

Edges are directed **dependent → dependency**:

| Edge | Meaning | Base weight |
| --- | --- | --- |
| `call` | Function/method call resolved to a definition | 1.00 |
| `inherits` | Class inheritance | 0.90 |
| `import_symbol` | `from module import symbol` | 0.70 |
| `import` | Module import | 0.55 |
| `contains` | File/class contains definition | 0.35 |

When multiple edges exist between the same nodes, the strongest type is kept and confidence is the maximum observed. Unresolved imports are recorded for diagnostics rather than guessed.

---

## 3. Change detection

`GitChangeDetector` supports:

- commit ↔ commit diffs,
- commit ↔ working tree (`head_ref=WORKING`),
- added/modified/deleted/renamed files,
- unified-diff hunks,
- parsing before/after Python content to map changed line spans onto entity spans.

Repository-state fallbacks:

- no commits → compare the Git empty tree (`EMPTY` sentinel) to the working tree;
- exactly one commit → recommend `HEAD` as the base instead of `HEAD~1`;
- invalid refs, missing Git and dirty/clean trees produce explicit errors or warnings rather than silent empty diffs.

Security:

- refs are validated (`validate_git_ref`) before use,
- Git runs with an argument list, `GIT_TERMINAL_PROMPT=0`, a sanitized environment and a timeout,
- repository root must match the Git top-level.

Changes feed the impact analyzer as file-level and entity-level seeds. Deleted entities/files produce explicit direct-impact entries marked `is_deleted`.

---

## 4. Impact analysis

`ImpactAnalyzer` performs a max-score reverse traversal:

1. Seed changed nodes at score `100`.
2. Walk **incoming** edges (dependents), so affected callers/importers are discovered.
3. For each hop:

   ```
   new_score = parent_score
             × edge_weight
             × (0.65 + 0.35 × edge_confidence)
             × 0.9                 # hop decay
             × target_type_factor
   ```

   `target_type_factor`: function/method 1.0, class 0.95, file 0.88, module 0.60.
4. Clamp to `[1, 100]`; keep the best path per node with a priority queue.
5. Stop at `ANALYSIS_MAX_DEPTH` or `ANALYSIS_MAX_NODES`; mark the result truncated.
6. Exclude test nodes unless `include_tests=true`, counting exclusions.

Each impact entry stores score, depth, confidence, edge types, a human-readable reason and the dependency path. Output is split into `direct_impacts` and `indirect_impacts` and summarized by count, file, max depth and type.

**Not a prediction.** Scores estimate static coupling risk; they do not estimate the probability a test fails.

---

## 5. Test discovery, selection and coverage

### Discovery

Tests are discovered from pytest conventions (`test_*.py`, `*_test.py`, `tests/`), including classes and functions. IDs are `relative/path.py::[Class::]test_name`.

### Coverage collection

A generated pytest plugin enables Coverage.py **dynamic contexts**. Each test is mapped to the source lines it executed. Contexts are converted to repository-relative files and entity IDs, then persisted in a `CoverageSnapshot`. Selected-suite snapshots are merged into prior coverage so repeated runs accumulate evidence.

Collection is opt-in (`confirm=true`) because it executes repository code in a subprocess.

### Selection

Candidate tests come from the union of discovered tests and coverage contexts.

Per-test score combines:

- direct entity coverage,
- indirect/affected dependency coverage,
- affected-file coverage,
- static reachability through the graph,
- changed test file bonus,
- previously failing bonus.

Modes:

| Mode | With coverage | Without coverage |
| --- | --- | --- |
| `safe` | Every test covering changed/affected entities or files; plus statically linked, changed and previously failing tests | Complete discovered suite, `fallback_used=true` |
| `optimized` | Tests covering changed entities or strong affected-dependency coverage; plus changed/historically failing tests | Static evidence; if none, complete suite with explicit fallback |

Every selection persists `coverage_available`, `measured_tests`, warnings, rationale and fallback state. The UI surfaces these instead of silently returning an empty or misleading suite.

### Execution

`TestExecutor` runs pytest with explicit node IDs (or the full suite), a timeout, capped stdout/stderr, sanitized env and repository working directory. Results are parsed into counts and per-test statuses. Test runs and coverage collection require confirmation.

---

## 6. Persistence model

| Table | Contents |
| --- | --- |
| `repositories` | Path, name, status, counts, scan time/error |
| `code_entities` | Parsed symbols with spans, docs, decorators |
| `analyses` | Refs, status, summary counts, JSON impact and selection results |
| `coverage_snapshots` | Context/test maps, measured tests, covered files, duration |
| `test_runs` | Mode, counts, duration, timeout, execution payload |
| `benchmarks` | Full/selected durations, precision/recall, metrics/notes JSON |
| `copilot_conversations` | Repository scope, title, timestamps |
| `copilot_messages` | Role, content, intent, evidence/follow-up/warning JSON, model, latency |

JSON payloads are stored alongside normalized summaries so detail responses can be reconstructed without re-running analysis. `init_db()` creates missing tables on startup.

---

## 7. Service layer

- `RepositoryService` — scan, upsert, list/detail.
- `AnalysisService` / `analysis_pipeline` — detect changes, build graph, analyze, select, persist.
- `GraphService` — fresh graph for visualization with filters.
- `CoverageService` — collect/merge per-test coverage.
- `TestRunService` — resolve mode/test IDs, execute, persist.
- `BenchmarkService` — full + selected execution, precision/recall, persistence.
- `DashboardService` — SQL aggregates and recent activity.
- `CopilotService` — build context, call the optional model, validate citations, persist conversations/messages.
- `file_service` — read-only repository file access for evidence/citation viewing.

Services are thin singletons instantiated per router; the database session is injected per request.

---

## 8. Copilot pipeline

The Copilot is a retrieval-augmented pipeline with a deterministic fallback. It never executes repository code and has no write path to the repository.

```
question ──► intent detection ──► BM25 retrieval ──► graph expansion
                                      │
                                      ├──► Git state / changed files
                                      ├──► impact traversal (hypothetical or real diff)
                                      ├──► test discovery / selection / coverage metadata
                                      └──► deterministic static review
                                      │
                                numbered evidence [E1…En]
                                      │
                       ┌──────────────┴──────────────┐
                       ▼                             ▼
              model answer (if configured)   local evidence answer
                       └──────────────┬──────────────┘
                                      ▼
                     citation validation + secret redaction
```

### Retrieval

`repository_index.py` builds an in-memory BM25 index over each file, its AST symbols and docstrings. Identifiers are tokenized on snake_case and CamelCase boundaries. A query hits files/symbols lexically; hits are then expanded along real graph edges so callers, importers, inheritors and containing files can be included even when they do not share query terms. A character budget (`LLM_MAX_CONTEXT_CHARS`) bounds the evidence set. Secret-like files and values are filtered/redacted during indexing.

### Intent and evidence

`intent.py` selects `architecture`, `explain`, `impact`, `tests`, `git`, `debug`, `code_review` or `security_review`. It extracts file paths, backticked/called symbols, traceback file/line pairs and hypothetical change targets. Follow-ups inherit the previous intent when the new question is generic.

`context_builder.py` assembles live evidence: repository scan summary, Git commits/status/diff, graph neighbors, impact results, selected tests and coverage availability. `static_review.py` performs deterministic AST checks (syntax errors, `eval`/`exec`, shell execution, unsafe `pickle`/`marshal`, mutable defaults, TODO/FIXME comments, secret-like assignments, broad exception handling, unresolved imports) and labels findings `confirmed-pattern` or `potential`.

### Answering and safety

`llm.py` is a small OpenAI-compatible `/chat/completions` client. It is enabled only when a provider/model is configured; local providers (`ollama`, `lmstudio`, `local`) may run without a key. `LLM_API_KEY` never leaves the backend. Provider errors are shortened and redacted.

`prompts.py` treats all repository evidence as untrusted data, forbids following instructions embedded in code/comments, forbids revealing secrets or claiming execution/modification, requires exact `[E#]` citations and tells the model to admit insufficient evidence. `answers.py` removes citations to nonexistent evidence, deduplicates warnings, redacts secret-like strings and the configured API key, and falls back to a local evidence summary if the model fails or is disabled.

The frontend renders answers as React nodes (no raw HTML), makes `[E#]` citations clickable, displays evidence cards and opens a read-only, traversal-safe file drawer with real line numbers. Conversations can be reopened or deleted.

---

## 9. Frontend

```
src/
  api? → services/api.ts        typed fetch client + error normalization
  types/                        mirrors Pydantic schemas
  hooks/useAsync.ts             cancellation-safe fetching
  lib/format.ts                 durations, percentages, paths, tones
  components/                   layout, graph, Markdown renderer, UI primitives, execution view
  pages/                        Dashboard, Repositories, Detail, Analyses, Benchmarks, Copilot
```

The graph view uses a deterministic file-column layout (one column per file, symbols stacked by line) so views are stable without a physics simulation. Edges are colored by relationship; selecting a node reveals its direct incoming/outgoing relationships. All dashboard statistics, benchmark charts and tables come from API responses.

---

## 10. Security boundaries

- No shell execution; Git and pytest use argument-list subprocesses.
- Git refs validated; paths resolved and restricted.
- Test/coverage/benchmark endpoints require `confirm=true`.
- Timeouts and output caps protect against runaway suites/logs.
- CORS limited to the configured frontend origins.
- Copilot is read-only: no execution, file writes or automatic patch application.
- Model credentials are backend-only environment/config values and are redacted from status, errors and answers.
- Model context is bounded retrieval evidence, never the whole repository; prompts treat evidence as untrusted and defend against prompt injection.
- Copilot answers are rendered without raw HTML; the file viewer rejects traversal, symlinks, binary files and oversized files.
- Never expose this service publicly while allowing arbitrary repository paths and test execution without an authentication/authorization layer.
