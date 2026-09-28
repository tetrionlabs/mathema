# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An mkdocs hook that imports the mathema-language package's reference
into this site under `/language/reference/`.

The language docs are behind a flag until the package is published:
`extra.language_docs` in `mkdocs.yml`, overridden by
`$MATHEMA_LANGUAGE_DOCS_ENABLED`. While it is off, nothing is imported
and the "Language domains" page leaves the nav (it is still built, so
links to it resolve).

The package owns its reference (the languages, the hazards, the row
adaptors, the catalogue) in its own `docs/`, tested by its own suite.
When those docs are present at build time, at `$MATHEMA_LANGUAGE_DOCS`
or else at `_external/mathema-language/docs` beside this repository's
`mkdocs.yml`, every page there is added to the site under
`language/reference/`. When the package's `reference.yml` names a
`section`, that becomes a top-level section of this site's nav after
"Writing claims", holding the "Language domains" page and then the
package's nav; otherwise the package's nav is added inside "Writing
claims" after "Language domains". When the docs are absent the
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
FLAG = "MATHEMA_LANGUAGE_DOCS_ENABLED"
DEFAULT = pathlib.Path(__file__).resolve().parents[1] / "_external" / "mathema-language" / "docs"
SECTION, AFTER, TITLE = "Writing claims", "Language domains", "Language reference"


def enabled(config) -> bool:
    """Whether the language docs are shown: `$MATHEMA_LANGUAGE_DOCS_ENABLED`
    when set (`1` shows them, `0` or empty hides them), else the site's
    `extra.language_docs`, off when absent."""
    flag = os.environ.get(FLAG)
    if flag is not None:
        return flag.strip().lower() not in ("", "0", "false", "no")
    return bool((config.get("extra") or {}).get("language_docs", False))


def hide_core_page(nav: list) -> list:
    """`nav` without the `AFTER` page in `SECTION`; the page is still
    built, so links to it keep working."""
    for section in nav:
        if isinstance(section, dict) and SECTION in section:
            section[SECTION] = [item for item in section[SECTION]
                                if not (isinstance(item, dict) and AFTER in item)]
    return nav


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


def own_section(nav: list, title: str, reference: list) -> list:
    """`nav` with a top-level section `title` after `SECTION`, holding
    the `AFTER` page (moved out of `SECTION`) and then `reference`."""
    moved: list = []
    at = len(nav)
    for i, section in enumerate(nav):
        if isinstance(section, dict) and SECTION in section:
            items = section[SECTION]
            moved = [item for item in items if isinstance(item, dict) and AFTER in item]
            section[SECTION] = [item for item in items if item not in moved]
            at = i + 1
    nav.insert(at, {title: [*moved, *reference]})
    return nav


def on_config(config):
    if not enabled(config):
        if config.get("nav"):
            hide_core_page(config["nav"])
        return config
    found = source()
    if found is not None and config.get("nav"):
        loaded = yaml.safe_load((found / "reference.yml").read_text(encoding="utf-8"))
        reference = prefixed(loaded["nav"])
        if loaded.get("section"):
            own_section(config["nav"], loaded["section"], reference)
        else:
            insert_reference(config["nav"], reference)
    return config


def on_files(files, config):
    found = source() if enabled(config) else None
    if found is None:
        return files
    for page in sorted(found.glob("*.md")):
        files.append(File.generated(config, f"{PREFIX}/{page.name}", abs_src_path=str(page)))
    return files
