# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Validators of one text, checked over languages whose definitions a
proof assumes. `serve_languages` registers the languages of
`tests/_text_validators.py` for the length of a check and returns the
function that removes them."""
import re
import sys
from pathlib import Path

SLUG = re.compile(r"[a-c][a-c-]{0,3}\Z")
PERSON = re.compile(r"p:[0-9]{2}")


def serve_languages():
    tests = str(Path(__file__).resolve().parents[2])
    if tests not in sys.path:
        sys.path.append(tests)
    import _text_validators
    _text_validators.serve()
    return _text_validators.unserve


def check_slug(text):
    if not SLUG.match(text):
        raise ValueError(text)
    return text


def is_person(actor):
    return PERSON.fullmatch(actor) is not None


def same(text):
    return text


def shout(text):
    return text.upper()
