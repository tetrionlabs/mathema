# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An mkdocs hook that imports the mathema-language package's reference
into this site under `/language/reference/`.

The package owns its reference (the languages, the hazards, the row
adaptors, the catalogue) in its own `docs/`, tested by its own suite.
When those docs are present at build time, at `$MATHEMA_LANGUAGE_DOCS`
or else at `_external/mathema-language/docs` beside this repository's
`mkdocs.yml`, every page there is added to the site under
`language/reference/`, and the package's `reference.yml` nav is added
to this site's nav after "Language domains". When they are absent the
site builds exactly as it would without this hook. The pages are read
from where they are, never copied into `docs/`, so this repository's
own docs runner never sees them."""
from __future__ import annotations

import os
import pathlib

import yaml
from mkdocs.structure.files import File

PREFIX = "language/reference"
ENV = "MATHEMA_LANGUAGE_DOCS"
DEFAULT = pathlib.Path(__file__).resolve().parents[1] / "_external" / "mathema-language" / "docs"
SECTION, AFTER, TITLE = "Writing claims", "Language domains", "Language reference"


def source() -> pathlib.Path | None:
    """The package's docs directory, or None when it is not present."""
    path = pathlib.Path(os.environ.get(ENV) or DEFAULT)
    return path if (path / "reference.yml").is_file() else None


def prefixed(nav: list) -> list:
    """The package's nav with every page moved under `PREFIX`."""
    out = []
    for item in nav:
        ((title, target),) = item.items()
        out.append({title: prefixed(target) if isinstance(target, list) else f"{PREFIX}/{target}"})
    return out


def insert_reference(nav: list, reference: list) -> list:
    """`nav` with the reference section added to `SECTION` after the
    `AFTER` page, or at the end of `SECTION` when that page is not in it."""
    for section in nav:
        if isinstance(section, dict) and SECTION in section:
            items = section[SECTION]
            at = next((i + 1 for i, item in enumerate(items)
                       if isinstance(item, dict) and AFTER in item), len(items))
            items.insert(at, {TITLE: reference})
    return nav


def on_config(config):
    found = source()
    if found is not None and config.get("nav"):
        reference = yaml.safe_load((found / "reference.yml").read_text(encoding="utf-8"))["nav"]
        insert_reference(config["nav"], prefixed(reference))
    return config


def on_files(files, config):
    found = source()
    if found is None:
        return files
    for page in sorted(found.glob("*.md")):
        files.append(File.generated(config, f"{PREFIX}/{page.name}", abs_src_path=str(page)))
    return files
