# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The missing values family: None and nan written in a claim's call,
listed in its domain in every spelling, and empty inputs."""

F = "tests.families.functions.missing"
ARGUMENT = "the missing argument reading"
LISTED = "the listed missing value reading"
EMPTY = "the empty input reading"
NEGATION = "the negation reading"

CASES: list = []

# a missing value written in the call, in each spelling
for i, (fn, spelling, truth) in enumerate([
        ("none_in_band", "None", False), ("nan_in_band", "nan", False),
        ("nan_in_band", "float('nan')", False), ("nan_in_band", "inf - inf", False),
        ("none_in_band", "1", True), ("always_zero", "None", True), ("always_zero", "nan", True)]):
    CASES.append(dict(
        name=f"call.{i}.{fn}", function=f"{F}:{fn}",
        claim=f"for x in {{1}}, f({spelling}, 0.5) == 0", truth=truth,
        **({} if truth else dict(issue=124, rule=ARGUMENT)),
        shows=f"the call passes {spelling} as written; the function returns 1.0 there"
        if not truth else "the function returns 0.0 at the written value"))

CASES += [
    dict(name="call.none_true", function=f"{F}:none_in_band",
         claim="for x in {1}, f(None, 0.5) == 1", truth=True,
         shows="the call at None, 0.5 returns 1.0"),
    # a missing value listed in the domain
    dict(name="listed.none_set", function=f"{F}:none_in_band",
         claim="for x in {1, None}, y in {0.5}, f(x, y) == 0", truth=False,
         shows="None is listed for x and the function returns 1.0 there"),
    dict(name="listed.nan_set", function=f"{F}:nan_in_band",
         claim="for x in {1, nan}, y in {0.5}, f(x, y) == 0", truth=False,
         shows="nan is listed for x and the function returns 1.0 there"),
    dict(name="listed.absent_union", function=f"{F}:none_in_band",
         claim="for x in [0, 1] | absent, f(x, 0.5) == 0", truth=False, issue=124, rule=ARGUMENT,
         shows="`| absent` adds None to the domain"),
    dict(name="listed.is_defined_none", function=f"{F}:doubled",
         claim="for x in {None}, is_defined(f)", truth=False, issue=124, rule=LISTED,
         shows="x * 2.0 raises TypeError at the listed None"),
    dict(name="listed.is_defined_one_none", function=f"{F}:doubled",
         claim="for x in {1, None}, is_defined(f)", truth=False, issue=124, rule=LISTED,
         shows="x * 2.0 raises TypeError at the listed None"),
    dict(name="listed.not_is_defined_none", function=f"{F}:doubled",
         claim="for x in {None}, not is_defined(f)", truth=True, issue=124, rule=LISTED,
         shows="the listed None makes the function raise, so the negation is true"),
    dict(name="listed.is_defined_guarded", function=f"{F}:guarded_double",
         claim="for x in {1, None, nan}, is_defined(f)", truth=True,
         shows="the function returns at every listed value"),
    dict(name="listed.narrow_band", function=f"{F}:none_in_narrow_band",
         claim="for x in {1, None}, y in {0.65}, is_defined(f)", truth=False,
         shows="the function raises only at x = None with y inside (0.6, 0.7)"),
    dict(name="listed.floor_nan", function=f"{F}:floored",
         claim="for x in {1, nan}, is_defined(f)", truth=False,
         shows="floor(nan) raises ValueError"),
    # empty inputs
    dict(name="empty.union", function=f"{F}:mean_union", claim="is_empty_safe(xs)", truth=False,
         issue=128, rule=EMPTY, shows="`xs == []` lets the empty tuple through to len(xs) == 0"),
    dict(name="empty.optional", function=f"{F}:mean_optional", claim="is_empty_safe(xs)",
         truth=False, issue=128, rule=EMPTY, shows="an optional sequence admits the empty tuple"),
    dict(name="empty.list_or_text", function=f"{F}:mean_list_or_text", claim="is_empty_safe(xs)",
         truth=False, issue=128, rule=EMPTY, shows="the union admits the empty text"),
    dict(name="empty.list_or_range", function=f"{F}:mean_list_or_range", claim="is_empty_safe(xs)",
         truth=False, issue=128, rule=EMPTY, shows="the union admits range(0)"),
    dict(name="empty.union_not", function=f"{F}:mean_union_not", claim="is_empty_safe(xs)",
         truth=True, shows="`not xs` treats every empty input alike"),
    dict(name="empty.list", function=f"{F}:mean_list", claim="is_empty_safe(xs)", truth=True,
         shows="a list parameter admits one empty input"),
    dict(name="empty.unannotated", function=f"{F}:mean_unannotated", claim="is_empty_safe(xs)",
         truth=False, rule=EMPTY, shows="an unannotated parameter admits the empty tuple"),
]
