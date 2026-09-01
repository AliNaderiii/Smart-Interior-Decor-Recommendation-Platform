#!/usr/bin/env bash
# Install the canonical workflow into GitHub's active path.
#
# The Arena sandbox GitHub App is intentionally unable to do this: GitHub
# rejects a push that creates/updates .github/workflows/* without the App's
# `workflows` permission. Run this script from a normal clone authenticated as
# a repository owner/maintainer with a token that has the `workflow` scope:
#
#   cp ci/github-ci.yml .github/workflows/ci.yml
#   ./scripts/enable_ci.sh
#
# The script commits only the workflow file and pushes the current branch. It
# never asks for or stores credentials and never force-pushes.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ ! -f ci/github-ci.yml ]]; then
  echo "ERROR: canonical workflow ci/github-ci.yml is missing" >&2
  exit 1
fi

# Safety guard (added 2026-09-01): the workflow may have been activated already
# and *evolved past* the staged copy (e.g. by a direct edit with the workflow
# scope). Overwriting it with the older canonical file would silently regress
# CI. Refuse in that case; ask the operator to reconcile first.
if [[ -f .github/workflows/ci.yml ]] && ! cmp -s ci/github-ci.yml .github/workflows/ci.yml; then
  if [[ "${1:-}" == "--sync-canonical" ]]; then
    # Active workflow is newer — adopt it as the canonical copy instead.
    cp .github/workflows/ci.yml ci/github-ci.yml
    echo "Synced canonical ci/github-ci.yml from the active workflow."
  else
    echo "ERROR: .github/workflows/ci.yml already exists and differs from ci/github-ci.yml." >&2
    echo "       Refusing to overwrite (would possibly regress an evolved workflow)." >&2
    echo "       Reconcile, then either rerun, or adopt the active copy with:" >&2
    echo "         ./scripts/enable_ci.sh --sync-canonical" >&2
    exit 1
  fi
fi

mkdir -p .github/workflows
cp ci/github-ci.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml

# Do not accidentally include an unrelated staged change in the activation
# commit. This is especially useful when an operator runs the command from a
# working tree that contains an in-progress release.
mapfile -t staged < <(git diff --cached --name-only)
for path in "${staged[@]}"; do
  if [[ "$path" != ".github/workflows/ci.yml" ]]; then
    echo "ERROR: unrelated staged path would be included: $path" >&2
    echo "Unstage it, then rerun this script." >&2
    exit 1
  fi
done

if git diff --cached --quiet; then
  echo "Workflow already matches ci/github-ci.yml; no activation commit needed."
else
  git commit -m "ci: enable GitHub Actions workflow"
fi

branch=$(git branch --show-current)
if [[ -z "$branch" ]]; then
  echo "ERROR: detached HEAD; check out the intended branch before enabling CI." >&2
  exit 1
fi

echo "Pushing workflow on branch: $branch"
echo "This push requires GitHub workflow-file permission (PAT workflow scope or equivalent)."
git push origin HEAD

echo "CI workflow installed. Confirm a real run in the GitHub Actions tab before treating checks as active."
