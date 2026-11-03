# Benchmarking & Metrics

IMPACTMAP benchmarks are **measurements**, not synthetic estimates. The benchmark endpoint:

1. Builds or reuses an analysis for a Git diff.
2. Runs the complete discovered suite in a pytest subprocess.
3. Runs the selected suite (safe or optimized) in a second subprocess.
4. Records measured wall-clock durations, exit statuses and per-test results.
5. Computes coverage-based precision/recall from the repository's coverage snapshot.

Both runs use the same interpreter, working directory and timeout.

---

## Metric definitions

### `full_duration_ms`

Measured wall-clock duration of the complete suite, including pytest startup.

### `selected_duration_ms`

Measured wall-clock duration of the selected suite. `0` when nothing was selected and the suite was skipped.

### `reduction_percent`

```
(1 − selected_duration_ms / full_duration_ms) × 100
```

This is a **time** reduction, not a test-count reduction. Small suites can show little improvement because pytest startup dominates. The raw count reduction is stored in `metrics.selection_count_reduction_percent`.

### `selection_precision`

```
selected tests that cover ≥1 affected entity / selected tests
```

Coverage-based. A selected test that covers no affected entity lowers precision — even if it is a reasonable conservative selection.

### `selection_recall`

```
affected entities covered by the full suite and also by selected tests
/ affected entities covered by the full suite
```

Coverage-based. Recall is `null` when per-test coverage is unavailable, rather than fabricated.

These are **selection-quality metrics**, not fault-detection accuracy. IMPACTMAP does not inject faults or claim to predict test failures.

### Fallback state

Stored per selection and benchmark:

- `coverage_available` — whether per-test coverage was present.
- `fallback_used` — whether the mode reverted to the full suite because no evidence linked tests to the change.
- `warnings` / `rationale` — why the selection looks the way it does.

A benchmark with `fallback_used=true` and a full-suite selection should be read as “no safe reduction was possible,” not as a failure.

---

## Reproducing a measurement

### Through the UI

1. Scan `sample_repositories/calculator`.
2. Go to **Benchmarks**.
3. Select the repository, base `HEAD~1`, head `WORKING`, mode `optimized`.
4. Optionally label the dataset (e.g. `calculator-power-change`).
5. Confirm and run.

### Through the API

```bash
# Discover the repository id
curl -s http://localhost:8000/api/repositories | python -m json.tool

# Run a measured benchmark against the stored diff
curl -s -X POST http://localhost:8000/api/benchmarks/run \
  -H 'Content-Type: application/json' \
  -d '{
    "repository_id": "<repo-id>",
    "base_ref": "HEAD~1",
    "head_ref": "WORKING",
    "mode": "optimized",
    "dataset_name": "calculator-power-change",
    "confirm": true
  }' | python -m json.tool
```

To exercise coverage-based precision/recall, collect coverage first:

```bash
curl -s -X POST http://localhost:8000/api/repositories/<repo-id>/coverage \
  -H 'Content-Type: application/json' \
  -d '{"confirm": true, "timeout_seconds": 600}'
```

Then run the analysis/benchmark again so selection can use the snapshot.

---

## Sample dataset

The bundled `sample_repositories/calculator` is a Git repository with two commits:

| Commit subject | Description |
| --- | --- |
| `Baseline calculator sample` | Pre-change `power()` implementation |
| `Coerce power base to float` | Adds float coercion and an expanded docstring |

Exact hashes depend on when the history was generated. Run `scripts/init-sample-repo.sh` if the nested `.git` directory is missing, then confirm the subjects with `git log --oneline`.

The second commit changes a real function, so `HEAD~1..WORKING` yields a non-empty diff. The suite contains 20 tests across calculator, math helper and validator tests. This dataset is intentionally small; it validates correctness and wiring, not large-scale speedups.

Recommended labels:

- `calculator-power-change` — default diff, optimized mode.
- `calculator-power-change-safe` — same diff, safe mode.
- `calculator-full-suite` — no-change/fallback behavior.

---

## Interpreting results honestly

- **Do** compare full and selected durations from the same run.
- **Do** inspect precision/recall alongside the selected test list.
- **Do** check `warnings`, `fallback_used` and `coverage_available`.
- **Don’t** treat a high reduction as proof of correctness; it is a scheduling optimization paired with risk analysis.
- **Don’t** compare across machines or interpreters as if they were controlled measurements.

The benchmark UI displays stored values directly. There are no hardcoded improvements, curated “wins,” or synthetic trend lines.
