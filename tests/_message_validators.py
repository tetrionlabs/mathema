# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Refusing validators whose exception message reads a module-level
constant, for the tests of what the validator reader reads in a
message."""
import re

SLUG = re.compile(r"[a-c][a-c-]{0,3}\Z")
SETTING = "record format"
NOT_TEXT = 3


class FormatError(ValueError):
    pass


def check_name(name):
    if not SLUG.match(name):
        raise ValueError(f"{SETTING} is lower-case letters and hyphens: {name!r}")
    return name


def check_name_own_error(name):
    if not SLUG.match(name or ''):
        raise FormatError(f"{SETTING!r} is lower-case: {name!r}")
    return name


def check_name_calling(name):
    if not SLUG.match(name):
        raise ValueError(f"{SETTING.upper()} is lower-case: {name!r}")
    return name


def check_name_formatting(name):
    if not SLUG.match(name):
        raise ValueError(f"{SETTING:>20} is lower-case: {name!r}")
    return name


def check_name_not_text(name):
    if not SLUG.match(name):
        raise ValueError(f"{NOT_TEXT} is lower-case: {name!r}")
    return name
