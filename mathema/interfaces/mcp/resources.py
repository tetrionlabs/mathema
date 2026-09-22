# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The reference material the MCP server serves as resources, and the
procedures it serves as prompts.

A tool answers a question the agent already knew to ask. A resource is
what it reads when it does not, and a prompt is a procedure put in
front of it at the moment it chooses what to do, which is the one
place a method actually lands, rather than in a document read twenty
minutes earlier.

Everything here is generated from what core already owns (the claim
lexicon, the reason-code table, the verdict fold), so nothing crosses
a licence boundary and nothing can drift from the code it describes:
if a spelling or a code changes, the resource changes with it.

Same wall as the tools: nothing here accepts a verdict, and nothing
here accepts evidence on a human's behalf.
"""
from __future__ import annotations


def grammar_reference() -> str:
    """The claim language by example, straight from the lexicon."""
    from mathema.lexicon import LEXICON

    lines = ["# The claim grammar, by example", "",
             "Every spelling mathema accepts, rendered from its own",
             "lexicon, so this can never drift from what parses.", ""]
    for name, example in sorted(LEXICON.items()):
        lines.append(f"- `{name}`: {example}")
    return "\n".join(lines)


def reason_code_reference() -> str:
    """Why a function is underivable, and what would unlock it."""
    from mathema.reason_codes import CODE_IDS, CODE_TABLE

    lines = ["# Reason codes", "",
             "Why a function did not lift, and whose move it is.",
             "`actionable` means the code or the claim can change to",
             "unlock the derive route; `limitation` means the construct",
             "is fine and the derive route does not reach it yet (a",
             "probe claim still adjudicates); `N/A` means the derive",
             "route fundamentally does not apply. Nothing here is a",
             "failure: a probe-route claim adjudicates regardless.", "",
             "| id | code | unlock | meaning | hint |",
             "|---|---|---|---|---|"]
    for code, entry in CODE_TABLE.items():
        lines.append(f"| {CODE_IDS.get(code, '')} | `{code}` | "
                     f"{entry['derive_unlock']} | {entry['meaning']} | "
                     f"{entry['hint']} |")
    return "\n".join(lines)


def verdict_reference() -> str:
    """How to read a verdict, and the trap in reading it wrongly."""
    return """# Verdicts, stances, and what each one licenses

`stance` is the closed four-value fold to branch on. `verdict` is the
open string beside it, kept verbatim for fidelity, with a colon
marking a subroute (`derive:extensive`, `probe:lifted_numeric`,
`skipped:unknown_but_accepted`).

| stance | verdicts | what it means |
|---|---|---|
| `supported` | proven, holds | evidence stands: proven is symbolic, holds is empirical |
| `refuted` | falsified, invalidated | a counterexample was executed against the real function |
| `blocked` | skipped, unliftable | adjudication could not engage at all |
| `undecided` | unknown, everything else | it was attempted and did not settle |

**`skipped` is not `falsified`.** A skipped claim is a gap in
mathema's own evidence, not a fact about your code; a falsified one
carries a counterexample that replays on every re-adjudication. Read
the two differently: the first asks you to state the claim better, the
second says the code or the claim is wrong.

**`passed` can be true beside a refuted row.** That happens exactly
when the row is a suggestion mathema volunteered (`gates` false): a
falsified suggestion is information, not a failure. Check `gates`
before treating any row as a gate result.

**Proof is not the goal; evidence is.** A probe claim on a function
that will never lift symbolically is worth writing, and `derivable:
no` never means "do not claim this".

Accepting evidence, owning a risk, or recording a discovery is a human
act, done in the CLI. No tool here will do it for you, and the right
move on a falsification you cannot resolve is to leave it and say so.
"""


#: URI -> (zero-argument builder, mime type). A static resource URI
#: must decorate a zero-arg function; a `{param}` URI would make it a
#: template instead.
RESOURCES: dict = {
    "mathema://reference/grammar": (grammar_reference, "text/markdown"),
    "mathema://reference/codes": (reason_code_reference, "text/markdown"),
    "mathema://reference/verdicts": (verdict_reference, "text/markdown"),
}


def claim_this_function(target: str, root: str = ".") -> str:
    """Intent:
        The authoring procedure, bound to a real function; its
        signature and its current claim state resolved into the text,
        so the agent is choosing what to claim rather than working out
        how to start.
    """
    from mathema.interfaces.mcp import tools
    # a prompt must always render: a target that does not resolve is a
    # typo to be told about, not an exception to raise at an agent
    try:
        fns = tools.resolve_target(target, root).get("functions") or []
    except Exception as e:
        return (f"`{target}` does not resolve ({type(e).__name__}). Check "
                f"the spelling with `resolve_target`, or list what is "
                f"there with `audit_targets`.")
    sig = fns[0]["signature"] if fns else "(unresolved)"
    key = fns[0]["key"] if fns else target
    try:
        suggested = tools.suggest_claims(key, root) if fns else {"rows": []}
    except Exception:
        suggested = {"rows": []}
    lines = [
        f"Write claims for `{key}{sig}`.", "",
        "1. Read the function first; `audit_targets` gives you a "
        "`span`, a ready-made `sed -n` range, so read exactly it "
        "rather than the whole file.",
        "2. Lint each statement with `parse_claim(statement, "
        f"target=\"{key}\")` before adjudicating. Passing the target "
        "checks the parameter names and arity against the real "
        "signature, which is the mistake that otherwise costs a full "
        "adjudication to discover.",
        "3. Adjudicate with `adjudicate_target`. It returns your DECLARED "
        "claims by default; pass `include=\"suggested\"` to see "
        "candidates, or `include=\"all\"` for both.",
        "4. Claim the surface that carries risk, not the surface that "
        "is easy to prove. A pure scalar helper proves quickly and "
        "tells you little; the function with branches and domain "
        "edges is the one worth evidencing. `claims_vs_floor` and the "
        "`underclaimed` filter show which is which.",
        "5. A falsification is a finding, not a failure to hide. "
        "Record what it shows and leave the judgement to a human, "
        "there is no accept tool, deliberately.", "",
    ]
    if suggested.get("rows"):
        lines.append("mathema's own candidates for this function "
                     "(declares, never verifies):")
        for row in suggested["rows"][:8]:
            mark = "  [already declared]" if row[3] else ""
            lines.append(f"  - {row[0]}: {row[1]}{mark}")
    else:
        lines.append("mathema proposes no candidates here, state what "
                     "the function is FOR, in its own terms.")
    return "\n".join(lines)


def triage_repository(targets: str, root: str = ".") -> str:
    """Intent:
        Where to start on an unfamiliar codebase: orient, then narrow
        to what is both risky and unevidenced.
    """
    return f"""Triage `{targets}` before changing anything.

1. `audit_targets(["{targets}"])` for the population. The default
   columns are the triage set; add `blocker_hint` when you want the
   remedy in the row rather than a second lookup.
2. `filter="underclaimed"` is the "what have I not evidenced" query,
   functions carrying fewer claims than their own structural floor.
   An aggregate can look healthy while exactly the risky functions are
   the bare ones.
3. `filter="actionable"` finds functions where the derive route is one
   declared domain away. `limitation` rows are not broken, a probe
   claim adjudicates there regardless, so do not skip them.
4. `project_index` maps intent at system, module and function level,
   with a `span` per function. Read by span, never by search.
5. `verify_project` tells you what the store already knows and what a
   human still owes (`keys`, and the pending queue).

Report what is unevidenced and risky. Do not accept anything: that is
a human act in the CLI."""


def diagnose_falsification(target: str, claim: str, root: str = ".") -> str:
    """Intent:
        What to do with a claim that came back refuted, the fork
        that decides whether the code or the claim was wrong.
    """
    return f"""`{claim}` on `{target}` came back refuted. Diagnose it
before changing anything.

The counterexample is an executed witness against the real function,
so one of exactly two things is true:

- **The code is wrong.** Then fix the code. The counterexample replays
  on every re-adjudication until the claim proves, so it cannot be
  waved through, which is the point.
- **The claim was wrong.** The function's actual behaviour is the
  interesting fact. Write the claim that WOULD hold and state it
  alongside, rather than deleting the one that failed.

Decide which by reading the function at its `span` and asking what it
is for. On pre-existing code the prior favours the claim being wrong;
on code you just wrote, it favours the code.

`describe_target` gives the fuller view, and `reason_code` explains
any blocker in the payload.

What you must NOT do is record a verdict. Accepting a falsification as
a discovery is a human decision made in the CLI (`mathema accept ...
--as discovery`); there is deliberately no tool for it here. Leave the
claim falsified, say what you found, and hand it over."""


#: Name -> builder. A prompt returns the message text; the server
#: wraps it into the SDK's role/content shape.
PROMPTS: dict = {
    "claim_this_function": claim_this_function,
    "triage_repository": triage_repository,
    "diagnose_falsification": diagnose_falsification,
}
