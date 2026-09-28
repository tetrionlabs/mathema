# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`str(...)` is claim syntax on the probe route, so a round trip
through a parser that returns an object reads as written
(`str(parse(text)) == normalise(text)`). The derive route has no
reading of it and declines rather than treating it as an unknown
function."""
import uuid

from mathema.conjecture import check_conjectures, claim


def parse_id(text: str) -> uuid.UUID:
    """The id text as a UUID."""
    return uuid.UUID(text)


def normalise_id(text: str) -> str:
    """The id as the database stores it."""
    return str(uuid.UUID(text))


IDS = '{"12345678123456781234567812345678", "{12345678-1234-5678-1234-567812345678}"}'


def test_a_round_trip_through_str_holds():
    (p,) = check_conjectures(normalise_id, [claim(
        f"for text in {IDS}, normalise_id(text) == str(parse_id(text))")])
    assert p.verdict in ("proven", "holds"), p.note


def test_a_false_claim_through_str_is_falsified():
    (p,) = check_conjectures(normalise_id, [claim(
        f"for text in {IDS}, str(parse_id(text)) == text")])
    assert p.verdict == "falsified", p.note


def test_the_derive_route_declines_str():
    (p,) = check_conjectures(normalise_id, [claim(
        f"for text in {IDS}, normalise_id(text) == str(parse_id(text))", route="derive")])
    assert p.verdict != "proven" or "brute_force" in (p.route or ""), (p.verdict, p.route)
