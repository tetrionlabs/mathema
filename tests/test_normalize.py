# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The normalization pre-pass: exact rewrites (general range headers,
tuple unpacking with the swap case, loop-body temporaries, module
numeric constants) applied before every recognizer, with the inlined
constants riding the record note and the dependency-freshness surface
(a changed constant re-adjudicates, never a stale proof)."""
import os
import subprocess
import sys
import textwrap

from mathema.conjecture import check_conjectures, claim


def _mod(tmp_path, body, name="normmod"):
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    sys.path.insert(0, str(tmp_path))
    try:
        import importlib
        mod = importlib.import_module(name)
        importlib.reload(mod)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


def test_nonzero_start_range_fold_proves(tmp_path):
    mod = _mod(tmp_path, """
        def arith_from_one(n: int) -> float:
            total = 0.0
            for k in range(1, n):
                total += k
            return total
        """, "norm_a")
    (p,) = check_conjectures(mod.arith_from_one, [claim(
        "for n in [1,50], f(n) == n*(n-1)/2", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_stepped_range_lifts(tmp_path):
    # the trip count for range(0, n, 2) is floor((n+1)/2); the lift
    # must read the stepped header (the claim adjudicates either way;
    # the pin here is that derive is no longer unliftable)
    mod = _mod(tmp_path, """
        def stepped(n: int) -> float:
            total = 0.0
            for k in range(0, n, 2):
                total += k
            return total
        """, "norm_b")
    (p,) = check_conjectures(mod.stepped, [claim(
        "for n in [1,20], f(n) >= 0", route="derive")])
    assert "unliftable" not in (p.note or ""), p.note


def test_tuple_unpack_and_swap(tmp_path):
    mod = _mod(tmp_path, """
        import math

        def unpack(theta: float) -> float:
            ax, ay = math.cos(theta), math.sin(theta)
            return ax * ax + ay * ay

        def swap_pair(a: float, b: float) -> float:
            a, b = b, a
            return a - b
        """, "norm_c")
    (p,) = check_conjectures(mod.unpack, [claim(
        "for theta in [0,6], f(theta) == 1", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)
    (p,) = check_conjectures(mod.swap_pair, [claim(
        "for a in [0,5], b in [0,5], f(a,b) == b - a", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_loop_body_temporary_inlines(tmp_path):
    mod = _mod(tmp_path, """
        def with_temp(xs: list) -> float:
            total = 0.0
            for x in xs:
                term = 2.0 * x
                total += term
            return total
        """, "norm_d")
    from mathema.symbolic import lift_fold
    from mathema import analyze
    lifted = lift_fold(mod.with_temp, analyze(mod.with_temp))
    assert lifted is not None, "temp inlining did not reach the fold recognizer"
    (p,) = check_conjectures(mod.with_temp, [claim(
        "for xs in [0, 10], f(xs) >= 0", route="derive")])
    # the sign of a symbolic-length sum stays a prover gap; the pin
    # here is the LIFT (above) plus honest evidence with the sampler
    # respecting the element domain (this used to falsify falsely)
    assert p.verdict in ("holds", "proven"), (p.verdict, p.note)


def test_module_constant_inlines_with_explicit_note(tmp_path):
    mod = _mod(tmp_path, """
        import math

        HALF = 0.5

        def margin(a: float, b: float, c: float) -> float:
            return HALF * (a + b + c)
        """, "norm_e")
    (p,) = check_conjectures(mod.margin, [claim(
        "for a in [0,5], b in [0,5], c in [0,5], "
        "f(a,b,c) == (a+b+c)/2", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "module constants read at adjudication: HALF = 0.5" in p.note
    # the pedantic mirror: a float constant is its float value, never
    # the exact irrational it approximates; SQ3 == sqrt(3) must NOT
    # prove exactly
    mod2 = _mod(tmp_path, """
        import math

        SQ3 = math.sqrt(3)

        def root_margin(a: float) -> float:
            return SQ3 * a
        """, "norm_e2")
    (p,) = check_conjectures(mod2.root_margin, [claim(
        "for a in [1,5], f(a) == sqrt(3)*a", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch)


def test_changed_module_constant_invalidates_the_record(tmp_path):
    # the soundness rider end to end: adjudicate under one constant
    # value, rewrite the module with another, and the verify sweep must
    # RE-ADJUDICATE (the form hash cannot see the change; the
    # value-carrying dependency entry is what catches it)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pkg = tmp_path / "constpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "SCALE = 2.0\n\n\ndef scaled(x: float) -> float:\n"
        "    return SCALE * x\n")
    claims = tmp_path / "claims"
    claims.mkdir()
    (claims / "c.claims.yaml").write_text(
        "constpkg.mod.scaled:\n  claims:\n"
        "    - name: doubles\n"
        "      statement: 'for x in [0,5], f(x) == 2*x'\n"
        "      route: derive\n")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([repo, str(tmp_path)]))

    def run_verify():
        return subprocess.run(
            [sys.executable, "-c",
             "import sys; from mathema.cli import main; "
             f"sys.exit(main(['verify', '--root', {str(tmp_path)!r}]))"],
            cwd=str(tmp_path), capture_output=True, text=True, env=env)

    r = run_verify()
    assert "no baseline record" in r.stdout, r.stdout + r.stderr
    assert r.returncode == 0, r.stdout

    r = run_verify()
    assert "fresh" in r.stdout.splitlines()[0], r.stdout

    # the constant changes; the body does not (clear the bytecode
    # cache: the rewrite can land within the same mtime second)
    import shutil
    shutil.rmtree(pkg / "__pycache__", ignore_errors=True)
    (pkg / "mod.py").write_text(
        "SCALE = 3.0\n\n\ndef scaled(x: float) -> float:\n"
        "    return SCALE * x\n")
    r = run_verify()
    assert "dependency changed" in r.stdout, r.stdout
    assert "1 falsified" in r.stdout   # f(x) == 2*x is now false
    assert r.returncode == 1


def test_fold_epilogue_and_sequential_loops(tmp_path):
    # the bond-price shape: a post-loop statement updating the
    # accumulator lifts as sequential dataflow; and two independent
    # loops in one body compose their closed forms
    mod = _mod(tmp_path, """
        def bond_price(coupon: float, y: float, face_value: float, n: int) -> float:
            price = 0.0
            for i in range(n):
                price += coupon / (1 + y) ** (i + 1)
            price += face_value / (1 + y) ** n
            return price

        def two_loops(n: int, m: int) -> float:
            a = 0.0
            for i in range(n):
                a += i
            b = 0.0
            for j in range(m):
                b += j * j
            return a + b
        """, "norm_f")
    (p,) = check_conjectures(mod.bond_price, [claim(
        "for coupon in [1,10], y in [0.01,0.2], face_value in [50,100], "
        "n in [1,10], f(coupon,y,face_value,n) == "
        "coupon*(1 - (1+y)**(-n))/y + face_value*(1+y)**(-n)",
        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)
    (p,) = check_conjectures(mod.two_loops, [claim(
        "for n in [1,20], m in [1,20], "
        "f(n,m) == n*(n-1)/2 + m*(m-1)*(2*m-1)/6", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)
