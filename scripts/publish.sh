#!/usr/bin/env bash
set -euo pipefail

# Publish helper for analyze-qna
# - Bumps version (patch by default)
# - Packs and shows contents
# - Publishes to npm
#
# Usage:
#   scripts/publish.sh [patch|minor|major]
#
# Notes:
# - This does not create git commits or tags. Handle git workflow yourself.
# - Ensure you're logged in: `npm login`

BUMP_TYPE="${1:-patch}"

if [[ "$BUMP_TYPE" != "patch" && "$BUMP_TYPE" != "minor" && "$BUMP_TYPE" != "major" ]]; then
  echo "Invalid bump type: $BUMP_TYPE (expected: patch|minor|major)" >&2
  exit 1
fi

# Bump version in package.json only (no git tag/commit)
npm version "$BUMP_TYPE" --no-git-tag-version

# Show resulting version
VERSION=$(node -p "require('./package.json').version")
echo "Version bumped to: $VERSION"

# Pack and show contents
FILE=$(npm pack --silent)
echo "Packed: $FILE"

tar -tf "$FILE" | cat

# Publish
npm publish

echo "Published analyze-qna@$VERSION"
