# IMPACTMAP

**Code-impact analysis and intelligent test selection for Python repositories.**

IMPACTMAP scans a repository, builds a typed symbol/dependency graph from the Python AST, detects changes from Git, traverses reverse dependencies to explain what a change can affect, and selects the smallest defensible set of tests to run. A React dashboard exposes the graph, impact paths, coverage evidence, test runs and measured benchmarks.

A repository-aware **Copilot** adds grounded architecture, review, debug, test and impact questions. It retrieves relevant files/symbols, expands through the dependency graph, cites evidence such as `[E1]`, and can use an OpenAI-compatible model when one is configured. Without a model key it still answers from local static evidence; it never executes repository code or edits files.

The analysis engine is real: graph edges come from parsed imports, calls and inheritance; impact is a reverse traversal over those edges; test selection uses per-test Coverage.py data when available and documents its fallbacks when it is not; benchmark durations come from executing both suites in subprocesses.

The user interface features a distinctive **Y2K cyber-pink developer universe** with deep plum backgrounds, glowing accents, pixel typography, interactive graphs, and two roaming digital pet companions (**Pip the Rabbit** and **Moss the Tortoise**) offering developer encouragement and coding wisdom.

---

## Architecture

```
┌────────────────────────────┐        ┌────────────────────────────────────┐
│ React + TypeScript + Vite  │  /api  │ FastAPI                            │
│ React Flow · Recharts      │ ─────► │ Routers → Services → Engine        │
└────────────────────────────┘        └───────────────┬────────────────────┘
                                                      │
                              ┌───────────────────────┼───────────────────────┐
                              ▼                       ▼                       ▼
                        Scanner + AST            Git diff + graph        Test selection
                        (files, symbols)         (NetworkX, impact)      (coverage/static)
                              │                       │                       │
                              └───────────────────────┴───────────────────────┘
                                                      │
                                             SQLAlchemy async
                                          SQLite / PostgreSQL
```

- **Backend** — Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 async, NetworkX.
- **Frontend** — React 18, TypeScript, Vite, Tailwind CSS, React Flow, Recharts, Lucide.
- **Execution** — pytest subprocesses, Coverage.py dynamic contexts, argument-list Git subprocesses.

See [docs/architecture.md](docs/architecture.md) for the engine internals and data model, and [docs/benchmarks.md](docs/benchmarks.md) for metric definitions.

---

## Quick start

### 1. Backend

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
DEBUG=false .venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

Default database: `backend/impactmap.db` (`sqlite+aiosqlite:///./impactmap.db`). Set `DATABASE_URL` for PostgreSQL, for example:

```bash
DATABASE_URL=postgresql+asyncpg://impactmap:impactmap@localhost:5432/impactmap
```

PostgreSQL use additionally requires the `asyncpg` driver (`pip install asyncpg`).

#### Optional: enable model-written Copilot answers

Copy `backend/.env.example` to `backend/.env` and set the provider variables. Keys are read only by the backend and are never sent to the browser or returned by an endpoint.

```bash
LLM_PROVIDER=openai-compatible
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Any OpenAI-compatible `/chat/completions` server works. For a local server without authentication, set `LLM_PROVIDER=ollama` (or `lmstudio`/`local`) and `LLM_BASE_URL`, for example `http://localhost:11434/v1`. If no key/provider is configured, Copilot stays in local evidence mode and the rest of IMPACTMAP is unaffected.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `openai-compatible` | Provider label; `none` disables model calls, local labels allow keyless servers |
| `LLM_API_KEY` | empty | Backend-only credential; never exposed |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `LLM_MODEL` | `gpt-4o-mini` | Model identifier |
| `LLM_TIMEOUT_SECONDS` | `60` | Provider request timeout |
| `LLM_MAX_OUTPUT_TOKENS` | `1200` | Answer token cap |
| `LLM_MAX_CONTEXT_CHARS` | `24000` | Retrieved-evidence character budget |
| `COPILOT_RETRIEVAL_TOP_K` | `6` | Base retrieval result count before graph expansion |
| `COPILOT_MAX_FILE_BYTES` | `600000` | Largest file the viewer/Copilot may read |
| `COPILOT_MAX_HISTORY_MESSAGES` | `12` | Prior messages included in a follow-up

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to `http://localhost:8000`; override with `VITE_PROXY_TARGET`.

### 3. Demo repository

The bundled sample is a real Git repository with two commits and 20 pytest tests. If your checkout or archive tool strips nested `.git` directories, rebuild the history with:

```bash
./scripts/init-sample-repo.sh          # creates history only if missing
./scripts/init-sample-repo.sh --force  # recreates it (new commit hashes)
```

Then verify:

```bash
cd sample_repositories/calculator
../../backend/.venv/bin/python -m pytest -q    # 20 passed
git log --oneline
# <hash> Coerce power base to float
# <hash> Baseline calculator sample
```

Commit hashes depend on when the history was created; the two commit subjects and the `utils/math_helpers.py::power` diff are stable.

In the dashboard:

1. **Repositories → scan** the absolute path to `sample_repositories/calculator`.
2. **Analyze changes** with base `HEAD~1` and head `WORKING`.
3. Open **Impact** to inspect direct/indirect entities and dependency paths.
4. Open **Test selection** to compare safe and optimized modes.
5. **Tests & coverage** → collect coverage once (requires confirmation), then re-run the analysis to use coverage evidence.
6. **Benchmarks** → run a measured full-vs-selected comparison.
7. **Copilot** → choose the repository, ask about architecture/impact/tests/Git changes, and click a citation or evidence card to open the read-only file viewer.

The default `HEAD~1..WORKING` diff is non-empty because the sample’s second commit changed `utils/math_helpers.power`, while the working tree is clean.

---

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health/version |
| `POST` | `/api/repositories/scan` | Scan a local Python repository |
| `GET` | `/api/repositories` | List scanned repositories |
| `GET` | `/api/repositories/{id}` | Repository detail + entities |
| `GET` | `/api/repositories/{id}/graph` | Typed dependency graph |
| `POST` | `/api/repositories/{id}/analyze` | Git-diff impact analysis + selection |
| `GET` | `/api/repositories/{id}/tests` | Discovered pytest tests |
| `GET` | `/api/repositories/{id}/coverage` | Coverage snapshots |
| `POST` | `/api/repositories/{id}/coverage` | Collect per-test coverage (`confirm=true`) |
| `GET` | `/api/repositories/{id}/git-status` | Git availability |
| `GET` | `/api/repositories/{id}/git-refs` | Commits, branches, dirty state, recommended refs |
| `GET` | `/api/repositories/{id}/file?path=…` | Read-only, path-validated file viewer |
| `GET` | `/api/analysis` | Analysis history |
| `GET` | `/api/analysis/{id}` | Analysis detail |
| `GET` | `/api/analysis/{id}/impact` | Impact result |
| `GET` | `/api/analysis/{id}/tests` | Safe/optimized selections |
| `POST` | `/api/analysis/{id}/run-tests` | Execute tests (`confirm=true`) |
| `GET` | `/api/analysis/{id}/test-runs` | Execution history |
| `GET` | `/api/benchmarks` | Benchmark history |
| `POST` | `/api/benchmarks/run` | Measured full-vs-selected run (`confirm=true`) |
| `GET` | `/api/benchmarks/{id}` | Benchmark + execution payloads |
| `GET` | `/api/dashboard` | Aggregate live statistics |
| `GET` | `/api/copilot/status` | Credential-free Copilot/provider status |
| `POST` | `/api/copilot/repositories/{id}/chat` | Ask a repository-scoped question |
| `GET` | `/api/copilot/conversations` | Saved Copilot threads (optional `repository_id`) |
| `GET` | `/api/copilot/conversations/{id}` | Thread with messages and evidence |
| `DELETE` | `/api/copilot/conversations/{id}` | Delete a thread and its messages |

Example:

```bash
curl -s -X POST http://localhost:8000/api/repositories/scan \
  -H 'Content-Type: application/json' \
  -d '{"path":"/absolute/path/to/sample_repositories/calculator"}'
```

---

## How it works

### Graph

Nodes use stable IDs:

- `file:<path>`
- `module:<package>`
- `func:<path>::<qualified_name>`
- `class:<path>::<qualified_name>`
- `method:<path>::<qualified_name>`

Edges point **dependent → dependency**. Impact traversal therefore walks **incoming** edges: if `api.py` calls `calculator.py`, the edge is `api → calculator`, and a change in `calculator` reaches `api`.

### Change detection

Git diffs are parsed directly (never through a shell). The detector maps added/deleted line spans to Python entity spans, detects renames/deletions, and handles working-tree changes with `WORKING`.

### Impact scoring

Direct seeds start at `100`. Each reverse hop multiplies by the edge-type weight (`call` 1.0, `inherits` 0.9, `import_symbol` 0.7, `import` 0.55, `contains` 0.35), a confidence factor (`0.65 + 0.35 × confidence`), a hop decay (`0.9`) and a target-type factor. Every result stores its dependency path and a human-readable reason. These are **risk signals**, not failure predictions.

### Test selection

- **Safe** — all tests with a coverage/static link to changed or affected code, changed test files, and previously failing tests. Without coverage it selects the complete suite and says so.
- **Optimized** — coverage-backed tests covering changed entities or strongly affected dependencies, plus changed/historically failing tests. Without coverage it uses static reachability, then falls back to the full suite with an explicit warning.

Fallback state, warnings, rationale and `coverage_available` are persisted with every analysis.

### Execution safety

Coverage collection, test runs and benchmarks require `confirm=true`. They execute repository code in subprocesses with timeouts, capped output capture and a sanitized environment. Scanning rejects system paths and paths outside configured allow-lists.

---

## Copilot

The Copilot is repository-scoped and read-only. It combines local retrieval and analysis with an optional OpenAI-compatible model:

1. **Intent routing** — deterministic detection of architecture, explain, impact, tests, Git, debug/traceback, code review and security review questions. File paths, symbols and traceback lines are extracted and used to focus retrieval.
2. **Retrieval** — a local BM25 index over files, AST symbols and docstrings. Results are expanded through the real dependency graph (callers, imports, inheritance, containing files), not by sending the whole repository.
3. **Live evidence** — Git history/status, impact analysis, test selection, test discovery, coverage metadata and deterministic review findings are collected when relevant.
4. **Answering** — with a configured provider, the model receives a bounded, numbered evidence set and a prompt that treats repository content as untrusted data. Without a provider, IMPACTMAP composes a deterministic answer from the same evidence and clearly labels local mode.
5. **Citation hygiene** — answers may cite only supplied evidence IDs such as `[E1]`; citations to missing evidence are removed with a warning. Secret-like values and any configured API key echoed by a provider are redacted.
6. **History** — conversations and messages (including evidence, follow-ups and warnings) are stored in SQLite/PostgreSQL and can be reopened from the Copilot sidebar.

What it will not do: execute repository code, run tests, issue shell commands, edit files or apply patches automatically. Static-review findings are patterns with confidence labels, not proof of a vulnerability. Impact scores remain static risk signals.

Useful prompts:

- “Explain the overall architecture of this repository.”
- “What breaks if I change `power` in `utils/math_helpers.py`?”
- “Which tests should I run for this change?”
- “Review this repository for likely bugs and risky code.”
- “Here is my traceback: …” (file/line hints are extracted).
- Follow-ups inherit the previous intent and conversation context.

### Copilot security model

- `LLM_API_KEY` is read only from backend configuration/environment. It is never accepted from the browser, logged, returned by `/api/copilot/status`, or included in prompts.
- Repository evidence is fenced as untrusted data; the system prompt forbids following instructions found in comments, docstrings or files and forbids claiming execution or modifications.
- Answers are rendered as React nodes, not raw HTML. Raw HTML is shown as text and links are limited to safe schemes.
- File viewing is read-only, confined to the scanned repository, rejects traversal/symlinks, binary files and files above `COPILOT_MAX_FILE_BYTES`.
- Conversation deletion removes the thread and its messages; no repository file is touched.

---

## Development

```bash
# Backend tests
cd backend && DEBUG=false .venv/bin/python -m pytest -q

# Frontend typecheck, tests and production build
cd frontend && npm run typecheck && npm test && npm run build
```

Optional root shortcuts:

```bash
make test        # backend + frontend
make build       # frontend production build
make dev-api     # uvicorn
make dev-ui      # vite
```

### Docker

```bash
docker compose up --build
```

- Dashboard: http://localhost:3000
- API: http://localhost:8000
- Sample repositories are mounted at `/repositories`; SQLite data lives in the `impactmap-data` volume.

---

## Validation snapshot

The repository was validated end-to-end:

- Backend: **153 passed** (`pytest`), including Git edge cases, scanner/graph/impact/selection, Copilot retrieval/intent/LLM/citation security and API integration.
- Sample repository: **20 passed** (`pytest`).
- Frontend: **35 passed** (`vitest`), TypeScript clean, production build succeeds.
- Copilot tests run without a live model: provider calls use `httpx.MockTransport`, and tests assert that keys are never exposed or echoed.
- Manual API smoke: scan → graph → analyze → impact → tests → run-tests → coverage → re-analysis → benchmark → dashboard; Copilot chat/history/delete, Git refs and the file viewer.

---

## Limitations

- Python only; other languages are ignored by the parser.
- Static calls/imports are resolved conservatively. Dynamic imports, reflection, plugin registries and runtime-generated code are not fully modeled.
- Coverage is per-test via Coverage.py dynamic contexts; tests executed outside pytest or in separate processes may not be attributed.
- Precision/recall in benchmarks are **coverage-based selection metrics**, not fault-detection accuracy.
- Benchmark wall-clock reduction includes pytest startup overhead, so small suites may show little or no time improvement even with fewer tests.
- SQLite is the default. PostgreSQL requires installing `asyncpg`; the schema itself is portable.
- Diff analysis requires Git. Zero-commit and single-commit repositories use `EMPTY` and `HEAD` fallbacks with explicit warnings; non-Git directories still support scanning and graph exploration.
- Copilot retrieval is lexical BM25 plus graph expansion, not semantic embeddings. Synonyms, dynamic dispatch and concepts absent from code/docstrings may be missed.
- Model-written answers depend on the configured provider and can still be wrong; citations and warnings help verification but are not a correctness guarantee.
- Static review reports patterns (for example `eval`, `shell=True`, mutable defaults, TODO/FIXME) with confidence labels. It is not a full security audit and does not prove exploitability.
- Without an LLM key, Copilot answers are intentionally concise local evidence summaries rather than open-ended reasoning.

---

## License

Internal/demo project. Add a license before distributing.
