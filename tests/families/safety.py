# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The safety family: `is_state_safe` and `is_deterministic`, their
negations, writes in reachable and unreachable branches, and rows
searched for a value the function copied."""

F = "tests.families.functions.safety"
UNREACHABLE = "the unreachable code reading"
NEGATION = "the negation reading"
SHOWN = "the shown change"
SAFE = "is_state_safe(f)"
UNSAFE = "not is_state_safe(f)"

CASES: list = []


def pair(name, fn, domain, writes, shows, rule_pos=None, rule_neg=None, issue=None):
    """The positive claim and its negation over one domain: `writes`
    says whether some point of the domain writes."""
    for tag, body, truth, rule in (("safe", SAFE, not writes, rule_pos),
                                   ("unsafe", UNSAFE, writes, rule_neg)):
        case = dict(name=f"{name}.{tag}", function=f"{F}:{fn}",
                    claim=f"for x in {domain}, {body}", truth=truth, shows=shows)
        if rule:
            case.update(rule=rule, issue=issue)
        CASES.append(case)


pair("always", "appends", "[0, 1]", True, "an unconditional append")
pair("counter", "counts", "[0, 1]", True, "a global counter")
pair("pure", "pure", "[0, 1]", False, "no write at all")
pair("above_ten", "appends_above_ten", "[0, 1]", False,
     "the write sits under x > 10, which no point of [0, 1] reaches",
     rule_pos=UNREACHABLE, rule_neg=NEGATION, issue=127)
pair("if_false", "appends_never", "[0, 1]", False, "the write sits under `if False:`",
     rule_pos=UNREACHABLE, rule_neg=NEGATION, issue=127)
pair("above_ten_reached", "appends_above_ten", "[0, 20]", True, "x > 10 is reached in [0, 20]")
pair("above_half", "appends_above_half", "[0, 1]", True, "x > 0.5 is reached")
pair("rebound", "appends_after_rebinding", "[0, 1]", True,
     "the parameter is rebound to x + 100 before the test")
pair("loop_target", "appends_in_loop_target", "[0, 1]", True,
     "a loop target of the same name holds 100 at the test")
pair("inner_function", "appends_in_inner_function", "[0, 1]", True,
     "an inner function's parameter of the same name holds x + 100")
pair("xor", "appends_under_xor", "{0, 1}", True, "`^` is exclusive or: 1 ^ 12 is 13")
pair("float_rounding", "appends_under_float_rounding", "[0, 1.2]", True,
     "(1.2 + 1e16) - 1e16 is 2.0 in floats")
pair("write_then_raise", "appends_then_raises", "[0, 1]", True, "the append runs before the raise")
pair("integers", "appends", "Z", True, "an unconditional append over Z")
pair("finite_set", "appends_above_half", "{0, 1}", True, "the write runs at the member 1")
pair("last_member", "appends_at_last_member", "{" + ", ".join(str(k) for k in range(100)) + "}",
     True, "only the last listed member writes")
for name, fn in (("deque", "appends_to_deque"), ("ordered_dict", "sets_ordered_item"),
                 ("decimal", "binds_decimal"), ("cycle", "appends_to_cycle"),
                 ("nested", "writes_nested")):
    pair(f"held.{name}", fn, "[0, 1]", True,
         "a module-level value of a type whose state is not in its __dict__, or that holds itself, "
         "or reached through an index")

for tag, body in (("safe", SAFE), ("unsafe", UNSAFE)):
    # whether writing back an equal value is a change is not settled, so no truth is stated
    CASES.append(dict(name=f"value_back.{tag}", function=f"{F}:writes_value_back",
                      claim=f"for x in [0, 1], {body}", shows="a value is written back unchanged"))

for name, fn, truth, shows in (
        ("pure", "pure", True, "the same result each call"),
        ("draws", "draws", False, "each call draws from a module-level generator")):
    CASES.append(dict(name=f"repeat.{name}", function=f"{F}:{fn}",
                      claim="for x in [0, 1], is_deterministic(f)", truth=truth, shows=shows))
    CASES.append(dict(name=f"repeat.{name}.not", function=f"{F}:{fn}",
                      claim="for x in [0, 1], not is_deterministic(f)", truth=not truth, shows=shows))

for name in ("copies_mark_to_name", "copies_mark_to_list", "copies_mark_to_dict",
             "copies_mark_to_attribute", "makes_mark_named_object"):
    CASES.append(dict(name=f"marker.{name}", function=f"{F}:{name}",
                      claim="for x in [0, 1], " + UNSAFE, truth=True, marker=True,
                      shows="the row may say that the value changed, never what it holds"))
for name in ("returns_mark_with_draw", "returns_mark_named_object"):
    CASES.append(dict(name=f"marker.{name}", function=f"{F}:{name}",
                      claim="for x in [0, 1], not is_deterministic(f)", truth=True, marker=True,
                      shows="the row may say that two results differ, never what they hold"))
