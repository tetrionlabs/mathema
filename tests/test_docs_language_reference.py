# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The site imports the mathema-language reference when its docs are
present and builds unchanged when they are not: the hook finds the
docs at `$MATHEMA_LANGUAGE_DOCS`, prefixes every page with
`language/reference/`, adds the package's nav after "Language domains",
and serves the pages from where they are, so nothing is copied into
`docs/` for this repository's docs runner to find."""
import importlib.util
import pathlib

import pytest

pytest.importorskip("mkdocs")

_PATH = pathlib.Path(__file__).resolve().parents[1] / "docs_hooks" / "language_reference.py"
_spec = importlib.util.spec_from_file_location("language_reference_hook", _PATH)
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


@pytest.fixture
def package_docs(tmp_path, monkeypatch):
    (tmp_path / "reference.yml").write_text(
        "nav:\n  - Languages: index.md\n  - Adaptors:\n      - Writing one: adaptors.md\n")
    (tmp_path / "index.md").write_text("# Languages\n")
    (tmp_path / "adaptors.md").write_text("# Writing an adaptor\n")
    monkeypatch.setenv(hook.ENV, str(tmp_path))
    return tmp_path


def _nav():
    return [{"Home": "index.md"},
            {"Writing claims": [{"The claim grammar": "grammar.md"},
                                {"Language domains": "language.md"},
                                {"Lemmas": "lemmas.md"}]}]


def test_absent_docs_leave_the_site_alone(tmp_path, monkeypatch):
    monkeypatch.setenv(hook.ENV, str(tmp_path / "nowhere"))
    assert hook.source() is None
    config = {"nav": _nav()}
    assert hook.on_config(config)["nav"] == _nav()
    assert hook.on_files([], config) == []


def test_the_nav_goes_after_language_domains_prefixed(package_docs):
    config = hook.on_config({"nav": _nav()})
    (section,) = [s for s in config["nav"] if "Writing claims" in s]
    assert section["Writing claims"][2] == {"Language reference": [
        {"Languages": "language/reference/index.md"},
        {"Adaptors": [{"Writing one": "language/reference/adaptors.md"}]},
    ]}
    assert section["Writing claims"][3] == {"Lemmas": "lemmas.md"}


def test_every_page_is_served_from_the_package_docs(package_docs):
    from mkdocs.config.defaults import MkDocsConfig
    config = MkDocsConfig()
    config.load_dict({"site_name": "t", "docs_dir": str(package_docs),
                      "site_dir": str(package_docs / "site")})
    config.validate()
    config.plugins._current_plugin = "language_reference"  # set by mkdocs while a hook runs
    files = hook.on_files([], config)
    assert sorted(f.src_uri for f in files) == ["language/reference/adaptors.md",
                                               "language/reference/index.md"]
    assert all(pathlib.Path(f.abs_src_path).parent == package_docs for f in files)


def test_the_repository_ignores_the_imported_docs():
    ignore = (_PATH.parents[1] / ".gitignore").read_text()
    assert "_external/" in ignore.splitlines()
