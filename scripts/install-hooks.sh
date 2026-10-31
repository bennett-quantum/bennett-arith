#!/usr/bin/env bash
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
script_dir="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
root="$(git -C "$script_dir" rev-parse --show-toplevel)"
test -x "$root/.beads/hooks/pre-push"
# Preserve Beads' other hooks and use a relative path that works in clean worktrees.
git -C "$root" config --local core.hooksPath .beads/hooks
echo 'installed .beads/hooks/pre-push -> scripts/pre-push'
