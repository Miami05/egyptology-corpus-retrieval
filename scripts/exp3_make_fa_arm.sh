#!/usr/bin/env bash
# Experiment 3: make the F-a arm commit for scripts/run_exp3_prereg.sh.
#
#   bash scripts/exp3_make_fa_arm.sh BASE_SHA [BRANCH]
#
# The arms "differ only in the commit" (ROADMAP Experiment 3 addendum, pinned
# commands), so the F-a arm is BASE_SHA plus exactly one changed line,
# `EXP3_FA_DEFAULT = False` -> `True` in app/services/faithful.py. This writes that
# commit with git plumbing (a temporary index; no checkout, no working tree touched),
# points BRANCH (default exp3-fa-arm-2026-10-26) at it and prints its sha. Re-run it
# whenever BASE_SHA changes (e.g. after merging main / the KRI fixes into the branch).
set -euo pipefail

if [ "$#" -lt 1 ] || ! [[ "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: bash scripts/exp3_make_fa_arm.sh BASE_SHA [BRANCH]" >&2
  exit 2
fi
BASE_SHA=$1
BRANCH=${2:-exp3-fa-arm-2026-10-26}
FILE=app/services/faithful.py

old=$(git show "$BASE_SHA:$FILE")
new=$(printf '%s\n' "$old" | sed 's/^EXP3_FA_DEFAULT = False$/EXP3_FA_DEFAULT = True/')
changed=$(diff <(printf '%s\n' "$old") <(printf '%s\n' "$new") | grep -c '^[<>]' || true)
if [ "$changed" != 2 ]; then
  echo "expected exactly one line 'EXP3_FA_DEFAULT = False' in $FILE at $BASE_SHA" >&2
  exit 1
fi
blob=$(printf '%s\n' "$new" | git hash-object -w --stdin)
INDEX=$(mktemp)
trap 'rm -f "$INDEX"' EXIT
GIT_INDEX_FILE=$INDEX git read-tree "$BASE_SHA"
GIT_INDEX_FILE=$INDEX git update-index --cacheinfo "100644,$blob,$FILE"
tree=$(GIT_INDEX_FILE=$INDEX git write-tree)
msg="Experiment 3: the F-a arm (EXP3_FA_DEFAULT = True)

The one-line arm commit of the pre-registered run (ROADMAP.md, Experiment 3
addendum 2026-10-26): its parent $BASE_SHA is the base arm. Not for merging;
F-a becomes the default only through step 4.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
commit=$(git commit-tree "$tree" -p "$BASE_SHA" -m "$msg")
git branch -f "$BRANCH" "$commit" >/dev/null
echo "$commit"
