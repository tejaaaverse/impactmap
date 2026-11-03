#!/usr/bin/env bash
#
# Recreate the sample calculator repository's two-commit history.
#
# The dashboard demo expects a real Git repository whose HEAD~1..WORKING diff
# touches utils/math_helpers.py::power. Some checkout/copy mechanisms discard
# nested .git directories, so this script rebuilds the history from the sample
# working tree without changing the files that are on disk.
#
# Usage:
#   scripts/init-sample-repo.sh            # create history if it is missing
#   scripts/init-sample-repo.sh --force    # erase and recreate the history
#
# SAMPLE_DIR=/path/to/calculator scripts/init-sample-repo.sh --force

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAMPLE_DIR="${SAMPLE_DIR:-$ROOT_DIR/sample_repositories/calculator}"
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help)
      sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

command -v git >/dev/null 2>&1 || { echo "git is required" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

if [[ ! -d "$SAMPLE_DIR" ]]; then
  echo "sample repository not found: $SAMPLE_DIR" >&2
  exit 1
fi
SAMPLE_DIR="$(cd "$SAMPLE_DIR" && pwd)"

if [[ -d "$SAMPLE_DIR/.git" ]]; then
  if (( FORCE == 0 )); then
    echo "Git history already exists in $SAMPLE_DIR"
    echo "Re-run with --force to erase and recreate it."
    exit 0
  fi
  rm -rf "$SAMPLE_DIR/.git"
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/impactmap-sample.XXXXXX")"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

# Snapshot the final working tree; it contains the post-change version of
# power() that the second commit should introduce.
cp -R "$SAMPLE_DIR/." "$TMP_DIR/"
rm -rf "$TMP_DIR/.git" "$TMP_DIR/.pytest_cache"
find "$TMP_DIR" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$TMP_DIR" -type f -name '*.py[co]' -delete 2>/dev/null || true

# Rewrite math_helpers.py to the pre-change version for the baseline commit.
python3 - "$SAMPLE_DIR/utils/math_helpers.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text()
final = '''def power(a: float, b: float) -> float:
    """Raise a to the power of b.

    The base is coerced to float so fractional exponents and very large
    integer bases produce a stable floating-point result.
    """
    return float(a) ** b
'''
baseline = '''def power(a: float, b: float) -> float:
    """Raise a to the power of b."""
    return a ** b
'''
if final not in text:
    raise SystemExit(f"unexpected power() implementation in {path}")
path.write_text(text.replace(final, baseline, 1))
PY

(
  cd "$SAMPLE_DIR"
  git init -q -b main
  git config user.name "IMPACTMAP Sample"
  git config user.email "sample@impactmap.local"
  git add -A
  git commit -q -m "Baseline calculator sample"
)

# Restore the final working tree and record it as the change under test.
cp -R "$TMP_DIR/." "$SAMPLE_DIR/"

(
  cd "$SAMPLE_DIR"
  git add -A
  git commit -q -m "Coerce power base to float"
  git status --short
  echo
  git log --oneline
)
