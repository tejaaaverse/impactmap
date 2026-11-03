# Benchmark datasets

This directory is reserved for benchmark dataset descriptions and captured measurement manifests.

IMPACTMAP benchmarks are executed against **real Git repositories**. A dataset is currently defined by:

- repository path / id,
- base ref,
- head ref,
- selection mode (`safe` or `optimized`),
- optional dataset label stored on the benchmark row,
- timeout.

There is no synthetic fault injection and no fabricated speedup data. Benchmark rows are produced only by `POST /api/benchmarks/run`.

## Bundled dataset

`sample_repositories/calculator` is initialized as a Git repository with two commits:

```
<hash>  Baseline calculator sample
<hash>  Coerce power base to float
```

Hashes vary by generation time. If the nested `.git` directory was stripped from your checkout, run `scripts/init-sample-repo.sh` from the project root.

Recommended run:

```json
{
  "base_ref": "HEAD~1",
  "head_ref": "WORKING",
  "mode": "optimized",
  "dataset_name": "calculator-power-change",
  "confirm": true
}
```

See [../docs/benchmarks.md](../docs/benchmarks.md) for metric definitions and reproduction steps.

## Adding a dataset

1. Ensure the target repository is a Git working tree and its tests pass.
2. Collect per-test coverage if you want precision/recall (`POST /api/repositories/{id}/coverage`).
3. Run `POST /api/benchmarks/run` with `confirm=true`.
4. Export `GET /api/benchmarks/{id}` for the full measurement payload.

Store large external datasets outside this directory; commit only manifests or links.
