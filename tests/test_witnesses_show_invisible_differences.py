# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness a reader cannot see is spelled out: when a string in a
counterexample holds characters that do not show when printed
(combining marks, format characters, unusual spaces), or the two
compared sides differ yet read the same, the witness adds each such
string's escaped form. Ordinary text, however far from ASCII, is shown
as it is."""
import textwrap

from mathema.conjecture import check_conjectures, claim


def _load(tmp_path, body, name):
    import importlib.util
    import sys
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_two_sides_that_read_the_same_are_spelled_out(tmp_path):
    mod = _load(tmp_path, """
        import unicodedata

        def key(s):
            \"\"\"Case folded, without compatibility folding.\"\"\"
            return s.casefold()

        def nfkc(s):
            return unicodedata.normalize("NFKC", s)
    """, "invisible_fns")
    decomposed = "\u30d5\u309a"
    law = "let n = invisible_fns.nfkc, for s in {'" + decomposed + "'}, f(n(s)) == f(s)"
    # swept point by point: the witness is the failing input, spelled out
    (p,) = check_conjectures(mod.key, [claim(law)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "\\u30d5\\u309a" in p.counterexample, p.counterexample
    # sampled: the witness shows both compared sides, each spelled out
    (q,) = check_conjectures(mod.key, [claim(law, route="probe")])
    assert q.verdict == "falsified", (q.verdict, q.note)
    assert "\\u30d5\\u309a" in q.counterexample, q.counterexample
    assert "\\u30d7" in q.counterexample, q.counterexample


def test_ordinary_text_is_shown_as_it_is(tmp_path):
    mod = _load(tmp_path, """
        def shout(s):
            \"\"\"Upper case, then an exclamation.\"\"\"
            return s.upper() + "!"
    """, "plain_text_fns")
    (p,) = check_conjectures(mod.shout, [claim("for s in {'日本'}, f(s) == s")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "日本" in p.counterexample
    assert "\\u65e5" not in p.counterexample, p.counterexample
