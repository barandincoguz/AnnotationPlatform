#!/bin/bash
set -e

echo "🚀 Deploying stripped-down version to Hugging Face Spaces..."

# Make sure we're on main and up to date locally
git checkout main

# Create or reset a temporary deployment branch
git branch -D hf-deploy 2>/dev/null || true
git checkout -b hf-deploy

echo "🧹 Removing unnecessary documentation and old planning files for HF..."
git rm -r --quiet audit/ .planning/ thoughts/ runbooks/ tasks/ plans/ docs/superpowers/ docs/annotation-quality-harness/ docs/screenshots/ paper/ docs/dev-with-feedback-report.md docs/quality-audit-operations.md 2>/dev/null || true

echo "📦 Committing stripped version..."
git commit -q -m "chore: deploy stripped production version to HF Spaces"

echo "☁️ Pushing to Hugging Face Spaces..."
git push -f hf hf-deploy:main

echo "✅ Deployment successful. Returning to main branch."
git checkout main
echo "All your files are perfectly intact on your local machine and GitHub!"
