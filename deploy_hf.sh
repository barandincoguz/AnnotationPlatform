#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
deploy_dir=""
deploy_branch=""

cleanup() {
  if [[ -n "$deploy_dir" && -d "$deploy_dir" ]]; then
    git -C "$repo_root" worktree remove --force "$deploy_dir" >/dev/null 2>&1 || true
  fi
  if [[ -n "$deploy_branch" ]] && git -C "$repo_root" show-ref --verify --quiet "refs/heads/$deploy_branch"; then
    git -C "$repo_root" branch -D "$deploy_branch" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ -n "$(git -C "$repo_root" status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked changes are uncommitted; commit and verify them before deployment." >&2
  exit 1
fi

hf_url="$(git -C "$repo_root" config --get remote.hf.url || true)"
if [[ "$hf_url" != "https://huggingface.co/"* || "$hf_url" == *"@"* ]]; then
  echo "The hf remote must be a credential-free huggingface.co HTTPS URL." >&2
  exit 1
fi

git -C "$repo_root" fetch hf main
expected_remote="$(git -C "$repo_root" rev-parse refs/remotes/hf/main)"
deploy_dir="$(mktemp -d "${TMPDIR:-/tmp}/annotation-hf-deploy.XXXXXX")"
deploy_branch="hf-deploy-${deploy_dir##*.}"
git -C "$repo_root" worktree add --detach "$deploy_dir" HEAD

git -C "$deploy_dir" checkout --orphan "$deploy_branch"
git -C "$deploy_dir" rm -r --cached --quiet .

# Only runtime source and the HF Space manifest are publishable. Internal docs,
# research data, runbooks, audit material, agent skills, and git history never
# enter the deployment index.
deploy_paths=(
  ".dockerignore"
  "Dockerfile"
  "README.md"
  "pyproject.toml"
  "requirements.txt"
  "backend"
  "frontend/.npmrc"
  "frontend/package.json"
  "frontend/package-lock.json"
  "frontend/index.html"
  "frontend/postcss.config.js"
  "frontend/tailwind.config.ts"
  "frontend/tsconfig.json"
  "frontend/tsconfig.node.json"
  "frontend/vite.config.ts"
  "frontend/public"
  "frontend/src"
)
git -C "$deploy_dir" add -- "${deploy_paths[@]}"

# Directory-level runtime roots contain co-located tests in the development
# checkout. Remove every test/fixture/debug path from the orphan index, then
# verify the exclusion itself; a newly introduced matching file must never
# silently enter the public Space source tree.
deploy_excludes=(
  "backend/tests"
  "frontend/e2e"
  "frontend/src/test"
  ":(glob)frontend/src/**/*.test.ts"
  ":(glob)frontend/src/**/*.test.tsx"
  ":(glob)frontend/src/**/*.test.js"
  ":(glob)frontend/src/**/*.test.jsx"
)
git -C "$deploy_dir" rm -r --cached --ignore-unmatch -- "${deploy_excludes[@]}"

forbidden_matches="$(git -C "$deploy_dir" ls-files -- "${deploy_excludes[@]}")"
if [[ -n "$forbidden_matches" ]]; then
  echo "Refusing deployment: test or fixture files remain in the Space index." >&2
  echo "$forbidden_matches" >&2
  exit 1
fi

git -C "$deploy_dir" commit -m "deploy: historyless HF Space release"

parent_count="$(git -C "$deploy_dir" rev-list --parents -n 1 HEAD | wc -w | tr -d ' ')"
if [[ "$parent_count" != "1" ]]; then
  echo "Refusing deployment: generated commit unexpectedly has history." >&2
  exit 1
fi

git -C "$deploy_dir" push \
  --force-with-lease="main:$expected_remote" \
  hf HEAD:main

echo "HF Space deployment completed from a historyless, whitelisted commit."
