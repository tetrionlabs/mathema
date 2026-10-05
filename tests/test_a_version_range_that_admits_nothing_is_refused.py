# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A compendium file's `versions:` range whose upper bound is at or
below its lower bound (`">=6,<5"`) admits no release, so every row in it
would silently never apply; the file is refused with the reason, like
any range that does not read."""
import pytest

from mathema.spec import ClaimsFileError, validate_claims_file


def _file(versions):
    return {"compendium": "yaml", "versions": versions,
            "yaml.safe_dump": {"claims": [{"name": "d",
                                           "statement": "is_defined(f)"}]}}


@pytest.mark.parametrize("versions", [">=6,<5", ">=2.4,<2.4", "<0"])
def test_an_empty_range_is_refused(versions):
    with pytest.raises(ClaimsFileError, match="admits no version"):
        validate_claims_file(_file(versions), "claims/yaml.claims.yaml")


@pytest.mark.parametrize("versions", [">=6,<7", ">=2.4", "<3", "*",
                                      ">=1.24,<3"])
def test_a_range_with_room_is_accepted(versions):
    validate_claims_file(_file(versions), "claims/yaml.claims.yaml")
