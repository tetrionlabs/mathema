# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Intent extraction from documentation.

Intent and implementation are distinct records, loosely coupled: the docstring
is the author's *claim* about what a function is for, and it gets its own
evidence class; `documented`; the weakest tier (below proved/derived/probed),
but the only one available for compiled code (numpy, sklearn, builtins) and
often the richest statement of purpose anywhere.

Parses numpydoc-style docstrings: the summary paragraph becomes the documented
intent, the References section (and any bare URLs/DOIs) become citations on the
fact page, and keywords in the summary become concept hints for the graph.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# keyword → ontology node; matched only against the summary paragraph(s),
# not the whole docstring, to keep hints high-precision
KEYWORDS: dict[str, str] = {
    "convolution": "convolution", "convolve": "convolution",
    "average": "weighted-average", "mean": "weighted-average",
    "smoothing": "exponential-decay", "exponentially weighted": "exponential-decay",
    "monotonic": "monotonicity",
    "periodic": "periodicity", "sine": "periodicity", "cosine": "periodicity",
    "trigonometric": "periodicity", "tangent": "periodicity", "fourier": "periodicity",
    "recursive": "recursion",
    "cumulative": "conservation",
    "distance": "metric-space", "metric": "metric-space", "geodesic": "metric-space",
    "linear": "linearity",
    "idempotent": "idempotence",
    "commutative": "commutativity",
    "associative": "associativity",
}

_SECTION = re.compile(r"^(\w[\w ]*)\n\s*-{3,}\s*$", re.M)
# Google/Napoleon-style headers (Claims:, Intent:, Notes:, ...) coexist
# with numpydoc's dash-underlined ones. Each opens a block, not prose, so
# the summary stops at any of them, same as any other section; otherwise
# a docstring with no leading prose summary would have its block text
# read as `Facts.doc_intent` (and so as the `intent` field `to_spec()`
# writes). `Types:` and `Domain:` are not read as blocks anywhere, and
# stay listed so a docstring that carries one keeps that text out of
# the summary.
_GOOGLE_HEADER = re.compile(
    r"^\s*(Claims|Types|Intent|Domain|Notes|Concepts|Tags|Analysis"
    r"|References|Refs|Evidence|Policy):\s*$", re.M)
_URL = re.compile(r"https?://[^\s>\)\"]+")
_DOI = re.compile(r"\b10\.\d{4,9}/[^\s,;\"]+")


@dataclass
class DocIntent:
    """What `parse_doc()` extracted from a docstring: `summary` (the
    lead paragraph(s), stopped at the first section header), `refs`
    (role-labeled links from References/Refs/Analysis/Evidence/Policy
    sections plus any bare DOIs found anywhere, `(title, url, via)`
    triples), and `concept_hints` (ontology concepts matched against
    keywords in the summary, e.g. "monotonic" -> "monotonicity")."""
    summary: str = ""
    refs: list[tuple[str, str | None, str]] = field(default_factory=list)
    concept_hints: list[str] = field(default_factory=list)


def _sections(doc: str) -> dict[str, str]:
    out: dict[str, str] = {}
    matches = list(_SECTION.finditer(doc))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(doc)
        out[m.group(1).strip().lower()] = doc[m.end():end].strip()
    return out


def _summary(doc: str) -> str:
    head = _SECTION.split(doc)[0]  # everything before the first section header
    head = _GOOGLE_HEADER.split(head)[0]
    paras = [p.strip().replace("\n", " ") for p in head.split("\n\n") if p.strip()]
    return " ".join(paras[:2])[:400]


# reference-section spellings and the role each labels its links with:
# concepts are TAGS, references are LINKS, evidence, analysis
# notebooks, policy documents, and the role rides the record's `via`
# field so a reader knows what kind of link each is.
_REF_SECTIONS = {"references": "reference", "refs": "reference",
                 "analysis": "analysis", "evidence": "evidence",
                 "policy": "policy"}


def _references(doc: str, sections: dict[str, str]) -> list[tuple[str, str | None, str]]:
    refs: list[tuple[str, str | None, str]] = []
    seen: set[str] = set()

    def add(title: str, url: str | None, via: str = "reference") -> None:
        title = re.sub(r"\s+", " ", title).strip(" ,.\"'")
        if title.count('"') % 2:
            title = title.replace('"', "")
        key = url or title
        if key and key not in seen and title:
            seen.add(key)
            refs.append((title[:160], url, via))

    # References:, Refs:, and Analysis: all feed the same citation
    # list; Analysis: is the working-notes spelling (a notebook or
    # page documenting a model assumption, say), same shape, entirely
    # optional. Both header styles are read (numpydoc underlined and
    # Google colon), and "- Title: URL" lines and bare URLs parse
    # alongside the numpydoc ".. [1]" form.
    def _colon_block(name: str) -> str:
        m = re.search(rf"^([ \t]*){name}:[ \t]*$", doc,
                      re.IGNORECASE | re.MULTILINE)
        if not m:
            return ""
        rest = doc[m.end():].splitlines()
        out, baseline = [], None
        for line in rest:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if baseline is None:
                baseline = indent
            elif indent < baseline:
                break
            out.append(line)
        return "\n".join(out)

    for section, via in _REF_SECTIONS.items():
        body = sections.get(section, "") or _colon_block(section)
        if not body:
            continue
        for entry in re.split(r"\.\.\s*\[\d+\]\s*|\n", body):
            entry = entry.strip().lstrip("-* ")
            if not entry:
                continue
            url_m = _URL.search(entry)
            title = _URL.sub("", entry).strip(" :|")
            if url_m and not title:
                title = url_m.group(0)
            add(title, url_m.group(0) if url_m else None, via)
    # bare DOIs anywhere in the docstring
    for doi in _DOI.findall(doc):
        add(f"doi:{doi}", f"https://doi.org/{doi}")
    return refs[:8]


def parse_doc(doc: str | None) -> DocIntent:
    """Extract a `DocIntent` from a raw docstring. `None` or empty
    input returns an empty `DocIntent()`, never raises."""
    if not doc:
        return DocIntent()
    sections = _sections(doc)
    summary = _summary(doc)
    low = summary.lower()
    hints, seen = [], set()
    for kw, concept in KEYWORDS.items():
        if kw in low and concept not in seen:
            seen.add(concept)
            hints.append(concept)
    return DocIntent(summary=summary, refs=_references(doc, sections),
                     concept_hints=hints[:5])
