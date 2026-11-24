# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One function per enforced domain: `x * 2.0` behind
`enforce_domain({"x": <domain>})`, which refuses every value outside
that domain before the body runs."""
from mathema.authoring import enforce_domain

ENFORCED = {
    "closed": "[0, 1]", "open": "(0, 1)", "closed_open": "[0, 1)", "open_closed": "(0, 1]",
    "wide": "[0, 100]", "narrow": "[0.25, 0.75]", "pair": "{0, 1}", "integers": "Z",
    "naturals": "N", "reals": "R", "to_infinity": "[0, inf]", "shifted": "[-1, 2]",
}


def _enforced(name: str, text: str):
    def body(x):
        return x * 2.0
    body.__name__ = body.__qualname__ = f"e_{name}"
    return enforce_domain({"x": text})(body)


e_closed = _enforced("closed", ENFORCED["closed"])
e_open = _enforced("open", ENFORCED["open"])
e_closed_open = _enforced("closed_open", ENFORCED["closed_open"])
e_open_closed = _enforced("open_closed", ENFORCED["open_closed"])
e_wide = _enforced("wide", ENFORCED["wide"])
e_narrow = _enforced("narrow", ENFORCED["narrow"])
e_pair = _enforced("pair", ENFORCED["pair"])
e_integers = _enforced("integers", ENFORCED["integers"])
e_naturals = _enforced("naturals", ENFORCED["naturals"])
e_reals = _enforced("reals", ENFORCED["reals"])
e_to_infinity = _enforced("to_infinity", ENFORCED["to_infinity"])
e_shifted = _enforced("shifted", ENFORCED["shifted"])


def unguarded(x):
    return x * 2.0
