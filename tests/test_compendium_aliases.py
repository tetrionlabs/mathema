# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A compendium file's `aliases:` names the library by other names: a
distribution name for the installed-version lookup (`PyYAML` for
`compendium: yaml`), and a prefix a key may be written under (`np.cbrt`
for `numpy.cbrt`)."""
import textwrap

import pytest


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_yaml_compendium_with_its_distribution_alias_loads(tmp_path):
    from mathema.compendium import load_library_claims
    _write(tmp_path / "claims" / "yaml.claims.yaml", """
        compendium: yaml
        aliases: [PyYAML]
        versions: ">=5"
        yaml.safe_load:
          claims:
            - name: is_defined
              statement: "is_defined(f)"
    """)
    claims = load_library_claims(str(tmp_path))
    assert "yaml.safe_load" in claims
    assert claims["yaml.safe_load"]["compendium"] == "yaml"


def test_the_version_lookup_tries_each_alias():
    from mathema.compendium import _installed_version
    assert _installed_version("no_such_import_name_xyz") is None
    assert _installed_version("no_such_import_name_xyz",
                              ("also_missing_xyz", "PyYAML")) is not None


def test_two_aliases_and_a_key_spelled_under_either(tmp_path):
    from mathema.compendium import load_library_claims
    _write(tmp_path / "claims" / "yaml.claims.yaml", """
        compendium: yaml
        aliases: [PyYAML, pyyaml]
        PyYAML.safe_load:
          claims:
            - name: is_defined
              statement: "is_defined(f)"
        pyyaml.safe_dump:
          claims:
            - name: is_defined
              statement: "is_defined(f)"
    """)
    claims = load_library_claims(str(tmp_path))
    assert {"yaml.safe_load", "yaml.safe_dump"} <= set(claims)
    assert "PyYAML.safe_load" not in claims


def test_a_key_under_an_alias_prefix_matches_a_caller(tmp_path):
    pytest.importorskip("numpy")
    from mathema.analysis import analyze_source
    from mathema.compendium import (library_key_of, library_keys_called,
                                    load_library_claims, uninstall)
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        aliases: [np]
        np.cbrt:
          claims:
            - name: is_defined
              statement: "is_defined(f)"
    """)
    caller = _load(tmp_path, '''
        import numpy as np

        def root3(x: float) -> float:
            """Cube root through numpy."""
            return float(np.cbrt(x))
    ''', "alias_caller").root3
    claims = load_library_claims(str(tmp_path))
    assert "numpy.cbrt" in claims
    assert "numpy.cbrt" in library_keys_called(
        caller, analyze_source(caller), library_claims=claims)
    from mathema.compendium import install
    import numpy as np
    try:
        install(str(tmp_path))
        assert library_key_of(np.cbrt) == "numpy.cbrt"
    finally:
        uninstall()


@pytest.mark.parametrize("aliases, problem", [
    ("PyYAML", "list"),
    ("[PyYAML, '']", "list"),
    ("[Py YAML]", "list"),
])
def test_validation_refuses_a_malformed_alias_list(tmp_path, aliases, problem):
    import yaml

    from mathema.spec import ClaimsFileError, validate_claims_file
    data = yaml.safe_load(f"compendium: yaml\naliases: {aliases}\n")
    with pytest.raises(ClaimsFileError, match="aliases"):
        validate_claims_file(data, "yaml.claims.yaml")


def test_aliases_need_a_compendium():
    from mathema.spec import ClaimsFileError, validate_claims_file
    with pytest.raises(ClaimsFileError, match="aliases"):
        validate_claims_file({"aliases": ["PyYAML"]}, "x.claims.yaml")


def test_an_alias_key_and_the_library_key_for_one_function_are_refused():
    from mathema.spec import ClaimsFileError, validate_claims_file
    data = {"compendium": "yaml", "aliases": ["PyYAML"],
            "yaml.safe_load": {"claims": []},
            "PyYAML.safe_load": {"claims": []}}
    with pytest.raises(ClaimsFileError, match="yaml.safe_load"):
        validate_claims_file(data, "yaml.claims.yaml")


def test_status_reads_the_version_through_the_files_aliases(tmp_path):
    from importlib import metadata

    from mathema.compendium.status import compendium_status
    _write(tmp_path / "claims" / "yamlish.claims.yaml", """
        compendium: yamlish
        aliases: [also_missing_xyz, PyYAML]
        yamlish.safe_load:
          claims:
            - name: is_defined
              statement: "is_defined(f)"
    """)
    (entry,) = compendium_status(str(tmp_path), "yamlish")["libraries"]
    assert entry["version"] == metadata.version("PyYAML")


def test_status_without_aliases_finds_no_version_for_an_unknown_name(tmp_path):
    from mathema.compendium.status import compendium_status
    _write(tmp_path / "claims" / "yamlish.claims.yaml", """
        compendium: yamlish
        yamlish.safe_load:
          claims:
            - name: is_defined
              statement: "is_defined(f)"
    """)
    (entry,) = compendium_status(str(tmp_path), "yamlish")["libraries"]
    assert entry["version"] is None
