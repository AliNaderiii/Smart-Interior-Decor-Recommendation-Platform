#!/usr/bin/env bash
# One-command CI activation.
#
# The Arena sandbox's GitHub App token cannot push workflow files
# (`refusing to allow a GitHub App to ... update workflow ... without
# 'workflows' permission`), so the canonical workflow lives in ci/github-ci.yml.
# Run this from a normally-authenticated clone (your laptop / PAT with
# `workflow` scope):
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
mkdir -p .github/workflows
cp ci/github-ci.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "ci: enable GitHub Actions workflow"
git push
echo "CI enabled — check the Actions tab."
