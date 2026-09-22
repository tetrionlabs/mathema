# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Concepts: what a function is ABOUT, as stable string tags.

Three provenances feed one vocabulary, and the distinction is never
flattened inside mathema (a consumer that only wants the union reads
the record's `meta.concepts`; the full split rides beside it under
`mathema.concept_sources`):

- ``declared``, the author's own ``Concepts:`` or ``Tags:`` marker
  (a docstring section, a module README block, or a declared file
  entry's ``meta.concepts``). Both spellings parse; everything is a
  concept internally.
- ``mechanism``, harvested from adjudication evidence: what the
  lift and the proof machinery objectively touched (a fold lift means
  summation, an nlsat proof means polynomial arithmetic, a pole found
  means a singularity). `MECHANISM_CONCEPTS` is the registry.
- ``keyword``, the summary-keyword hints `intent.parse_doc` already
  infers, the lowest rung.

Concept names are kebab tokens (lowercase, inner whitespace becomes
``-``). Once released they are STABLE identifiers, future layers
link them to policy/compliance documents and build the knowledge
graph on them, so registry values are additive-only, the same
discipline `reason_codes` follows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Concept:
    """One concept tag with its provenance (`declared` | `mechanism`
    | `keyword`); the carrier `Record.concepts` holds, whose `.name`
    the record's own "instantiates: ..." reasoning line renders."""
    name: str
    source: str

_TOKEN_SPLIT = re.compile(r"[,\n]")


def normalize_concept(raw: str) -> str | None:
    """One concept token in canonical form: stripped, lowercased,
    inner whitespace collapsed to a single hyphen. None for an empty
    or punctuation-only token."""
    token = re.sub(r"\s+", "-", raw.strip().lower()).strip("-")
    return token or None


def parse_concepts(text: str | None) -> list[str]:
    """The concept tokens of one marker body: comma- or
    newline-separated, a leading list dash tolerated, normalized and
    de-duplicated in order."""
    if not text:
        return []
    out: list[str] = []
    for piece in _TOKEN_SPLIT.split(text):
        token = normalize_concept(piece.lstrip("-* "))
        if token and token not in out:
            out.append(token)
    return out


# What each adjudication mechanism objectively touched, keyed by the
# `mathema.derive_route` value the evidence already carries. A
# colon-parameterized route matches on its head (`substitution:sqrt`
# consults _SUBSTITUTION_CONCEPTS below for the tail).
MECHANISM_CONCEPTS: dict[str, tuple[str, ...]] = {
    "gap_substitution": ("symmetry", "wlog"),
    "squared_comparison": ("radicals",),
    "loggamma_canonicalization": ("special-functions", "logarithms"),
    "smt_nlsat": ("polynomial-arithmetic",),
    "termwise_sum": ("summation",),
    "domain_split": ("case-analysis",),
    "substitution": ("change-of-variables",),
    "rewrite": ("algebraic-rewriting",),
    "widened_retry": (),
}

_SUBSTITUTION_CONCEPTS = {
    "sqrt": ("radicals",),
    "erf": ("special-functions",),
    "tanh": ("special-functions",),
    "atan": ("trigonometry",),
}

# claim-text atoms -> concepts, matched as call heads in adjudicated
# statements
_STATEMENT_CONCEPTS = (
    ("d(", "differentiation"),
    ("integrate(", "integration"),
    ("lim(", "limits"),
    ("Sum(", "summation"),
    ("Prod(", "products"),
)

# extensive-rung sketch phrases that carry no meta of their own
_SKETCH_CONCEPTS = (
    ("residue", "contour-integration"),
    ("interval refinement", "interval-arithmetic"),
    ("real-root isolation", "root-isolation"),
    ("each term of the sum", "summation"),
    ("nlsat", "polynomial-arithmetic"),
)

# domain-hazard kinds (diagnostics.domain_hazards) -> concepts
_HAZARD_CONCEPTS = {
    "pole": "singularity",
    "stationary": "critical-points",
    "inflection": "critical-points",
}

# built-in claim names whose PROVEN verdict is itself a structural
# concept
_PROVEN_CLAIM_CONCEPTS = (
    ("affine", "affine"),
    ("monotonic", "monotonicity"),
    ("convex", "convexity"),
    ("concave", "convexity"),
    ("even", "symmetry"),
    ("odd", "symmetry"),
    ("commutative", "symmetry"),
)


def mechanism_concepts(facts, probes) -> list[str]:
    """Intent:
        The mechanism-provenance concepts for one adjudicated
        function: lift shape from the structural facts, mechanism meta
        and statement atoms and sketch phrases from each probe, in
        first-seen order.
    """
    out: list[str] = []

    def add(*names):
        for n in names:
            if n and n not in out:
                out.append(n)

    for loop in getattr(facts, "loops", []) or []:
        if loop.kind == "fold":
            add("summation", "folded-sum")
        elif loop.kind in ("build", "filter-build"):
            add("iteration")
    if getattr(facts, "recursion", False):
        add("recursion")

    for p in probes or []:
        meta = getattr(p, "meta", None) or {}
        route = meta.get("mathema.derive_route")
        if route:
            head, _, tail = route.partition(":")
            add(*MECHANISM_CONCEPTS.get(head, ()))
            if head == "substitution":
                add(*_SUBSTITUTION_CONCEPTS.get(tail, ()))
        statement = getattr(p, "statement", "") or ""
        for atom, concept in _STATEMENT_CONCEPTS:
            if atom in statement:
                add(concept)
        sketch = (getattr(p, "sketch", "") or "")
        for phrase, concept in _SKETCH_CONCEPTS:
            if phrase in sketch:
                add(concept)
        verdict = getattr(p, "verdict", "") or ""
        if verdict.startswith("proven"):
            name = (getattr(p, "name", "") or "").split("[", 1)[0]
            for prefix, concept in _PROVEN_CLAIM_CONCEPTS:
                if name == prefix or name.startswith(prefix + "_"):
                    add(concept)
    return out


def hazard_concepts(hazards) -> list[str]:
    """Intent:
        Concepts from analytically found domain hazards (the
        diagnostics `domain_hazards` list): a pole is a singularity, a
        stationary/inflection point is a critical point.
    """
    out: list[str] = []
    for h in hazards or []:
        concept = _HAZARD_CONCEPTS.get((h or {}).get("kind"))
        if concept and concept not in out:
            out.append(concept)
    return out


def concepts_for(facts, probes) -> dict:
    """The full provenance split for one adjudicated function:
    `{"declared": [...], "mechanism": [...], "keyword": [...]}`,
    each in stable order, never flattened here (the record writes the
    flat union at its interop surface and this split beside it)."""
    declared = list(getattr(facts, "doc_concepts", []) or [])
    mechanism = mechanism_concepts(facts, probes)
    keyword = [normalize_concept(h) for h in
               (getattr(facts, "doc_hints", []) or [])]
    return {"declared": declared,
            "mechanism": mechanism,
            "keyword": [k for k in keyword if k]}


def flat_union(sources: dict) -> list[str]:
    """The interop shape: one sorted, de-duplicated list over every
    provenance, exactly the spec's own `meta.concepts` example."""
    seen: set = set()
    for names in sources.values():
        seen.update(names)
    return sorted(seen)



def curation_path(root: str = ".") -> str:
    """The concept-curation file under the store's meta/ area:
    `.mathema/meta/concepts.yaml`, `{key: {concepts_dismissed: [...]}}`.
    `.mathema/` travels with the code (commit it, the verified layer
    is the record); meta/ is the UX/curation corner of it."""
    import os
    return os.path.join(root, ".mathema", "meta", "concepts.yaml")


def dismissed_concepts(root: str, key: str) -> list:
    """The dismissed-concept list for one key, [] when none."""
    import os

    import yaml
    path = curation_path(root)
    if not os.path.exists(path):
        return []
    try:
        doc = yaml.safe_load(open(path)) or {}
    except Exception:
        return []
    return list((doc.get(key) or {}).get("concepts_dismissed") or [])

def accept_concepts(root: str, key: str, accepted: list,
                    dismissed: list, by: "str | None" = None) -> str:
    """Intent:
        The lightweight tag-curation acceptance: `accepted` concepts
        earn the documented rung (stamped on the verified record as
        `concepts_accepted`, carried forward), `dismissed` ones are
        recorded in the AUTHORED declared layer
        (claims/concepts.claims.yaml entry meta
        mathema.concepts_dismissed) so the suggestion pass never
        offers them again. Never gates anything.
    """
    import os

    import yaml
    from . import auth
    # curation is the lightest acceptance, and it was also the one
    # path that wrote with no prompt at all; the gate closes that
    auth.enforce_policy(auth.require_human("accept --concepts"), root)
    wrote = []
    if accepted:
        from .spec import verified_dir, write_yaml
        path = os.path.join(verified_dir(root), f"{key}.yaml")
        if os.path.exists(path):
            doc = yaml.safe_load(open(path)) or {}
            entry = doc.get(key) or {}
            have = list(entry.get("concepts_accepted") or [])
            for c in accepted:
                c = normalize_concept(c)
                if c and c not in have:
                    have.append(c)
            entry["concepts_accepted"] = have
            doc[key] = entry
            from .spec import integrity_checksum
            try:
                entry.setdefault("identity", {})["integrity"] = \
                    integrity_checksum(entry)
            except Exception:
                pass
            write_yaml(path, doc,
                       header=f"machine record; concepts accepted for {key}")
            wrote.append(f"accepted {', '.join(accepted)}")
        else:
            wrote.append(f"no verified record for {key}; accepted "
                         f"concepts need one (run verify first)")
    if dismissed:
        path = curation_path(root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        doc = (yaml.safe_load(open(path)) or {}) if os.path.exists(path) \
            else {}
        have = list((doc.get(key) or {}).get("concepts_dismissed") or [])
        for c in dismissed:
            c = normalize_concept(c)
            if c and c not in have:
                have.append(c)
        doc.setdefault(key, {})["concepts_dismissed"] = have
        with open(path, "w") as fh:
            fh.write("# concept curation, dismissals recorded here so "
                     "suggestions never repeat; part of .mathema/meta, "
                     "committed with the store\n")
            yaml.safe_dump(doc, fh, sort_keys=False, allow_unicode=True)
        wrote.append(f"dismissed {', '.join(dismissed)}")
    return "; ".join(wrote) or "nothing to write"
