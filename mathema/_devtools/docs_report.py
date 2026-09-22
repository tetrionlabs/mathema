# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Report-only self-application of the mathema-docstring convention to
mathema's own public surface: for every name in `mathema.__all__` that
resolves to a function, how its Intent and Notes stand (the sections
that matter here; Types duplicate the signature and Domain lives in
claims, so they aren't assessed for our own code).

    python -m mathema._devtools.docs_report

Never fails and never gates anything; the point is a visible number
that can only be improved on purpose. The convention stays optional
for end users; applying it to ourselves is what makes recommending it
honest.
"""
from __future__ import annotations

import inspect


def main() -> int:
    import mathema
    from mathema.docstring import parse_mathema_docstring

    rows = []
    for name in sorted(getattr(mathema, "__all__", [])):
        obj = getattr(mathema, name, None)
        if not inspect.isfunction(obj):
            continue
        doc = inspect.getdoc(obj) or ""
        try:
            parsed = parse_mathema_docstring(obj)
            intent = parsed.intent
        except Exception:
            intent = None
        if intent:
            words = len(intent.split())
            intent_col = f"documented ({words}w{', overlong' if words > 40 else ''})"
        elif doc.strip():
            summary = doc.strip().splitlines()[0]
            words = len(summary.split())
            intent_col = f"declared ({words}w{', overlong' if words > 40 else ''})"
        else:
            intent_col = "MISSING"
        has_notes = "Notes:" in doc
        rows.append((name, intent_col, "yes" if has_notes else "-"))

    width = max((len(r[0]) for r in rows), default=10) + 2
    print(f"{'public function':<{width}} {'intent':<28} notes")
    for name, intent_col, notes in rows:
        print(f"{name:<{width}} {intent_col:<28} {notes}")
    documented = sum(1 for _, c, _ in rows if c.startswith("documented"))
    declared = sum(1 for _, c, _ in rows if c.startswith("declared"))
    missing = sum(1 for _, c, _ in rows if c == "MISSING")
    print(f"\n{len(rows)} public functions: {documented} documented intent, "
          f"{declared} declared (summary-only), {missing} missing; "
          f"{sum(1 for r in rows if r[2] == 'yes')} with Notes.")
    print("report-only: nothing gates on this yet, by design.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
