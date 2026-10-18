# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A docstring's `Intent:` block is the function's recorded intent
whenever one is present, through `analyze` and into the record `check`
produces; the summary line stands in only when there is no block, and
a docstring with neither records no intent. The same holds for a
documentation-only record, built for a callable with no Python
source."""
import mathema


def implied_vol(price, spot, strike, t, r):
    """Intent:
        The volatility at which bs_call reproduces price. Never
        negative; zero at or below intrinsic.
    """
    return 0.0


def summary_only(x):
    """Twice x, always."""
    return 2 * x


def ema(x: list[float], alpha: float) -> float:
    """Exponentially weighted moving average.

    Intent:
        Blends each new value with the running mean.
    """
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def undocumented(x):
    return x


_BLOCK_TEXT = ("The volatility at which bs_call reproduces price. Never "
               "negative; zero at or below intrinsic.")
_EMA_BLOCK = "Blends each new value with the running mean."

_EMA_SOURCE = '''
def ema(x, alpha):
    """Exponentially weighted moving average.

    Intent:
        Blends each new value with the running mean.
    """
    return 0.0
'''


def _without_source(text: str):
    """Intent:
        The function `text` defines, built by `exec` so that it has no
        retrievable source and `analyze` falls back to a
        documentation-only record.
    """
    ns: dict = {}
    exec(text, ns)
    return ns["ema"]


def test_an_intent_block_alone_is_the_functions_intent():
    facts = mathema.analyze(implied_vol)
    assert facts.doc_intent == _BLOCK_TEXT
    assert facts.doc_intent_source == "documented"


def test_an_intent_block_alone_reaches_the_record():
    spec = mathema.check(implied_vol, claims=[]).to_spec()
    assert spec["intent"] == _BLOCK_TEXT


def test_a_summary_line_without_a_block_stays_the_intent():
    facts = mathema.analyze(summary_only)
    assert facts.doc_intent == "Twice x, always."
    assert facts.doc_intent_source == "declared"


def test_the_block_wins_over_a_summary_line():
    facts = mathema.analyze(ema)
    assert facts.doc_intent == _EMA_BLOCK
    assert facts.doc_intent_source == "documented"


def test_the_block_over_a_summary_line_reaches_the_record():
    spec = mathema.check(ema, claims=[]).to_spec()
    assert spec["intent"] == _EMA_BLOCK
    intent_steps = [s for s in spec["reasoning"] if s["step"] == "intent"]
    assert [s["claim"] for s in intent_steps] == [_EMA_BLOCK]


def test_a_docstring_with_neither_records_no_intent():
    facts = mathema.analyze(undocumented)
    assert facts.doc_intent is None
    assert facts.doc_intent_source is None
    assert mathema.check(undocumented, claims=[]).to_spec()["intent"] is None


def test_the_block_wins_in_a_documentation_only_record():
    facts = mathema.analyze(_without_source(_EMA_SOURCE))
    assert facts.tier == 0
    assert facts.doc_intent == _EMA_BLOCK
