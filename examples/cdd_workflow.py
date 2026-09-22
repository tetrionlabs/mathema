# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Claim-driven development, end to end, with a mocked LLM.

Run:  python examples/cdd_workflow.py

The workflow this demonstrates:

  1. A human states an intent.
  2. A (mocked) LLM generates an implementation. Version one has a subtle,
     realistic bug: it seeds the running average at zero.
  3. The human states claims the simple way: plain law strings.
  4. A (mocked) AI proposes further claims; the verifier, never the model,
     adjudicates every one.
  5. Falsifications catch the bug; the counterexamples go back into the
     (mocked) regeneration prompt; version two passes.
  6. The accepted version is recorded; the two versions are provably not
     the same function, and the record says why the second one is right.

Every LLM response here is a hard-coded mock, so the example is
deterministic, offline, and honest about which parts are machine judgment
(the verifier) and which are machine suggestion (the model).
"""
import os
import importlib.util

import mathema
from mathema.claims import claim, check

HERE = os.path.dirname(__file__)
GEN_DIR = os.path.join(HERE, "walkthrough")

INTENT = "Exponentially weighted moving average of a series."

# ---------------------------------------------------------------------------
# Step 2: the mocked LLM writes code. V1 contains the classic seeding bug.
# ---------------------------------------------------------------------------
MOCK_LLM_V1 = '''\
def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average of a series."""
    y = 0.0
    for v in x:
        y = alpha * v + (1 - alpha) * y
    return y
'''

MOCK_LLM_V2 = '''\
def ema(x: list, alpha: float) -> float:
    """Exponentially weighted moving average of a series."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y
'''

# ---------------------------------------------------------------------------
# Step 4: the mocked AI proposes claims, exactly as it might propose test
# cases, except these are laws that link back to the CDD spec (symmetry,
# order, and compositional families) and the verifier adjudicates them.
# ---------------------------------------------------------------------------
MOCK_AI_CLAIMS = [
    # a two-element sequence unrolls exactly: list literals and the auxiliary
    # scalars a, b are all part of the claim language
    claim("f([a, b], alpha) == alpha*b + (1 - alpha)*a",
          name="two_step_unrolling", source="ai"),
    claim("f(x, 1.0) == x[-1]", name="alpha_one_is_last", source="ai"),
    claim("f(x, alpha) <= max(x)", name="upper_bound", source="ai"),
]

HUMAN_CLAIMS = [
    "min(x) <= f(x, alpha)",          # stays inside the data (lower)
    "f(x, alpha) == f(x, alpha)",     # trivially: deterministic
]


def load_generated(source: str, version: str):
    """Write the mock LLM's output to a real file and import it, so the
    analyzer can see genuine source."""
    path = os.path.join(GEN_DIR, f"generated_ema_{version}.py")
    os.makedirs(GEN_DIR, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(source)
    spec = importlib.util.spec_from_file_location(f"generated_{version}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ema


def adjudicate(fn, label: str):
    results = check(fn, HUMAN_CLAIMS + MOCK_AI_CLAIMS,
                    domain={"alpha": (0.0, 1.0)})
    print(f"\n── adjudication: {label}")
    for p in results:
        mark = {"holds": "✓", "falsified": "✗", "skipped": "–"}[p.verdict]
        line = f"  {mark} {p.verdict:9} {p.name}: {p.statement}"
        if p.counterexample:
            line += f"\n      counterexample {p.counterexample}"
        print(line)
    return results


if __name__ == "__main__":
    print(f"INTENT: {INTENT}")

    ema_v1 = load_generated(MOCK_LLM_V1, "v1")
    r1 = adjudicate(ema_v1, "version 1 (mock LLM output)")
    falsified = [p for p in r1 if p.verdict == "falsified"]
    print(f"\n{len(falsified)} claim(s) falsified: the counterexamples go back "
          "into the regeneration prompt.")

    ema_v2 = load_generated(MOCK_LLM_V2, "v2")
    r2 = adjudicate(ema_v2, "version 2 (mock LLM regeneration)")
    assert not [p for p in r2 if p.verdict == "falsified"]
    print("\nAll claims hold. Accept version 2.")

    form1 = mathema.analyze(ema_v1).form
    form2 = mathema.analyze(ema_v2).form
    print(f"\nform hash v1: {form1}\nform hash v2: {form2}")
    print("different: the seeding fix is a real behavioral change, not a rename.")

    accepted = mathema.write_spec(ema_v2, claims=HUMAN_CLAIMS + MOCK_AI_CLAIMS,
                            key="pricing.ema", root=GEN_DIR,
                            domain={"alpha": (0.0, 1.0)})
    print(f"\nRecorded the accepted version: {os.path.relpath(accepted.spec_path)}")
