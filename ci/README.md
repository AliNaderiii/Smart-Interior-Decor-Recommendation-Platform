# CI workflow

GitHub blocked the automated push of workflow files (the integration lacks the
`workflows` permission). To activate CI, move this file back:

```bash
mkdir -p .github/workflows
git mv ci/github-ci.yml .github/workflows/ci.yml
git commit -m "ci: enable GitHub Actions workflow"
git push
```

Jobs: backend pytest (43 tests) + extraction benchmark + ruff · frontend
strict tsc build · Lighthouse gate (fails <80 performance on the app).
