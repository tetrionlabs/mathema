# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Harvest every claim text the repository ships, and pin how each reads.

Usage:
    python scripts/harvest_claim_corpus.py            # print a summary
    python scripts/harvest_claim_corpus.py --write    # rewrite the data file

Intent:
    Collect claim statements from the places the repository keeps them
    (test literals, documentation code blocks and inline spans, example
    files, the shipped claims files, and the package's own docstrings),
    then record, for each, whether it parses, how it renders in ascii and
    unicode, its identity text, its claims fingerprint and how each of
    its domain bindings renders. `tests/test_the_claim_corpus_reads_as_pinned.py`
    compares today's values with the data file `tests/data/claim_corpus.json`.

Notes:
    A statement is taken from a call's first argument or `statement=` /
    `law=` keyword for `claim`, `check`, `declare` and `claim_text`, from
    the value under a `statement` or `law` key, and from any string that
    begins with `for`, `let`, `∀` or `assuming` and parses. Only the
    first group is kept when it does not parse (the refusal message is
    pinned instead).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tests" / "data" / "claim_corpus.json"

_CALLS = {"claim", "check", "declare", "claim_text"}
_KEYS = {"statement", "law"}
_KEYWORD_START = re.compile(r"^\s*(for|let|∀|assuming)\b")
_MAX_LEN = 1500

#: Spellings pinned on purpose: the reserved representation spellings, the
#: type clause and hole forms, the `let` forms, and the membership forms
#: between languages and finite sets.
_EXTRA = (
    "let R be f32, for x in [0, 1], f(x) >= 0",
    "let Z be i64, for n in [0, 100] subset Z, f(n) >= 0",
    "let N be u64, for n in [0, 10] subset N, f(n) >= 0",
    "let x be f32, f(x) >= 0",
    "let c be i64, f(c) >= 0",
    "for x in [0, 1] as f32, f(x) >= 0",
    "for x in [0, 1] : float as f32, f(x) >= 0",
    "for x in [0, 1e8] subset f32, f(x) >= 0",
    "for x in [0, 1], f(x) >= 0",
    "for x in [0, 1] : float, f(x) >= 0",
    "for x in [0, 1] : int, f(x) >= 0",
    "for x in [0, 10] subset Z, f(x) >= 0",
    "for x in [0, 10] subset N, f(x) >= 0",
    "for x in [0, 10] subset R, f(x) >= 0",
    "for x in [0, 10] ⊂ ℤ, f(x) ≥ 0",
    "for x in [0, 1] : float|absent, f(x) >= 0",
    "for x in [0, 1] : float|missing, f(x) >= 0",
    "for x in [0, 1] : float|absent|missing, f(x) >= 0",
    "for x in [0, 1]|absent, f(x) >= 0",
    "for x in [0, 1]|missing, f(x) >= 0",
    "for x in R, f(x) >= 0",
    "for x in Z, f(x) >= 0",
    "for n in N, f(n) >= 0",
    "for x in [0, oo), f(x) >= 0",
    "for x in (-oo, oo), f(x) >= 0",
    "for x in [0, inf], f(x) >= 0",
    "let |inf| be 1e6, for x in [0, oo), f(x) >= 0",
    "let |inf| be 1e12, for x in [0, oo], f(x) >= 0",
    "let c be 2.0, f(c) >= 0",
    "let c be [-1e6, 1e6], for x in [0, 10], f(x) + c >= 0",
    "let g = math.sqrt, for x in (0, 100], g(x) >= 0",
    "let k be 3, for x in [0, 1], f(x) + k >= 0",
    "for x in [0, 1], x in [0, 2]",
    "for n in Z, n in Z",
    "for x in [0, 1], x in R",
    "for x in [0, 1], x in [0, 2], f(x) >= 0",
    "for s in L[ascii], s in L[ascii]",
    "for c in L[ascii], c in L[unicode]",
    "for c in L[ascii], f(c) in L[unicode]",
    "for k in {1, 2}, k in {1, 2, 3}",
    "for k in {1, 2}, f(k) in {1, 2, 3}",
    "for x in [0, 1], f(x) in [0, 2]",
    "L[ascii] subset L[unicode]",
    "L[ascii] ⊆ L[unicode]",
    "L[a] ⊂ L[b]",
    "L[ascii, len <= 8] subset L[unicode]",
    "for c in L[ascii] | {\"\"}, c in L[unicode]",
    "for order in L[ascii], f(order) in L[unicode]",
)


def _str_nodes(tree: ast.AST):
    """Yield (text, is_slot) for each string constant in a parsed module."""
    slot_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fname = (node.func.attr if isinstance(node.func, ast.Attribute)
                     else getattr(node.func, "id", None))
            if fname in _CALLS:
                if node.args:
                    slot_ids.add(id(node.args[0]))
                for kw in node.keywords:
                    if kw.arg in _KEYS:
                        slot_ids.add(id(kw.value))
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value in _KEYS:
                    slot_ids.add(id(v))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value, id(node) in slot_ids


def _python_candidates(path: Path):
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return
    for text, slot in _str_nodes(tree):
        if slot:
            yield text, True
        elif "\n" in text:
            for line in text.splitlines():
                yield line.strip(), False
        else:
            yield text, False


def _markdown_candidates(path: Path):
    body = path.read_text(encoding="utf-8")
    for span in re.findall(r"`([^`\n]+)`", body):
        yield span, False
    for line in body.splitlines():
        yield line.strip(), False


def _yaml_candidates(path: Path):
    import yaml
    try:
        docs = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except yaml.YAMLError:
        return

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in _KEYS and isinstance(v, str):
                    yield v, True
                else:
                    yield from walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from walk(v)
    for doc in docs:
        yield from walk(doc)


def _sources():
    """Yield (relative path, kind, candidates) over every tracked source."""
    import subprocess
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True,
                           capture_output=True, text=True).stdout.split("\n")
    for rel in sorted(f for f in files if f):
        path = ROOT / rel
        if rel == "scripts/harvest_claim_corpus.py" or rel.startswith(
                "tests/data/claim_corpus"):
            continue
        top = rel.split("/")[0]
        if rel.endswith(".py"):
            kind = {"tests": "tests", "examples": "examples",
                    "mathema": "package"}.get(top, "other")
            yield rel, kind, _python_candidates(path)
        elif rel.endswith(".md"):
            yield rel, "docs", _markdown_candidates(path)
        elif rel.endswith((".yaml", ".yml")):
            kind = "claims-file" if "claims" in rel else "other"
            yield rel, kind, _yaml_candidates(path)


def read_claim(text: str) -> dict:
    """How one claim text reads today: parse outcome, renderings, identity."""
    from mathema.conjecture import claim
    from mathema.domain import render_domain
    from mathema.spec import claims_fingerprint, fingerprint_text, render_claim_text
    try:
        cj = claim(text)
    except Exception as exc:  # noqa: BLE001 - the refusal is the datum
        return {"parses": False,
                "error": f"{type(exc).__name__}: {str(exc)[:400]}"}
    out = {"parses": True,
           "ascii": render_claim_text(cj, unicode=False),
           "unicode": render_claim_text(cj, unicode=True),
           "identity": fingerprint_text(cj),
           "fingerprint": claims_fingerprint(
               [{"name": "c", "statement": text}])}
    domains = {}
    for name in sorted(cj.domain):
        bound = cj.domain[name]
        domains[name] = [render_domain(bound, ascii_mode=True),
                         render_domain(bound, ascii_mode=False)]
    out["domains"] = domains
    return out


def harvest() -> dict:
    """Return the corpus: {text: {"sources": [...], ...reading}}."""
    found: dict[str, dict] = {}
    for rel, kind, cands in _sources():
        for text, slot in cands:
            text = text.strip()
            if not text or len(text) > _MAX_LEN:
                continue
            if not slot and not _KEYWORD_START.match(text):
                continue
            entry = found.setdefault(text, {"slot": False, "sources": set()})
            entry["slot"] = entry["slot"] or slot
            entry["sources"].add(f"{kind}:{rel}")
    for text in _EXTRA:
        entry = found.setdefault(text, {"slot": True, "sources": set()})
        entry["slot"] = True
        entry["sources"].add("extra:scripts/harvest_claim_corpus.py")
    corpus = {}
    for text in sorted(found):
        reading = read_claim(text)
        if not reading["parses"] and not found[text]["slot"]:
            continue
        reading["sources"] = sorted(found[text]["sources"])[:3]
        corpus[text] = reading
    return corpus


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(ROOT))
    corpus = harvest()
    parsed = sum(1 for v in corpus.values() if v["parses"])
    print(f"{len(corpus)} texts, {parsed} parse, "
          f"{len(corpus) - parsed} refused")
    if "--write" in argv:
        DATA.write_text(json.dumps(corpus, indent=1, ensure_ascii=False,
                                   sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {DATA.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
