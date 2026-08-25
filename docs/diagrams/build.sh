#!/usr/bin/env bash
# Rebuild every diagram SVG from its d2 source.
#
#   brew install d2      (or: https://d2lang.com/install)
#   docs/diagrams/build.sh
#
# Output lands in docs/images/ and is committed, so the README renders on
# GitHub and on the Hugging Face Space without a build step.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
out="$here/../images"
render() { d2 --theme 0 --pad 24 "$here/$1.d2" "$out/$2.svg"; }

render architecture   architecture
render lock-lifecycle lock-lifecycle
render workflow-states workflow-states
echo "diagrams rebuilt into $out"
