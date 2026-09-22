#!/usr/bin/env bash
# Produce the history-free public tree for github.com/tetrionlabs/mathema.
#
# The published repository must never contain the private development
# history. The working tree is clean (no private file has ever been
# committed), but the COMMIT MESSAGES are not: they reference `.smd`
# notes, internal product strategy, and at least one superseded legal
# statement. This script takes a tag, exports
# exactly that tree via `git archive` (which honours .gitignore'd and
# untracked exclusions by construction: only committed content at the
# tag is exported), and creates a fresh repository whose entire history
# is one commit.
#
# Run it from the development repo root, AFTER stamping the LICENSE and
# tagging, and BEFORE pushing anything public:
#
#   scripts/make_public_export.sh v0.6.0 ../mathema-public
#
# Or, to SEED the published repository once from main before any
# release tag exists:
#
#   scripts/make_public_export.sh main ../mathema-seed
#
# Then run the code-docs checklist and the pre-publication audit
# against ../mathema-public, add the tetrionlabs remote, and push.
set -euo pipefail

REF="${1:?usage: make_public_export.sh <tag|committish> /path/to/export-dir}"
DEST="${2:?usage: make_public_export.sh <tag|committish> /path/to/export-dir}"

if [ -e "$DEST" ]; then
  echo "refusing to overwrite existing $DEST" >&2
  exit 1
fi

git rev-parse --verify "$REF^{commit}" >/dev/null

# A release export is taken from a TAG and carries that tag forward. A
# seed (the one-time birth of the published repository, taken from
# main before any release exists) is not a tag and carries none.
if git rev-parse --verify --quiet "refs/tags/$REF" >/dev/null; then
  IS_TAG=yes
else
  IS_TAG=no
fi

# The version the exported tree declares, which names the commit
# whether or not a tag is involved.
VERSION=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' mathema/__init__.py)
[ -n "$VERSION" ] || { echo "could not read __version__" >&2; exit 1; }

mkdir -p "$DEST"
git archive --format=tar "$REF" | tar -x -C "$DEST"

cd "$DEST"

# Belt-and-braces: nothing private-shaped in the export. These names
# should never be tracked in the dev repo in the first place; a hit
# here means stop and investigate, not delete and continue.
for needle in "code-docs-checklist" ".smd"; do
  if [ -e "$needle" ] || find . -name "$needle" -print -quit | grep -q .; then
    echo "export contains private-shaped path: $needle" >&2
    exit 1
  fi
done

git init -q -b main
git add -A
git commit -q -m "mathema $VERSION"
# Annotated, with a message: a lightweight tag fails outright when the
# operator has tag.forceSignAnnotated set, and `set -e` would abort
# here leaving a half-built export whose verification never ran.
if [ "$IS_TAG" = yes ]; then
  git tag -a "$REF" -m "mathema $VERSION"
fi

COUNT=$(git log --oneline | wc -l | tr -d ' ')
if [ "$IS_TAG" = yes ]; then
  echo "export at $DEST: $COUNT commit (must be 1), tagged $REF"
else
  echo "export at $DEST: $COUNT commit (must be 1), seed from $REF, untagged"
fi
[ "$COUNT" = "1" ]
