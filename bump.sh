#!/usr/bin/env bash
# Usage: ./bump.sh          → increments patch  (1.3.0 → 1.3.1)
#        ./bump.sh minor    → increments minor  (1.3.0 → 1.4.0)
#        ./bump.sh major    → increments major  (1.3.0 → 2.0.0)
set -euo pipefail

FILE="version.json"
current=$(python3 -c "import json; print(json.load(open('$FILE'))['version'])")
IFS='.' read -r major minor patch <<< "$current"

case "${1:-patch}" in
  major) major=$((major+1)); minor=0; patch=0 ;;
  minor) minor=$((minor+1)); patch=0 ;;
  *)     patch=$((patch+1)) ;;
esac

new="$major.$minor.$patch"
echo "{ \"version\": \"$new\" }" > "$FILE"
echo "Bumped $current → $new"
