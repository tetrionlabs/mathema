# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The mathema statement grammar: typeable math, rendered as LaTeX.

A law is written the way a person types math in plain text, over the
generic function name `f` and the function's parameter names, and every
law has an exact LaTeX rendering:

    f(-x) = -f(x)          →   f(-x) = -f(x)
    f(x)^2 >= 0            →   f(x)^{2} \\geq 0
    f(x + c) ≤ f(x) + c    →   f(x + c) \\leq f(x) + c

The dialect is deliberately a superset of what conjecture.py already
evaluates: `^` means power (the law grammar has no XOR, so it is
unambiguous), a single `=` (or `≈`) means equality, `!=`/`≠` means
inequality, common Unicode math symbols (≤ ≥ − · × π ∞) are accepted,
and `|x|`/`||x||`/`⌊x⌋`/`⌈x⌉` mean `abs(x)`/`norm(x)`/`floor(x)`/`ceil(x)`
(bitwise-or is not a whitelisted operator anywhere in the grammar, so
`|` is otherwise unused). Bars wrap any expression: a bar opens where
an operand cannot end and closes where one can, so `|x + y - f(x)|`
and `|x| + |y|` both read as written, and a pair whose content is
exactly one further pair is a norm (`||x||`), while `||a| - |b||` is an
absolute value of a difference. On a matrix expression the same bars
are the determinant (see linalg.apply_matrix_sugar). `normalize()` maps any of these spellings to
the one canonical Python-expression form the probe and derive routes
both consume, so `f(x)^2 ≥ 0` and `f(x)**2 >= 0` are the same statement
with the same identity.

Rendering goes *through* sympy, so it is mathematically faithful rather
than typographically literal: a side may normalize (x + 0 renders as x).
Quantifiers are not part of the grammar at all; "for all x in ..." is the
claim's domain field, not statement syntax.

More special forms, all derive route only (see symbolic.py):

`d(<expr>, var[, var2, ...])` (or `∂(...)`, an alternate call-form
spelling) a partial derivative (`d(f(t,x), t)` is ∂f/∂t, `d(f(t,x), x,
x)` the second partial ∂²f/∂x²; what a PDE claim is, `d(f(t,x), t) ==
d(f(t,x), x, x)`, the heat equation, an ordinary equality over
partial-derivative terms, no new relation grammar needed). Several
shorter spellings all resolve to this same call, `d` and `∂` freely
interchangeable in every one of them: `d(<expr>/d<var>)` (a fraction,
scoped to *inside* the call, where the intent is unambiguous even
though the variable isn't, deferred, checked once the real
function's parameter names are known, since the literal denominator
could just as easily be a genuine parameter, e.g.
`gibbs_free_energy(dh, t, ds)`; a real collision is `skipped:misspecified`
rather than a silent guess; `∂`-marked units are never ambiguous
this way, since `∂` cannot appear in a real Python identifier at all);
a mixed/higher-order denominator concatenates one marker per variable,
each with its own optional exponent (`d(<expr>/dx^2dy)`, matching how
`\\frac{\\partial^3 f}{\\partial x^2 \\partial y}` is conventionally
written; superscript digits, `d(<expr>/dx²dy)`, work the same way,
converted to this ASCII form before parsing); the call's own opening
symbol may itself carry a restated total order (`d^3(<expr>/dx^2dy)`),
purely decorative unless it disagrees with what the denominator's own
exponents sum to, in which case the whole call is left unexpanded as a
likely typo. `d(<expr>)` (the variable omitted entirely, inferred from
`<expr>`'s own single free name, ambiguous or empty inference just
leaves the call unexpanded); and prime notation, `f'(x)`/`f''(x)`/...
(one apostrophe per differentiation, the variable inferred the same
way). A traditional, *unscoped* `∂f/∂x` fraction (bare division
anywhere in a law, not wrapped in `d(...)`/`∂(...)`) is still never
attempted, for either symbol, always scoped inside the call, so an
ordinary variable named `d` or `dh` is never at risk of being misread
as this sugar just because it appears near a `/`. `d(<expr>,
var[, ...])@{v=val, ...}` (or the word `at` instead of `@`, either with
optional whitespace around the marker) differentiates, then
substitutes each named variable for its value.

`lim(<expr>, var, point)` (point a constant or `oo`/`-oo`), or spelled
`lim(<expr>, var -> point)`/`lim(<expr>, var → point)`. A bracket-free
form drops the parens entirely: `lim <expr>, var -> point`, the
variable is always named explicitly here (unlike `d`/`integrate`'s own
variable-omitted forms, `lim <expr> -> point` reads ambiguously without
it, so that shorter spelling is deliberately not accepted).

`integrate(<expr>, var)` (indefinite) or `integrate(<expr>, var, lo,
hi)` (definite), or `integrate(<expr>, var)|_{lo}^{hi}`/`|_lo^hi`
(bare-token bounds need no braces, only a bound with its own space or
comma does, e.g. `|_0^oo` but `|_{0}^{n + 1}`); `var` may be omitted
from either the call or the bar form when `<expr>` has exactly one free
name. `∫` and the word `integral` are synonyms for `integrate`. A
bracket-free form chains one bound-bar per differential, left to
right, matching sympy's own native support for repeated `(var, lo,
hi)` triples in one call: `integral f(x,y) dx|_b^a dy|_b2^a2` (or,
variable omitted, `integral f(x)|_0^oo`).

`Sum(<expr>, var, lo, hi)` / `Prod(<expr>, var, lo, hi)`, discrete
summation/product over an index variable, capitalized deliberately, so
neither collides with the existing lowercase `sum(x)` (a sequence
aggregate over real sampled/observed data, used by the probe route and
by mathema.data) or a hypothetical `prod`; `var` here is a fresh index
name, not necessarily one of the function's own parameters. `Σ`/`Π` are
synonyms, and `Sum(<expr>)_{var=lo}^{hi}`/`Sum_{var=lo}^{hi} <expr>`
(subscript/superscript, either order, bare-token-or-braced bounds) are
sugar for the same 4-argument call.
"""
from __future__ import annotations

import ast
import re

import sympy
from sympy.printing.str import StrPrinter

from ._math_vocab import _BINOPS, _D_AT_SENTINEL, _MATH_ATTRS, _SYMPY_FUNCS, _call_name
from ._render_mode import (get_unicode_output as get_unicode_output,
                           set_unicode_output as set_unicode_output)
from ._scan import (_split_commas, mask_strings, outside_strings,
                    sub_outside_strings, unmask_strings)
# The domain model moved wholesale to domain.py (a sympy-free leaf);
# these re-exports keep every `from .grammar import <name>` consumer
# working. New code should import from mathema.domain directly.
from .domain import (MISSING as MISSING, Domain as Domain,
                     Interval as Interval, InvalidDomain as InvalidDomain,
                     _MEMBERSHIP_OPS as _MEMBERSHIP_OPS,
                     desuperscript_spaces as _desuperscript_spaces,
                     _as_domain as _as_domain,
                     _is_missing as _is_missing,
                     domain_bound_from_json as domain_bound_from_json,
                     domain_bound_to_json as domain_bound_to_json,
                     domain_contains as domain_contains,
                     is_missing as is_missing,
                     parse_binding as parse_binding,
                     render_domain as render_domain,
                     render_domain_bound as render_domain_bound,
                     split_quantifier as split_quantifier)
from .routes import MATRIX_PREDICATES as _MATRIX_PREDICATES
from .routes import OUTPUT_PREDICATES as _OUTPUT_PREDICATES
from .linalg import (RENDER_CALLS as _MATRIX_RENDER_CALLS,
                     RENDER_DIM as _MATRIX_RENDER_DIM,
                     operand_matrix_names as _matrix_names)


def _domain_safety_predicates() -> frozenset:
    # the LIVE examine vocabulary (static tables plus predicates owned
    # by registered claim families), read per parse rather than bound
    # at import so a family registered later is still recognized
    from .routes import examine_predicates
    return examine_predicates()


# \alpha, \beta, ... as identifier spellings: unlike \pi/\infty (math
# *constants*, collapsed to the fixed word _MATH_ATTRS already
# recognizes), these are ordinary *variable* names, so they collapse
# to the actual Unicode Greek letter, not a spelled-out word, matching
# how the letter would actually be written in a formula. Python accepts
# Unicode letters as identifiers, so `α` is a perfectly ordinary name
# once past this substitution; one extra benefit for `\epsilon`/
# `\lambda` specifically: `ε` already has its own established meaning
# elsewhere (conjecture.py/symbolic.py resolve `eps`/`epsilon`/`ε` to a
# claim's declared tolerance), so `\epsilon` naturally lines up with
# that rather than introducing a fourth spelling of the same thing; and
# `λ` sidesteps `lambda` being a Python keyword entirely (the *word*
# "lambda" would make `ast.parse` refuse it as a name, but the symbol
# isn't the keyword and parses as an ordinary identifier).
#
# One dict, used both directions: `_UNICODE` merges it in for
# `\name` -> symbol on input, `_GREEK_TO_BACKSLASH` (its exact reverse,
# built from this same table so the two can never drift apart) converts
# symbol -> `\name` for ASCII-mode *output*, but only for a symbol
# that's actually a key's value here. An arbitrary Unicode identifier
# with no entry in this table (Chinese, Cyrillic, ...) has no defined
# ASCII spelling and is left exactly as written; ASCII mode governs
# this grammar's own glyphs, not arbitrary identifier spelling in
# general, which isn't a well-posed problem to solve.
#
# `\Sigma`/`\Pi` (capital) are deliberately not in this table, same
# reasoning as lowercase π/ε (a math constant, a claim's own tolerance)
#; Σ/Π are the summation/product symbols instead, handled by their
# own substitution in normalize() (Σ -> "Sum", Π -> "Prod", run before
# _expand_sum_prod so `Σ(f(i))_{i=0}^n` gets the same subscript/
# superscript sugar `Sum(f(i))_{i=0}^n` already has), not this table.
_GREEK_LETTERS = {
    "\\alpha": "α", "\\beta": "β", "\\gamma": "γ", "\\Gamma": "Γ",
    "\\delta": "δ", "\\Delta": "Δ", "\\epsilon": "ε", "\\zeta": "ζ",
    "\\eta": "η", "\\theta": "θ", "\\Theta": "Θ", "\\iota": "ι",
    "\\kappa": "κ", "\\lambda": "λ", "\\Lambda": "Λ", "\\mu": "μ",
    "\\nu": "ν", "\\xi": "ξ", "\\Xi": "Ξ", "\\rho": "ρ", "\\sigma": "σ",
    "\\tau": "τ", "\\upsilon": "υ", "\\Upsilon": "Υ",
    "\\phi": "φ", "\\Phi": "Φ", "\\chi": "χ", "\\psi": "ψ", "\\Psi": "Ψ",
    "\\omega": "ω", "\\Omega": "Ω",
}

# `\vega`: not an actual Greek letter (there is no such letter), but
# quant-finance literature conventionally writes the option-pricing
# Greek "vega" as ν, the letter nu, precisely because nu's glyph reads
# like a stylized "v", a well-known point of confusion (vega and nu
# are not etymologically related), but adopted widely enough in that
# literature to be the correct symbol to recognize here regardless.
# Kept in a table separate from `_GREEK_LETTERS` (merged into the same
# input-side spots, `_UNICODE` and `_GREEK_WORD_TO_SYMBOL`) so it can
# never win the symbol -> `\name` reverse mapping below over the real
# letter nu that shares its glyph, see `_GREEK_TO_BACKSLASH`'s own
# construction.
_PSEUDO_GREEK_LETTERS = {"\\vega": "ν"}

# One set of tables, used both directions: `_UNICODE` merges
# `_GREEK_LETTERS` and `_PSEUDO_GREEK_LETTERS` in for `\name` -> symbol
# on input; `_GREEK_TO_BACKSLASH` converts symbol -> `\name` for
# ASCII-mode *output*, but only for a symbol that's actually a value in
# one of these tables. An arbitrary Unicode identifier with no entry in
# either table (Chinese, Cyrillic, ...) has no defined ASCII spelling
# and is left exactly as written; ASCII mode governs this grammar's own
# glyphs, not arbitrary identifier spelling in general, which isn't a
# well-posed problem to solve.
#
# Built from `_GREEK_LETTERS` (the real letters) first, then
# `_PSEUDO_GREEK_LETTERS` only fills in a symbol slot that isn't
# already claimed, so `\vega` sharing nu's own glyph (ν) can never
# overwrite `_GREEK_TO_BACKSLASH["ν"]`; it stays `"\\nu"`, never
# `"\\vega"`, regardless of dict insertion order.
_GREEK_TO_BACKSLASH = {symbol: name for name, symbol in _GREEK_LETTERS.items()}
for _pseudo_name, _pseudo_symbol in _PSEUDO_GREEK_LETTERS.items():
    _GREEK_TO_BACKSLASH.setdefault(_pseudo_symbol, _pseudo_name)
del _pseudo_name, _pseudo_symbol

# English-word spelling ("theta", "Theta", ...) -> symbol, the same
# tables with the leading backslash stripped off each key, a real
# function parameter can't literally be named "θ" (Python source can't
# easily type a bare Greek letter as an identifier a reader would
# recognize), but it can be named "theta" (or "vega"), and that's a
# deliberate enough choice of name that render_claim_text()'s unicode
# output auto-lets it to the symbol (see greek_symbol_for_name()).
# Case-sensitive: "Theta" and "theta" are different real parameter
# names and resolve to the different capital/lowercase symbols the
# table already distinguishes.
_GREEK_WORD_TO_SYMBOL = {name[1:]: symbol for name, symbol
                         in {**_GREEK_LETTERS, **_PSEUDO_GREEK_LETTERS}.items()}


def greek_symbol_for_name(name: str) -> str | None:
    """The Greek symbol `name` spells out in English (`"theta"` -> `θ`,
    `"Theta"` -> `Θ`, ...), matched case-sensitively against the same
    tables `_GREEK_LETTERS`/`_PSEUDO_GREEK_LETTERS`' own backslash
    spellings use, `None` for any other identifier, including a
    Greek letter's *symbol* itself (this is word -> symbol, not symbol
    -> symbol) and look-alike words this grammar has no symbol for
    (`"omicron"`, indistinguishable from Latin "o", was never added,
    see `_GREEK_LETTERS`' own note). `"vega"` -> `ν` matches here too,
    despite vega not being a real Greek letter; see
    `_PSEUDO_GREEK_LETTERS`."""
    return _GREEK_WORD_TO_SYMBOL.get(name)


#; long-name auto-let: a short spelling for a real parameter/function;
#; name too long to read comfortably in rendered output ----------------
#
# Purely positional: the Nth long name needing a short spelling gets the
# Nth available symbol off the pool below, in whatever order the caller
# supplies (spec.render_claim_text passes first-occurrence-in-the-law
# order for parameters, cj.funcs' own declaration order for functions)
#; this never tries to guess a "meaningful" letter from the name
# itself, which would need a lookup table and still guess wrong as
# often as right. `x` is always the first parameter-pool entry (the
# single most conventional variable letter); `g` the first function one
# (immediately after the primary `f`).
#
# ASCII pools are plain Latin only. Unicode pools mix in a curated set
# of Greek letters actually common in scientific notation, deliberately
# excluding: `iota`/`xi`/`upsilon`/`omicron` (rare, or, omicron;
# indistinguishable from Latin "o", see greek_symbol_for_name()'s own
# note); `pi` (already reserved as the math constant, see _UNICODE);
# `phi`/`psi`/`chi` (reserved for the *function* pool instead, an
# operator/functional convention); and `epsilon` (already reserved
# elsewhere in this codebase for a claim's own declared tolerance,
# conjecture.py/symbolic.py resolve `eps`/`epsilon`/`ε` that way,
# reusing it here for an unrelated long name would misread as a
# tolerance reference).
#
# `is_reserved()` (the derivative call form `d`, `lim`, ...) is excluded
# from every pool at assignment time, not baked into the string itself,
# since is_reserved() is the one true source for that set.
_PARAM_POOL_UNICODE = "xyzuv" + "τκαβγλμνσρδηζωθ" + "wabcijklmnopqrst"
_PARAM_POOL_ASCII = "xyzwuvabcdefghijklmnopqrst"
_FUNC_POOL_UNICODE = "gh" + "φψχ" + "ijklmnopqrstuvwxyzabce"
_FUNC_POOL_ASCII = "ghijklmnopqrstuvwxyzabce"


def _assign_short_names(names: list, pool: str, numbered_base: str, taken: set) -> dict:
    """`names` (already in a fixed, deterministic order) -> the next
    available symbol off `pool` each, skipping anything already in
    `taken` or reserved for this grammar's own call-forms; overflows to
    a numbered `<numbered_base><n>` once `pool` runs out rather than
    raising; a claim with dozens of long names is unusual, not
    invalid.

    Never iterates a set for anything that decides *which* name gets
    *which* symbol; `taken` is only ever used for O(1) membership
    tests, so the result depends solely on `names`' and `pool`'s own
    fixed order, stable across processes and runs (unlike Python's own
    `hash()` on a string, randomized per-process, never used here)."""
    out: dict = {}
    it = iter(c for c in pool if c not in taken and not is_reserved(c))
    for name in names:
        symbol = next(it, None)
        if symbol is None:
            n = 1
            while f"{numbered_base}{n}" in taken:
                n += 1
            symbol = f"{numbered_base}{n}"
        out[name] = symbol
        taken.add(symbol)
    return out


def auto_short_names(param_names: list, func_names: list, *, unicode: bool,
                     taken: set | None = None) -> dict:
    """Long real-parameter/function names -> a short spelling apiece
    (see the pool comment above). `param_names`/`func_names` must
    already be in the order a caller wants symbols handed out in; this
    function never reorders them. Functions are assigned first, so
    `g`/`h` (and, in unicode, `φ`/`ψ`/`χ`) are reserved before
    parameters can draw from the pool that follows them. `taken` seeds
    the "already spoken for" set (e.g. a real single-letter name
    already present in the claim, or a symbol a different auto-let
    mechanism already assigned), omit it to start from an empty set."""
    if taken is None:
        taken = set()
    func_pool = _FUNC_POOL_UNICODE if unicode else _FUNC_POOL_ASCII
    param_pool = _PARAM_POOL_UNICODE if unicode else _PARAM_POOL_ASCII
    func_renames = _assign_short_names(func_names, func_pool, "f", taken)
    param_renames = _assign_short_names(param_names, param_pool, "x", taken)
    return {**func_renames, **param_renames}


# A run of Unicode superscript digits is this grammar's own spelling of
# `^<digits>`; `x²` reads as `x^2` (ordinary power), and (the reason
# this exists) a derivative fraction's own restated total order or
# per-variable exponent (`d²(f(x)/dx²)`) reads the same way. Digits
# only: superscript *letters* exist for the whole alphabet in Unicode
# (via two different blocks, confirmed with `unicodedata.lookup`,
# not guessed), but nothing in this grammar's own `^`/`_` positions is
# ever a bare letter, so there's no meaning to map one to. No matching
# INPUT rule for subscript digits: every `_`-position this grammar has
# (`Sum`/`Prod`'s own index) is always `name=value`, never a bare
# digit. Subscript digits are still used on the *output* side, purely
# decoratively: `_print_Integral` attaches a definite integral's own
# integer bounds directly to its `∫` (subscript lower, superscript
# upper, `∫₀¹`), redundantly with the same bounds already spelled out in
# the call's own arguments, decoration only, never load-bearing, so
# no matching input rule is needed there either.
_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_SUBSCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉"
_SUPERSCRIPT_TO_DIGIT = str.maketrans(_SUPERSCRIPT_DIGITS, "0123456789")
_DIGIT_TO_SUPERSCRIPT = str.maketrans("0123456789", _SUPERSCRIPT_DIGITS)
_DIGIT_TO_SUBSCRIPT = str.maketrans("0123456789", _SUBSCRIPT_DIGITS)
_SUPERSCRIPT_RUN = re.compile(f"⁻?[{_SUPERSCRIPT_DIGITS}]+")

_UNICODE = {
    "≤": "<=", "≥": ">=", "≠": "!=", "−": "-", "·": "*", "×": "*",
    "π": "pi", "√": "sqrt", "∀": "for ", "∈": " in ", "∞": "oo",
    **_GREEK_LETTERS,
    **_PSEUDO_GREEK_LETTERS,
    # ⩽/⩾ ("less/greater-than-or-slanted-equal", U+2A7D/2A7E): an
    # ISO-style typesetting variant of ≤/≥, not a different relation,
    # true synonyms, unlike ⊂/⊆ (deliberately *not* merged anywhere in
    # this module: proper-subset and subset-or-equal are different
    # claims, not a spelling choice). Mathematical italic small pi
    # (U+1D70B, "𝜋", what many PDF/LaTeX renders actually paste,
    # distinct from the plain Greek π above) is the same constant, so
    # it collapses the same way plain π does.
    "⩽": "<=", "⩾": ">=", "𝜋": "pi",
    # ≈ ("approximately equal") normalizes to its own relation token,
    # `~=`, not a bare `=` collapsed into plain equality; it *evaluates*
    # exactly like a toleranced `==` claim (conjecture.py's `slack`,
    # symbolic.py's try_prove both treat `~=` as an alias of `==`), but
    # keeping it a distinct token means to_latex() can still render the
    # standard `\approx` rather than losing that a claim was ever written
    # as approximate in the first place.
    "≈": "~=",
    "≡": "=:=",
    # => / --> / \implies: three spellings of one "implies" marker,
    # canonicalized to `=>`, core's own outcome section
    # (`extract_outcome_clause`) reads this once normalize() has unified all three
    # spellings; unicode output renders it back as `⟹` (the same glyph
    # `\implies` already conventionally means), ascii keeps the plain
    # `=>`. A bare `->` is deliberately NOT folded in here even though
    # it reads the same way; lim's own bracket-free form has at least
    # one intentionally-unexpanded malformed shape that still contains
    # a literal `->` (`lim f(x) -> a`, missing its variable, left
    # exactly as typed so a later stage gives a clear error instead of
    # silently reinterpreting it), confirmed by a real test failure
    # when this was tried. `-->`/`⟹`/`\implies` have no such ambiguity
    # anywhere else in this grammar. A mathema.data-flavored claim
    # (record-schema.md's separate `grammar` field) is parsed by its
    # own, entirely different function, never core's `claim()`, so
    # this doesn't affect it.
    "⟹": "=>", "-->": "=>", "\\implies": "=>",
    # LaTeX-command spellings, typed literally (backslash and all) rather
    # than as the pre-composed Unicode glyph, same idea as \implies
    # above, extended to the symbols this batch adds. Each collapses to
    # the identical canonical token its Unicode counterpart does, so
    # `\neq`/`≠`/`!=` are one statement with one identity. Only plain
    # token-for-token LaTeX commands are covered; anything needing brace
    # arguments (`\sqrt{...}`, `\lfloor...\rfloor`, `\sum_{..}^{..}`,
    # `\|...\|`) is a real gap, not attempted here, see the module
    # docstring.
    "\\neq": "!=", "\\ne": "!=", "\\approx": "~=", "\\infty": "oo",
    "\\leq": "<=", "\\le": "<=", "\\geq": ">=", "\\ge": ">=",
    "\\leqslant": "<=", "\\geqslant": ">=", "\\equiv": "=:=",
    "\\varepsilon": "ε", "\\varphi": "φ",
    # sizing commands carry no meaning of their own: `\left| x \right|`
    # is the bars it sizes
    "\\left": "", "\\right": "",
    "\\cdot": "*", "\\times": "*", "\\pi": "pi", "\\forall": "for ",
    "\\in": " in ",
    # \partial(...)/\lim(...): call-prefix aliases only, same narrow
    # scope as the bare ∂( alias below (normalize()'s "∂(" -> "d("), not
    # a parse of the traditional ∂f/∂x or lim_{x->a} notations.
    "\\partial(": "d(", "\\lim(": "lim(",
    # Greek letter look-alikes worth merging, the same reasoning as ⩽/⩾
    # and math-italic π earlier: mathematical italic Greek letters
    # (U+1D6E2-U+1D7FF, "Mathematical Alphanumeric Symbols") are exactly
    # what many PDF/LaTeX renders paste for *every* Greek letter, not
    # just π, verified against Python's own unicodedata (MATHEMATICAL
    # ITALIC SMALL/CAPITAL <NAME>), not typed from memory, so there's no
    # transcription risk in the exact code points. Final sigma (`ς`,
    # used only in word-final position in actual Greek text) is the
    # same letter as `σ` everywhere a claim would use it, unlike ⊂/⊆,
    # there's no version of "sigma" that means something else. Only the
    # capital letters already given their own `\Name` spelling above get
    # an italic-capital merge here, the others (`\Alpha`, `\Beta`, ...)
    # were never added, since they're visually indistinguishable from
    # plain Latin capitals and wouldn't be typed deliberately.
    "𝛼": "α", "𝛽": "β", "𝛾": "γ", "𝛿": "δ", "𝜀": "ε", "𝜁": "ζ", "𝜂": "η",
    "𝜃": "θ", "𝜄": "ι", "𝜅": "κ", "𝜆": "λ", "𝜇": "μ", "𝜈": "ν", "𝜉": "ξ",
    "𝜊": "ο", "𝜌": "ρ", "𝜎": "σ", "𝜏": "τ", "𝜐": "υ", "𝜑": "φ", "𝜒": "χ",
    "𝜓": "ψ", "𝜔": "ω", "ς": "σ", "𝛤": "Γ", "𝛥": "Δ", "𝛩": "Θ", "𝛬": "Λ",
    "𝛯": "Ξ", "𝛴": "Σ", "𝛶": "Υ", "𝛷": "Φ", "𝛹": "Ψ", "𝛺": "Ω",
}

# a LaTeX command is the whole run of letters after its backslash, so
# `\left` is never read as `\le` followed by `ft`
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")
_LATEX_COMMANDS = {k: v for k, v in _UNICODE.items()
                   if _LATEX_COMMAND.fullmatch(k)}

RELATIONS = ("<=", ">=", "!=", "~=", "=:=", "==", "<", ">")
_REL_LATEX = {"==": "=", "<=": r"\leq", ">=": r"\geq", "!=": r"\neq",
             "~=": r"\approx", "=:=": r"\equiv",
             # the strict pair render as themselves: `<` and `>` are
             # already LaTeX math-mode operators
             "<": "<", ">": ">"}

# Every name this grammar's own special call-forms (`d`/`lim`/
# `integrate`/`Sum`/`Prod`) or the derive route's own function
# vocabulary (`_SYMPY_FUNCS`, `sin`, `sqrt`, `abs`, `factorial`, ...)
# recognizes, usable only in their own call shape (`d(...)`,
# `sin(...)`, ...), never as a bare variable name, on either route:
# `f(x) == sin` should be rejected the same way `f(x) == Sum` already
# is, not silently compare a number to a function object. `Σ`/`Π`
# normalize to `Sum`/`Prod` before parsing (see normalize()), so a
# bare, uncalled `Σ`/`Π` is caught by this same set under its word
# spelling, not left to slip through as an ordinary symbol just because
# it never looked like the ASCII word.
#
# This is the derive-route half of the reservation only, the probe
# route's own vocabulary (`conjecture._SAFE_FUNCS`) has a few names
# with no symbolic equivalent at all (`len`, `sum`), which `grammar.py`
# can't see without importing back from `conjecture.py` (a real
# circular import, not just an inconvenience: `conjecture.py` already
# imports from `grammar.py`). `conjecture._validate` ORs `is_reserved()`
# with its own `name in _SAFE_FUNCS` check to cover those too, rather
# than this module trying to know about a route-specific vocabulary
# that isn't its own.
_RESERVED_CALL_NAMES = (frozenset({"d", "lim", "integrate", "Sum", "Prod",
                                   "cauchy_pv"})
                        | frozenset(_SYMPY_FUNCS))


def reserved_names() -> frozenset[str]:
    """Every name reserved for this grammar's own call-forms (see
    `_RESERVED_CALL_NAMES`), usable only as `name(...)`, never as a
    plain variable. `is_reserved(name)` checks one name against this
    set. Doesn't include the probe route's own few `_SAFE_FUNCS`-only
    names (`len`, `sum`), see this set's own module-level note."""
    return _RESERVED_CALL_NAMES


def is_reserved(name: str) -> bool:
    """Is `name` one of this grammar's own reserved call-form names
    (`reserved_names()`)? Checked wherever a bare `ast.Name` is about to
    become an ordinary variable/symbol, so `Sum`/`d`/`sin`/... get a
    clear, direct rejection instead of silently becoming a plain name
    that happens to share text with a recognized function."""
    return name in _RESERVED_CALL_NAMES

# The single-term shape the renderer writes between bars: a bare
# name/number, one f(x)-shaped call, or one parenthesized group. Input
# bars wrap any expression (see _fold_bars); rendering keeps bars for
# one term and the `abs(...)` call spelling for anything bigger.
_BAR_TOKEN = r"\w+(?:\([^|]*\))?|\([^|]*\)"
# `let name = expr, name2 = expr2, ... in rest`: textually binds each
# name to `(expr)` inside `rest`, left to right within the group, so a
# quantity too big for one bar-token can still go inside bars, e.g.
# `let y = a + b in |y| < 1` rather than the disallowed `|a + b| < 1`.
# Multiple bindings share one `in` (matching the `for x in .., y in ..:`
# quantifier's own comma-list convention) rather than needing nested
# `let .. in let .. in`; groups themselves still chain left to right.
_LET = re.compile(r"^\s*let\s+(.+?)\s+in\s+(.+)$", re.DOTALL)
# `lim(f(x), x -> a)` / `lim(f(x), x → a)`: sugar for the ordinary
# 3-argument form `lim(f(x), x, a)`. Recognized only inside a `lim(...)`
# call, not a general arrow anywhere in a law.
_LIM_ARROW = re.compile(r"(lim\(.*?,\s*)(\w+)\s*(?:->|→)\s*([^,()]+?)(\s*\))")
# `lim f(x), x -> a` / `lim f(x) as x -> a`: the bracket-free form of
# `lim`, no parens at all, the variable always named explicitly; see
# _expand_lim_bare. `as` reads the way this is conventionally spoken
# ("the limit of f(x) as x approaches a") and is a pure synonym for the
# comma separator here, not a third shape.
_LIM_WORD = re.compile(r"\blim\b")
_LIM_BARE_STOP = re.compile(r",|\bas\b|->|→|<=|>=|!=|~=|==|=")
# `Sum(f(i))_{i=0}^n` / `Sum(f(i))_{i=0}^{n+1}` (same for `Prod`): sugar
# for the 4-argument call form `Sum(f(i), i, 0, n)`, matching how
# `\sum_{i=0}^{n}` is conventionally written, subscript names the
# index and its lower bound, superscript the upper bound (a bare token,
# or a brace-wrapped expression for anything bigger than one token).
# Parsed by hand rather than a single regex, since the expression inside
# `Sum(...)` can itself contain parens (`Sum(f(i) + g(i))_{...}`) that a
# non-recursive regex can't balance.
_SUM_PROD_NAME = re.compile(r"\b(Sum|Prod)\(")
# trailing lookahead, not `\b`: `_` is itself a word character, so a
# plain `\bSum\b` would never match `Sum_{i=0}^n` at all (no boundary
# between "m" and "_"), excluding a following letter/digit directly
# (rather than requiring a non-word character) is what actually
# distinguishes `Sum_{...}` from `Summary`/`Sum2`, while still allowing
# `_`/`^`/`(` right after the word.
_SUM_PROD_WORD = re.compile(r"\b(Sum|Prod)(?![a-zA-Z0-9])")
# no leading `^` anchor on these: matched via .match(text, pos), which
# already anchors to `pos`; `^` there would mean "true start of
# string" instead and silently never match anywhere but position 0.
# One `_`/`^` mark: either a single non-brace character or a
# `{...}`-wrapped group, LaTeX's own convention, more than one
# character always needs braces (`Sum_i^n`, not just `Sum_{i}^{n}`, but
# `Sum_{i=0}^{n+1}` for anything bigger). `[^{}]*` rather than a nested-
# brace scan: a bound's own content is never itself brace-delimited
# (unlike Sum/Prod's *expression* argument, which can contain parens
# and is handled by _find_balanced_call instead).
_BOUND_MARK = re.compile(r"\s*([_^])\s*(?:\{([^{}]*)\}|(\S))")
_TRAILING_EXPR_STOP = re.compile(r",|<=|>=|!=|~=|==|=")
# `d(f(x,y), x)@{x=a, y=b}` / `d(f(x,y), x) at {x=a, y=b}`: sugar for
# differentiating first, then substituting each named variable for its
# value, see _expand_d_at. `@` and the word `at` are pure synonyms,
# with optional whitespace on either side of the marker.
# `integrate(f(x), x)|_{a}^{b}`: sugar for the already-existing 4-argument
# bounded form `integrate(f(x), x, a, b)`, see _expand_integrate_at.
# Both reuse _find_balanced_call/_scan_bound, the same hand-scan
# _expand_sum_prod itself uses and was factored out of, for the same
# reason: the expression inside the call can itself contain parens.
_D_NAME = re.compile(r"\bd\(")
_INTEGRATE_NAME = re.compile(r"\bintegrate\(")
_D_AT_MARK = re.compile(r"\s*(?:@|\bat\b)\s*\{\s*(.+?)\s*\}")
_EVAL_BAR_PREFIX = re.compile(r"\s*\|_")
# `integral f(x,y) dx|_b^a dy|_b2^a2` / `integral f(x)|_0^oo` (var
# omitted): the bracket-free form of `integrate`, no parens around the
# integrand, see _expand_integral_bare. The expression scan stops at
# whichever comes first: the ordinary Sum/Prod-style stop tokens, a
# bare top-level `|` (the variable-omitted shape, bound bar attached
# directly), or a `d<name>` marker immediately (whitespace aside)
# followed by `|` (an explicit differential's own bound bar).
_INTEGRAL_WORD = re.compile(r"\bintegral\b")
# One or more `∫`/`∬`/`∭`, each optionally immediately followed by its
# own subscript-lower/superscript-upper bound decoration
# (`_integral_bound_marker`'s own output, e.g. `∫₀¹`), collapses the
# whole run to the single word `integral`, discarding any decoration
# with it, in whichever order the subscript/superscript halves come in
# (they're discarded either way, so there's nothing to gain by being
# strict about it, matching `_scan_bound_marks`'s own either-order
# tolerance for Sum/Prod's `_`/`^` marks). Without consuming the
# decoration here too, it would be left glued directly onto the word
# `integral` with no separator (`∫₀¹(` -> `integral₀¹(`, not even a
# valid identifier), since that decoration is purely cosmetic output,
# never meant to be typed or parsed on its own.
_INTEGRAL_MARK_RUN = re.compile(
    rf"(?:[∫∬∭][₋⁻{_SUBSCRIPT_DIGITS}{_SUPERSCRIPT_DIGITS}]*)+")


def _collapse_integral_marks(text: str) -> str:
    """`_INTEGRAL_MARK_RUN.sub("integral", text)`, factored out so it
    can run as `apply_unicode_synonyms()`'s own first step (see that
    function's docstring), not just at its usual position in
    `normalize()`. A decorated `∫₀¹` must collapse to the plain word
    `integral` *before* any superscript-digit conversion sees the same
    text: converting the decoration's superscript half to `^<digits>`
    first would glue it onto `integral` with no separator
    (`integral^1(...)`, not even a valid identifier), since that
    decoration is purely cosmetic output, never meant to be parsed
    piece by piece. Idempotent: once collapsed, there's no more
    `∫`/`∬`/`∭` left for a second call to match."""
    return _INTEGRAL_MARK_RUN.sub("integral", text)
_D_MARKER_BAR = re.compile(r"\s*\bd([A-Za-z_]\w*)\s*(?=\|)")
_INTEGRAL_EXPR_STOP = re.compile(r",|<=|>=|!=|~=|==|=|\bd[A-Za-z_]\w*(?=\|)|\|")
# `f'(x)` / `f''(x)`: prime notation, sugar for `d(f(x), x)` /
# `d(f(x), x, x)`; one apostrophe per differentiation, the variable
# inferred the same way `d(<expr>)`'s own single-parameter inference
# does (see _extract_single_free_identifier). The prime character is
# the plain apostrophe, not a backtick. Must run before _expand_d_single_var
# (which only looks for literal `d(` calls, never `name'(`) so a primed
# call is already a plain `d(...)` by the time that pass runs.
_PRIME_NAME = re.compile(r"\b([A-Za-z_]\w*)('+)\(")


class NoRelation(ValueError):
    """The law text contains no ==, !=, <=, >= (or =) to split on."""


class UnreadableSpelling(ValueError):
    """A symbol in the law text whose reach cannot be read without
    guessing (a radical followed by a power, say)."""


_RADICAL_ATOM = re.compile(
    rf"\s*([0-9]+(?:\.[0-9]*)?|[^\W\d](?:(?![{_SUPERSCRIPT_DIGITS}])\w)*)")
_RADICAL_TRAILER = re.compile(r"\s*(?:\^|\*\*|!|\[|[⁰¹²³⁴⁵⁶⁷⁸⁹])")


def _radical_to_call(text: str) -> str:
    """Intent:
        Every `√` as a `sqrt(...)` call over the one atom that follows
        it: `√x` is `sqrt(x)`, `√2` is `sqrt(2)`, `√f(x)` is
        `sqrt(f(x))`, and `√(x + 1)` is `sqrt(x + 1)`. Radicals nest
        from the inside out, so `√√x` is `sqrt(sqrt(x))`.

    Raises:
        UnreadableSpelling: a radical with no atom after it, or one
        whose atom is followed by a power, factorial or subscript, where
        `√x^2` could mean either `sqrt(x^2)` or `sqrt(x)^2`.
    """
    while "√" in text:
        i = text.rindex("√")
        rest = text[i + 1:]
        if rest.lstrip().startswith("("):
            text = text[:i] + "sqrt" + rest.lstrip()
            continue
        m = _RADICAL_ATOM.match(rest)
        if m is None:
            raise UnreadableSpelling(
                f"`√` needs something to take the root of: write "
                f"√(...) in {text!r}")
        end = m.end()
        if rest[end:end + 1] == "(" and not m.group(1)[0].isdigit():
            depth = 0
            for j in range(end, len(rest)):
                depth += {"(": 1, ")": -1}.get(rest[j], 0)
                if depth == 0:
                    end = j + 1
                    break
        if _RADICAL_TRAILER.match(rest[end:]):
            raise UnreadableSpelling(
                f"the reach of `√` in {text!r} is ambiguous (the root of "
                f"the power, or the power of the root): write "
                f"√(...) with parentheses")
        text = f"{text[:i]}sqrt({rest[:end].strip()}){rest[end:]}"
    return text


def _expand_let(text: str) -> str:
    """Expand every leading `let <bindings> in rest` group; one or more
    comma-separated `name = expr` pairs sharing one `in`, by
    substituting whole-word occurrences of each name in `rest` with
    `(expr)`, left to right within the group. Chains across groups
    (`let a = .. in let b = .. in ...`) the same way."""
    m = _LET.match(text)
    while m is not None:
        bindings, rest = m.group(1), m.group(2)
        for part in _split_commas(bindings):
            name, _, expr = part.partition("=")
            name, expr = name.strip(), expr.strip()
            rest = sub_outside_strings(
                rf"\b{re.escape(name)}\b", f"({expr})", rest)
        text = rest
        m = _LET.match(text)
    return text


# `let name = expr, name2 = expr2, ..., for x in [...], statement`: a
# second, comma-terminated `let` shape, sitting directly in the same
# leading comma-list a `for` quantifier's own bindings occupy, no
# shared `in` needed, since each binding is already unambiguously
# self-terminated by an ordinary top-level comma, the same way a `for`
# binding already is. One leading `let` keyword opens the run (the same
# ergonomics as `_LET`/`_expand_let`'s own comma-separated bindings);
# repeating `let` on a later binding in the same run is accepted too but
# never required. This is what extract_let_bindings() recognizes;
# _LET/_expand_let above is left untouched for its own job (an
# `in`-terminated group wrapping an oversized bar-expression, e.g.
# `let y = a + b in |y| < 1`, which has no comma-list context to anchor
# to at all). The two shapes are told apart by content, not position: a
# segment's captured right-hand side containing the standalone word `in`
# means it's the *other* shape (an `in`-terminated group, or its `rest`
# swallowed a later `for ... in`), so extract_let_bindings() stops
# rather than guessing, deliberately conservative, since a wrong guess
# here would silently misparse rather than raise. A right-hand side
# that's a plain dotted path (`pkg.mod.func`) binds a callable by name
# instead of substituting an expression, see claim()'s own funcs=
# handling, which resolves a string value there identically. Must run
# on the raw law text, before normalize(): once a leading run of these
# is peeled off, nothing `let`-shaped is left over for _expand_let to
# see, so the two mechanisms never compete for the same text.
#
# Known sharp edge: since a binding continuing the run doesn't need its
# own `let`, a segment immediately after one that looks like the `n=500`
# sampling-intensity modifier (no surrounding spaces around `=`) would be
# swallowed as a let-binding instead, if nothing but commas separate it
# from the run's start; put a `for` binding between the run and
# `n=...`, or repeat `let` on it, to avoid this (mirrors the existing
# `n`-as-a-real-parameter-name sharp edge split_quantifier's own
# docstring already calls out).
_LET_RUN_STARTS = re.compile(r"^\s*let\b")
_LET_STRIP = re.compile(r"^\s*let\s+")
# the `=` must not be the head of a relation token: `f =:= g` after a
# let run is the claim's own equivalence statement, never a binding
# `f = := g`, and `f == g` likewise stays a statement
_LET_BINDING = re.compile(r"^\s*(?:let\s+)?(\w+)\s*=(?![:=])\s*(.+)$",
                          re.DOTALL)
# `` let `<token>` = <name> ``, a display-symbol alias, e.g.
# `` let `σ1` = sigma1 ``.
# `<token>` is anything but a literal backtick or newline, deliberately
# not restricted to `\w+` the way a bare alias name is; it's replaced
# away by a literal string match (see the loop below), never fed to
# ast.parse as a token, so it never needs to be a valid identifier at
# all. Backtick continuation always repeats `let` (unlike a bare-word
# alias's own optional repeat); a token's own contents could
# otherwise be mistaken for something else mid-run.
_LET_BINDING_BACKTICK = re.compile(r"^\s*let\s+`([^`\n]+)`\s*=\s*(.+)$", re.DOTALL)
_LET_DECLARE = re.compile(r"^\s*(\w+)\s+be\s+(.+)$", re.DOTALL)
# `let |inf| be 1e6`, the operational meaning of infinity for this
# claim (the pseudo-infinity magnitude every probe that would
# otherwise reach for float extremes consults). The bars ARE the
# grammar's magnitude spelling, and this is deliberately the ONE
# claim-text way to state it. A bare `let inf be ...` or a signed
# `let +-inf be ...` is refused with guidance rather than silently
# declaring a free variable named after infinity; `inf`/`oo` is
# also a domain-endpoint spelling. `∞` (synonym-folded to `oo` before
# matching) is accepted inside the bars.
_LET_PSEUDO_INF = re.compile(
    r"^\s*(?:(?P<bars>\|\s*(?:inf|oo|infinity)\s*\|)"
    r"|(?P<rejected>(?:\+-|±|\+/-)?\s*(?:inf|oo|infinity)))"
    r"\s+be\s+(?P<rhs>.+)$", re.DOTALL)
_LET_SEGMENT_HAS_IN = re.compile(r"\bin\b")
_LET_FUNC_VALUE = re.compile(r"^\w+(?:\.\w+)+$")
# `d(<expr>/d<var>)` -> `d(<expr>, <var>)` (also mixed/higher-order,
# `d(<expr>/dx^2dy)` -> `d(<expr>, x, x, y)`, and curly `∂` instead of
# `d` per unit, `∂` and `d` freely mixable): the traditional `df/dx`
# fraction spelling, scoped to *inside* a `d(...)`/`∂(...)` call, where
# the intent (differentiate) is unambiguous even though the specific
# variable isn't, see extract_diff_fraction_sugar. `(?<![A-Za-z0-9_])`
# rather than `\b` for the call opener: `\b` never matches immediately
# before `∂` at all (confirmed empirically); `∂` is a math-symbol
# character, not a "word" character by regex's own definition, so a
# boundary only exists there when the *preceding* character happens to
# be a word character, never when `∂` is preceded by whitespace, a
# comma, or the start of the string, which is the overwhelmingly common
# case. An explicit "not preceded by an identifier character" check
# works uniformly for both `d` and `∂`. An optional `^<digits>` right
# after the opening symbol (`d^3(...)`/`∂^3(...)`, superscript digits
# already converted to this ASCII form by `apply_unicode_synonyms`
# before this regex ever runs) restates the total order, purely
# decorative unless it disagrees with what the denominator's own
# exponents sum to, in which case the whole call is left unexpanded as
# malformed (a real typo worth catching, not silently trusting one
# source of truth over the other).
# `[^\W\d]` is "a word character that is not a digit", which is every
# Unicode letter plus underscore. ASCII-only here would be wrong in
# both directions: the grammar auto-renames `sigma` to the Greek
# letter when rendering, so `∂σ` is a spelling mathema itself WRITES
# and must therefore read back. When the unit failed to match, the
# denominator was not recognised and `f/∂σ` degraded into an ordinary
# quotient, turning a proven claim into an unknown one after a round
# trip through the store.
_DIFF_IDENT = r"[^\W\d]\w*"
_DIFF_FRAC_OPEN = re.compile(r"(?<![A-Za-z0-9_])([d∂])(?:\^(\d+))?\(")
_DIFF_FRACTION_UNIT = rf"[d∂]{_DIFF_IDENT}(?:\^\d+)?"
_DIFF_FRACTION_TRAILING = re.compile(rf"/((?:{_DIFF_FRACTION_UNIT})+)$")
_DIFF_FRACTION_UNIT_PARSE = re.compile(rf"([d∂])({_DIFF_IDENT})(?:\^(\d+))?")


def extract_diff_fraction_sugar(text: str) -> tuple[str, frozenset[str]]:
    """`d(<expr>/d<var>)` -> `d(<expr>, <var>)`, generalizing to a mixed/
    higher-order denominator (`d(<expr>/dx^2dy)` -> `d(<expr>, x, x,
    y)`, matching how `\\frac{\\partial^3 f}{\\partial x^2 \\partial y}`
    concatenates one marker per variable) and to curly `∂` instead of
    `d`, freely mixable per unit (`d(<expr>/dx^2∂y)` works the same as
    an all-`d` or all-`∂` denominator). Plus the set of literal
    ASCII-`d`-marked denominator names (`dh`, not the stripped `h`) this
    guessed at differentiation, checked later by `check_conjectures()`
    against the real function's own parameter names, once known, since
    `dh` could just as easily be a genuine parameter (a
    `gibbs_free_energy(dh, t, ds)`-shaped function is exactly that
    shape) as it could mean "d/dh". A `∂`-marked unit is never
    ambiguous this way and never added to that set: `∂` cannot appear
    in a real Python identifier at all (it's a math-symbol character,
    not a letter, by Python's own identifier grammar), so a
    `∂h`-marked denominator can never collide with a genuine parameter
    named `h`.

    Only the *last* top-level division inside a `d(...)`/`∂(...)` call
    is treated as the differentiation marker; anything earlier is
    ordinary division, deliberately unaffected (`d((1 + x)/(2+3)/dx)`
    differentiates `(1 + x)/(2+3)` with respect to `x`; the first
    division is never touched). Returns the input unchanged with an
    empty set when there's no such pattern at all.

    Must run on the raw law text, before `extract_let_bindings()`/
    `normalize()`, `claim()`'s own only caller. Calls
    `apply_unicode_synonyms()` on `text` first, for the same reason
    `extract_let_bindings()` does: a superscript-digit exponent
    (`d(<expr>/dx²)`) needs converting to its ASCII `^2` spelling before
    this function's own regexes, which only look for the ASCII form,
    ever see it.

    Returns a real tuple rather than a text-embedded marker: no
    separator can be guaranteed to never collide with legitimate claim
    text, and a marker embedded in the string has to be found and
    stripped at every place that might see it before `ast.parse`, the
    private `_D_AT_SENTINEL` used elsewhere in this module is exactly
    that kind of marker, and its own rendering path needed a dedicated
    fix to stop it leaking into displayed text. A `frozenset[str]`,
    always present (empty when nothing is ambiguous), has nothing to
    strip anywhere, since the text itself is never contaminated to
    begin with."""
    text = apply_unicode_synonyms(text)
    ambiguous: set[str] = set()

    def rewrite(m, args, call_end):
        restated_order = m.group(2)
        stripped = args.strip()
        fm = _DIFF_FRACTION_TRAILING.search(stripped)
        if fm is None:
            return None
        expr = stripped[:fm.start()].strip()
        units = [(um.group(1), um.group(2), int(um.group(3) or 1))
                for um in _DIFF_FRACTION_UNIT_PARSE.finditer(fm.group(1))]
        total = sum(order for _, _, order in units)
        if restated_order is not None and int(restated_order) != total:
            return None
        expanded_vars = []
        for symbol, name, order in units:
            expanded_vars.extend([name] * order)
            if symbol == "d":
                ambiguous.add(f"d{name}")
        return f"d({expr}, {', '.join(expanded_vars)})"

    rewritten = outside_strings(
        lambda masked: _rewrite_balanced_calls(masked, _DIFF_FRAC_OPEN,
                                               rewrite), text)
    return rewritten, frozenset(ambiguous)


def _parse_pseudo_infinity(form: str, rhs: str) -> float:
    """Intent:
        Resolve one pseudo-infinity binding to its magnitude. Only the
        bars form (`let |inf| be 1e6`) is a valid claim-text spelling;
        the bars mean magnitude, and infinity is treated
        symmetrically. Any other spelling of the word (bare `inf`, a
        signed `+-inf`) is refused with guidance: `inf`/`oo` also
        spells a domain endpoint, so those forms are too easy to
        misread as something else.

    Raises:
        InvalidDomain: a non-bars spelling, or a magnitude that isn't
        a finite positive number.
    """
    rhs = rhs.strip()
    if form != "bars":
        raise InvalidDomain(
            "the operational infinity is spelled with magnitude bars: "
            "`let |inf| be 1e6`; a bare or signed `inf` reads too "
            "much like the domain-endpoint spelling")
    try:
        magnitude = float(rhs)
    except ValueError as e:
        raise InvalidDomain(
            f"let |inf| be ... expects a positive magnitude (let |inf| "
            f"be 1e6); got {rhs!r}") from e
    if magnitude != magnitude or magnitude <= 0 \
            or magnitude == float("inf"):
        raise InvalidDomain(
            f"let |inf| be ...: the operational infinity must be a "
            f"finite positive magnitude; got {rhs!r}")
    return magnitude


# the named sets a representation declaration rebinds, and the carrier
# vocabulary it rebinds them to (`let Z be i64`). Reserved: the parser
# refuses both spellings with guidance rather than reading either as an
# ordinary free-variable binding, so the future meaning stays free.
_BASE_SET_NAMES = frozenset({"R", "Z", "N", "C"})
_RESERVED_CARRIERS = frozenset({
    "i8", "i16", "i32", "i64", "i128",
    "u8", "u16", "u32", "u64", "u128",
    "f16", "f32", "f64", "bigint", "f64int",
})


_SECTION_KEYWORDS = frozenset({"let", "for", "be", "in", "assuming"})


def _refuse_binding_subject(name: str) -> None:
    """Intent:
        Refuse a binding of the name `f`, which always denotes the
        function under test.

    Raises:
        InvalidDomain: `name` is `f`.
    """
    if name == "f":
        raise InvalidDomain(
            "`f` always names the function under test and cannot be "
            "rebound; bind another name (`let g = pkg.mod.func`) and "
            "use that")


def extract_let_bindings(
        text: str) -> tuple[dict[str, str], dict, str, dict[str, str],
                            float | None]:
    """Peel a leading run of comma-terminated `let` segments off `text`,
    one of three shapes each: `let name = expr` (later bindings in the
    same run may repeat `let` or omit it, both accepted), applying each
    substitution (`name` -> `(expr)`, left to right, so a later binding
    can reference an earlier one) into everything that follows, later
    bindings and the eventual statement alike, exactly as `_expand_let`
    already does within one `in`-terminated group; `let name = pkg.mod.func`
    (a bare dotted path, no other punctuation), a callable-letter binding
    instead, no substitution happens for it, returned in the
    `{name: "pkg.mod.func"}` map ready to merge into a claim's `funcs=`;
    and `let name be bounds`, deliberately not `in`, so a free
    variable's own declaration never looks like a `for` binding's
    (`parse_binding()`'s bound grammar is still reused as-is underneath,
    just fed through with `be` swapped back to `in` first), a *free*
    variable, one with no real parameter to alias, like a gauge-
    invariance claim's arbitrary shift constant. `bounds` accepts
    anything `parse_binding()` does after a membership operator: any
    interval closedness (`[lo, hi]`/`(lo, hi)`/mixed), a bare scalar
    (`let c be 2.0`, a degenerate single-point domain), a discrete set,
    or a bare `Z`/`N`/`R`. Declared with its own domain, returned in the
    second map ready to merge into a claim's `domain=` and exempt that
    name from the real-parameter-only domain-key check
    `check_conjectures()` otherwise applies (`Conjecture.free_vars`),
    and if the name collides with a real parameter anyway,
    `check_conjectures()` treats that as a likely mistake (use `for`
    instead) rather than silently accepting it. A `let name be bounds`
    binding must repeat `let` every time, unlike the other two shapes,
    its own right-hand side often contains other bare names, so allowing
    it to continue a run unmarked would risk swallowing a segment that
    wasn't meant to be a binding at all.

    A fourth shape rides on `be`: `let |inf| be 1e6` binds the
    claim's operational meaning of infinity (its pseudo-infinity
    magnitude, applied symmetrically) rather than declaring a free
    variable; the magnitude is the 5th return value (None when no
    such binding appears). This is deliberately the ONE claim-text
    spelling; a bare or signed `inf`/`oo` before `be` is refused with
    guidance, never treated as a free-variable name. Binding it twice
    with different magnitudes raises.

    Stops at the first segment that matches none of the shapes, or
    whose `name = expr` right-hand side contains the standalone word
    `in` (the `_LET`/`in`-terminated shape's territory, left untouched
    for `normalize()`'s own `_expand_let` to handle). Returns
    `({}, {}, text, {}, None)` unchanged when there's no leading `let`
    at all.

    The 4th return value: every bare-identifier alias found (`name ->
    expr`, alias key to real-name target, not the dotted-path
    `funcs` map, and not a `let ... be ...` free variable, which has no
    real-name target at all), exposed so `claim()` can detect a real
    parsing hazard non-positional `let`/`for` ordering makes newly
    reachable: a `for`
    clause processed in an *earlier* retry-loop iteration, before this
    call ever ran, can commit a domain key literally spelled the same
    as an alias found only *here* (`for m in [...], let m = m1, ...`)
   , silently binding the declared domain to the alias name instead
    of the real parameter it resolves to, since by the time the alias
    is known, the domain key is already committed and unreachable from
    here. `claim()` cross-checks this dict's keys against the final
    domain to catch that case and raise, rather than silently keeping
    a domain key that can never match a real parameter.

    Runs `apply_unicode_synonyms()` on `text` first, before any of its
    own `\\w+`-based name matching; this function runs on raw text,
    before `normalize()`'s own call to that same substitution, so a
    backslash-spelled name (`let \\alpha = alpha, ...`) needs resolving
    to its Unicode letter right here or `\\w+` (which can't include a
    leading backslash) would never recognize it as a binding name at
    all."""
    text = apply_unicode_synonyms(text)
    if _LET_RUN_STARTS.match(text) is None:
        return {}, {}, text, {}, None
    # quoted literals are data: masked for the whole run, so no binding
    # substitutes into a string value
    text, literals = mask_strings(text)
    funcs: dict[str, str] = {}
    free_domain: dict = {}
    aliases: dict[str, str] = {}
    pseudo_infinity: float | None = None
    while True:
        segments = _split_commas(text)
        first = segments[0]
        if _LET_STRIP.match(first) is not None:
            stripped = _LET_STRIP.sub("", first, count=1)
            pim = _LET_PSEUDO_INF.match(stripped)
            if pim is not None:
                bound = _parse_pseudo_infinity(
                    "bars" if pim.group("bars") else "rejected",
                    pim.group("rhs"))
                if pseudo_infinity is not None and bound != pseudo_infinity:
                    raise InvalidDomain(
                        f"the operational infinity is bound twice with "
                        f"different magnitudes: {pseudo_infinity:g} "
                        f"then {bound:g}")
                pseudo_infinity = bound
                text = ",".join(segments[1:]).strip()
                continue
            dm = _LET_DECLARE.match(stripped)
            if dm is not None:
                fname = dm.group(1)
                bounds = unmask_strings(dm.group(2).strip(), literals)
                _refuse_binding_subject(fname)
                if fname in _BASE_SET_NAMES or bounds in _RESERVED_CARRIERS:
                    # the representation-declaration spelling: rebinding
                    # a named set's machine carrier, the same shape as
                    # `let |inf| be 1e6` rebinding infinity. Reserved
                    # rather than squattable, so the future meaning is
                    # not taken by an accidental free-variable binding.
                    raise InvalidDomain(
                        f"`let {fname} be {bounds}` is reserved for "
                        f"representation declarations (binding a named "
                        f"set to a machine carrier such as i64 or f32), "
                        f"which are not supported yet; a free variable "
                        f"cannot be named {fname!r} and a carrier name "
                        f"cannot be a bound")
                parsed_binding = parse_binding(f"{fname} in {bounds}")
                if parsed_binding is None:
                    # parse_binding has no bare-scalar shape (`for x in
                    # 2.0` isn't valid syntax either); `let x be 2.0`
                    # gets one anyway, as the degenerate closed interval
                    # (2.0, 2.0), the same shape _inferred_literal_domain
                    # already uses for a claim's own literal argument.
                    try:
                        point = float(bounds)
                    except ValueError:
                        point = None
                    if point is not None:
                        parsed_binding = (fname, (point, point))
                if parsed_binding is None:
                    from .domain import _parse_binding
                    reason = _parse_binding(f"{fname} in {bounds}")
                    raise InvalidDomain(
                        reason if isinstance(reason, str) else
                        f"cannot read the bounds of `let {fname} be "
                        f"{bounds}`")
                if parsed_binding is not None:
                    _, value = parsed_binding
                    # a real parameter's own kind is already knowable
                    # elsewhere (its Python type annotation), so an
                    # untyped `for x in [0, 1]` leaves the type implicit
                    # on purpose, see parse_binding()'s own docstring.
                    # A `let`-declared free variable has no such other
                    # source, so its type is never left implicit: no
                    # explicit `subset`/`⊂` clause means "assumed real,"
                    # and _as_domain() makes that assumption an explicit
                    # Domain(base_type="R", ...) rather than a bare
                    # Interval/tuple that only means "real" by
                    # convention. An already-explicit type (Domain, or a
                    # bare "Z"/"N" string) passes through unchanged.
                    free_domain[fname] = _as_domain(value)
                    text = ",".join(segments[1:]).strip()
                    continue
        bm = _LET_BINDING_BACKTICK.match(first)
        if bm is not None and not _LET_SEGMENT_HAS_IN.search(bm.group(2)):
            token, expr = bm.group(1), bm.group(2).strip()
            rest = ",".join(segments[1:]).strip()
            # literal span replace, not `\b{name}\b`, a backtick token
            # is deliberately allowed to contain characters (`%`, digit
            # subscripts, ...) `\b` word-boundary matching can't reliably
            # bracket; the backticks themselves are the only delimiter
            # this needs, and they're never ambiguous with anything else
            # in this grammar (no other use of backtick exists).
            text = rest.replace(f"`{token}`", f"({expr})")
            if re.match(r"^\w+$", expr):
                aliases[token] = expr
            continue
        m = _LET_BINDING.match(first)
        if m is None or _LET_SEGMENT_HAS_IN.search(m.group(2)):
            if (_LET_STRIP.match(first) is not None
                    and not _LET_SEGMENT_HAS_IN.search(first)):
                raise InvalidDomain(
                    f"cannot read the binding "
                    f"{unmask_strings(first.strip(), literals)!r}: a let "
                    f"binding is `let name = expr`, `let g = pkg.mod.func` "
                    f"or `let name be bounds`")
            break
        name, expr = m.group(1).strip(), m.group(2).strip()
        if name in _SECTION_KEYWORDS:
            raise InvalidDomain(
                f"cannot read the binding "
                f"{unmask_strings(first.strip(), literals)!r}: {name!r} is "
                f"a keyword of the claim grammar, not a name to bind")
        if not expr:
            raise InvalidDomain(
                f"`let {name} =` binds {name!r} to nothing: give it an "
                f"expression or a dotted function path")
        _refuse_binding_subject(name)
        if re.fullmatch(rf"[(\s]*{re.escape(name)}[)\s]*", expr):
            raise InvalidDomain(
                f"`let {name} = ...` resolves to {name!r} itself: the let "
                f"bindings refer to each other in a cycle, so none of them "
                f"names a value")
        rest = ",".join(segments[1:]).strip()
        if not rest and _LET_STRIP.match(first) is None:
            shown = unmask_strings(first.strip(), literals)
            raise InvalidDomain(
                f"`{shown}` reads as another `let` binding (a binding may "
                f"continue a let run without repeating `let`), which leaves "
                f"no claim after the let run; if it is the claim, write it "
                f"with `==`: `{name} == {unmask_strings(expr, literals)}`")
        if _LET_FUNC_VALUE.match(expr):
            funcs[name] = expr
            text = rest
        else:
            text = re.sub(rf"\b{re.escape(name)}\b", f"({expr})", rest)
            if re.match(r"^\w+$", expr):
                aliases[name] = expr
    # A real parameter's name is a common thing to alias away from;
    # "let x = some_long_real_parameter_name" is a big part of what
    # `let` is *for*. If that long name is later reused as its own
    # `for`-binding (someone consistently writing the short alias
    # everywhere, forgetting the binding itself still needs the real
    # name), the substitution above already wrapped it in parens
    # wherever it appeared, including there, "(some_long_...) in
    # [...]" isn't a valid binding name at all. Resolved through the
    # alias dict here rather than left broken: any occurrence
    # immediately followed by a membership operator is unwrapped back
    # to the bare target name, exactly as if the real name had been
    # written in the `for` clause directly. Only ever built for a
    # bare-identifier alias target above (`aliases[name] = expr` only
    # runs when `expr` is a single word); a compound expression has
    # no single name that could stand as a binding's own, so it's never
    # a candidate for this at all.
    for target in aliases.values():
        text = re.sub(rf"\({re.escape(target)}\)(\s*{_MEMBERSHIP_OPS}\s)",
                      rf"{target}\1", text)
    if not text.strip():
        raise InvalidDomain(
            "the let run binds names but has no claim after it: state the "
            "claim after the last binding (`let c be [0, 1], f(x) + c >= 0`)")
    return (funcs, free_domain, unmask_strings(text, literals), aliases,
            pseudo_infinity)


def _find_balanced_call(text: str, name_pattern: "re.Pattern", start: int):
    """Find the next call matching `name_pattern` (e.g. `Sum(`, `d(`) at
    or after `start`, with a hand-scanned (not regex) balanced-paren
    match for its own argument list, necessary since the expression
    inside can itself contain parens, which a non-recursive regex can't
    balance. Returns `(match, args_text, call_end)`, `match` the
    regex match object (so a caller needing e.g. `match.group(1)` for
    `Sum` vs `Prod` still can), `args_text` everything between the
    call's own parens, `call_end` the index one past its closing `)`,
    or `None` if no more matches exist, or the one found has unbalanced
    parens (left for `ast.parse` to reject downstream, not this
    function's job)."""
    m = name_pattern.search(text, start)
    if m is None:
        return None
    depth, j = 1, m.end()
    while j < len(text) and depth > 0:
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
        j += 1
    if depth != 0:
        return None
    return m, text[m.end():j - 1], j


def _rewrite_matches(text: str, pattern: "re.Pattern", rewrite) -> str:
    """The shared skeleton every regex-scanned sugar expander used to
    hand-roll: repeatedly find `pattern`'s next match, splice in what
    `rewrite(m)` returns, and keep everything between matches verbatim.
    `rewrite` returns `(replacement, resume_index)` to rewrite (the
    scan continues at `resume_index`, which may be past the match when
    the sugar consumed trailing text), or `None` to leave the matched
    text alone, the "left alone on failure" convention every sugar in
    this module follows."""
    out, i = [], 0
    while True:
        m = pattern.search(text, i)
        if m is None:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:m.start()])
        result = rewrite(m)
        if result is None:
            out.append(m.group(0))
            i = m.end()
        else:
            replacement, i = result
            out.append(replacement)


def _rewrite_balanced_calls(text: str, name_pattern: "re.Pattern", rewrite) -> str:
    """`_rewrite_matches`'s sibling for call-shaped sugar: the scan unit
    is a whole balanced `name(...)` call (`_find_balanced_call`), and
    `rewrite(m, args, call_end)` returns a replacement string (the scan
    resumes right after the call), `(replacement, resume_index)` when
    the sugar also consumed a suffix (`@{...}`, `|_a^b`), or `None` to
    leave the call untouched. Scanning stops outright at an unbalanced
    call, leaving the rest of the text for `ast.parse` to reject
    downstream, `_find_balanced_call`'s own convention."""
    out, i = [], 0
    while True:
        found = _find_balanced_call(text, name_pattern, i)
        if found is None:
            out.append(text[i:])
            return "".join(out)
        m, args, j = found
        out.append(text[i:m.start()])
        result = rewrite(m, args, j)
        if result is None:
            out.append(text[m.start():j])
            i = j
        elif isinstance(result, tuple):
            replacement, i = result
            out.append(replacement)
        else:
            out.append(result)
            i = j


_CALL_NAME_BEFORE_PAREN = re.compile(r"([A-Za-z_]\w*)\s*\(")
_IDENTIFIER = re.compile(r"\b[A-Za-z_]\w*\b")


def _extract_single_free_identifier(expr_text: str) -> str | None:
    """The one variable name `expr_text` is actually a function of, or
    `None` if that is not well-defined, zero real candidates (`3 + 4`)
    or more than one (`f(x, y)`, `f(x) + g(y)`). A name used as a call's
    own function (`f` in `f(x)`) is never a candidate, and neither is a
    name this grammar already reserves for a call-form
    (`reserved_names()`). Shared by every sugar that infers "the"
    variable from an expression with exactly one free name: `d(<expr>)`'s
    single-parameter inference, prime notation (`f'(x)`), and
    `integrate`/`lim`'s own variable-omitted forms."""
    call_names = {m.group(1) for m in _CALL_NAME_BEFORE_PAREN.finditer(expr_text)}
    candidates = {name for name in _IDENTIFIER.findall(expr_text)
                  if name not in call_names and not is_reserved(name)}
    if len(candidates) != 1:
        return None
    return next(iter(candidates))


def _scan_bound(text: str, pos: int) -> tuple[str, int] | None:
    """Scan one bound token starting at `pos`: either a `{...}`-wrapped
    group, or the whole run of non-whitespace characters; `{...}` is
    the recommended notation for anything beyond a single word/number
    (unambiguous even to a human reader), but since a claim's rendered
    output always states the resolved bound back explicitly either way
    (render_domain/render_claim_text), a bare compound bound (`pi/2`,
    `2*pi`) is still accepted rather than silently truncated to just
    its leading word/number, truncating `pi/2` down to `pi` and
    leaving `/2` for the surrounding expression to consume produced a
    real, silent wrong answer here once (`integrate(f(x), x, 0,
    pi)/2` instead of a bound of `pi/2`).

    Returns `(bound_text, end)`, or `None` if nothing recognizable is
    there, shared across every bound position this module's sugar
    expansions need: `Sum`/`Prod`'s own `_{lo}^{hi}` upper bound, and
    `integrate(...)`'s `|_{lo}^{hi}` evaluation-bar sugar for BOTH its
    lower and upper bound (unlike `Sum`/`Prod`, whose lower bound is
    always name=value inside a fixed `_{...}` wrapper, `integrate(...)`'s
    own lower bound has no `=` in it at all, so it needs the same
    bare-or-braced flexibility the upper bound already has, not a
    separate, narrower rule).

    A next differential marker glued on with no separating space
    (`dx|_0^1dy|_0^2`) is swept into the same run (`1dy`) rather than
    specially detected here; treating it as ambiguous would need
    knowing whether `y` is actually a real variable in this context
    (the same question `ambiguous_diff_vars` answers for the
    differentiation-sugar case, deferred to check_conjectures() once
    the real function's parameters are known), which this low-level
    scan has no way to answer. `1dy` is not a valid bound either way,
    so it already fails cleanly downstream (`claim()`/check_conjectures()
    reject it as unparseable), no separate handling needed here.

    `^` itself is excluded from the run (never swallowed into a bare
    bound); it's this sugar's own structural mark introducing the
    upper bound (`_scan_bar_bounds` scans the lower bound with this
    same function, then checks that a literal `^` immediately follows
    before scanning the upper bound; a lower-bound scan greedy enough
    to eat that `^` itself would never find it there and the whole
    `|_lo^hi` match would silently fail instead). An upper bound
    wanting its own exponent (`pi^2`) needs braces (`{pi^2}`) for the
    same reason, not a new restriction, `^` was never part of a bare
    token here even before compound bounds were accepted."""
    if pos < len(text) and text[pos] == "{":
        depth, k = 1, pos + 1
        while k < len(text) and depth > 0:
            if text[k] == "{":
                depth += 1
            elif text[k] == "}":
                depth -= 1
            k += 1
        if depth != 0:
            return None
        return text[pos + 1:k - 1], k
    m = re.match(r"[^\s^]+", text[pos:])
    if m is None:
        return None
    return m.group(0), pos + m.end()


def _scan_bound_marks(text: str, pos: int):
    """Zero, one, or two `_`/`^` marks starting at `pos`, in either
    order (`_{...}^{...}` or `^{...}_{...}`), shared by both Sum/Prod
    shapes (leading-parenthesized and trailing-bare). Returns
    `(sub_content, sup_content, end)`, either content `None` if that
    mark wasn't present, or `None` entirely if neither matched at `pos`
    at all. Contents come back raw and uninterpreted, deliberately
    generic rather than assuming today's only supported shape
    (`index=value` in the subscript; a bare bound or `index=value` in
    the superscript, see `_parse_sum_prod_sub`/`_sup` below), so a
    richer bound (a double index, an inequality, a convergence
    criterion) is still just more text this same scan already captures
    correctly, not a reason to rewrite it later."""
    sub = sup = None
    end = pos
    for _ in range(2):
        m = _BOUND_MARK.match(text, end)
        if m is None:
            break
        content = m.group(2) if m.group(2) is not None else m.group(3)
        if m.group(1) == "_":
            if sub is not None:
                break
            sub = content
        else:
            if sup is not None:
                break
            sup = content
        end = m.end()
    if sub is None and sup is None:
        return None
    return sub, sup, end


def _parse_sum_prod_sub(content: str | None):
    """`index=lo` -> `(index, lo)`, or `None` if `content` doesn't have
    that shape, including no subscript at all, or a bare index with
    no inline bound (`Sum_i`, pulling the bound from a separately-
    declared domain instead): a real, requested shape, just not
    resolvable at this point in the pipeline yet (normalize() runs
    before any domain is parsed), tracked as a follow-up, not
    misread as something else here.

    Intended design for that follow-up, noted here rather than
    half-built now: expanding to a sentinel identifier (e.g.
    `Sum(f(i), i, __sum_bound_i_lo__, __sum_bound_i_hi__)`) with no
    resolver yet to consume it would only trade today's clean "not
    expanded, still literal text" no-op for a confusing "name not
    defined" failure later, worse, not better, until the resolver
    (reading the index's declared domain once one is parsed) actually
    exists. Build the sentinel and the resolver together, not this
    half first."""
    if content is None:
        return None
    name, sep, lo = content.partition("=")
    if not sep:
        return None
    return name.strip(), lo.strip()


def _parse_sum_prod_sup(content: str | None) -> str | None:
    """A bare bound (`n`), or `index=hi` (repeating the index, as some
    texts write "from i=0 to i=n"), either way, the actual upper
    bound value. Doesn't check the repeated index name against the
    subscript's own, accepted as written, not a reason to reject an
    otherwise well-formed claim over a naming mismatch that doesn't
    actually change the resulting bound."""
    if content is None:
        return None
    _, sep, hi = content.partition("=")
    return (hi if sep else content).strip()


def _resolve_sum_prod_bounds(text: str, pos: int):
    """The mark-scan plus subscript/superscript parse combined, from
    `pos` (right after Sum/Prod's expression, whichever shape),
    `(index, lo, hi, end)`, or `None` if any step fails, so both call
    sites in `_expand_sum_prod` (leading-parenthesized, trailing-bare)
    bail out identically."""
    marks = _scan_bound_marks(text, pos)
    if marks is None:
        return None
    sub_content, sup_content, end = marks
    sub = _parse_sum_prod_sub(sub_content)
    if sub is None:
        return None
    index, lo = sub
    hi = _parse_sum_prod_sup(sup_content)
    if hi is None:
        return None
    return index, lo, hi, end


def _scan_trailing_expr(text: str, pos: int,
                        stop: "re.Pattern" = _TRAILING_EXPR_STOP) -> tuple[str, int]:
    """The bare expression starting at `pos`, ending at the next
    top-level match of `stop` (or the end of the string),
    paren/bracket/brace-depth aware, the same convention `_split_commas`
    already uses, so a summand's own call arguments (`f(i, j)`) never
    terminate it early. `stop` defaults to `_TRAILING_EXPR_STOP` (a
    comma or relation operator) for Sum/Prod's own trailing-expression
    shape (`Sum_{i=0}^n f(i)`, no parens around the summand at all;
    the leading-parenthesized shape already has an unambiguous end, its
    own closing paren); `_expand_integral_bare`/`_expand_lim_bare` pass
    their own wider stop pattern, since a bracket-free `integral`/`lim`
    also needs to stop at its own differential/arrow marker, not just a
    comma or relation."""
    depth, i = 0, pos
    while i < len(text):
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            m = stop.match(text, i)
            if m is not None:
                return text[pos:i].strip(), i
        i += 1
    return text[pos:].strip(), len(text)


def _expand_lim_bare(text: str) -> str:
    """`lim f(x), x -> a` / `lim f(x) as x -> a` -> the parenthesized
    3-argument form `lim(f(x), x, a)`, the bracket-free spelling of
    `lim`, no parens around the expression at all, the variable always
    named explicitly (unlike `d`/`integrate`'s own variable-omitted
    forms, `lim f(x) -> a` reads ambiguously without the variable named;
    deliberately not supported). `as` is a pure synonym for the
    comma separator, reading the way this is conventionally spoken.
    `lim(` (immediately followed by a paren, no space) is left alone
    here; the ordinary parenthesized forms are handled by `_LIM_ARROW`
    instead. Left alone wherever no comma/`as`-then-arrow shape follows
    the expression."""
    def rewrite(m):
        after = m.end()
        if after < len(text) and text[after] == "(":
            return None
        expr, end = _scan_trailing_expr(text, after, stop=_LIM_BARE_STOP)
        stop_m = _LIM_BARE_STOP.match(text, end) if expr and end < len(text) else None
        if stop_m is None or stop_m.group(0) not in (",", "as"):
            return None
        var_m = re.match(r"\s*([A-Za-z_]\w*)\s*(?:->|→)\s*", text[stop_m.end():])
        if var_m is None:
            return None
        var = var_m.group(1)
        point_start = stop_m.end() + var_m.end()
        point, pend = _scan_trailing_expr(text, point_start)
        return f"lim({expr}, {var}, {point})", pend

    return _rewrite_matches(text, _LIM_WORD, rewrite)


def _expand_sum_prod(text: str) -> str:
    """`Sum(f(i))_{i=0}^n` (leading, parenthesized) or `Sum_{i=0}^n f(i)`
    /`Σ_{i=0}^n f(i)` (trailing, bare, the traditional reading order,
    Σ/Π already normalized to the word form by this point) -> the
    4-argument call form `Sum(f(i), i, 0, n)` (same for `Prod`).
    Subscript/superscript may appear in either order, and either may be
    a single bare character instead of a `{...}`-wrapped group, or the
    upper bound may repeat the index (`^{i=n}`) instead of a bare bound,
    see `_scan_bound_marks`/`_parse_sum_prod_sub`/`_sup`. Left alone
    wherever none of these shapes matches; the 4-argument form keeps
    working exactly as before, unsugared, and a bare index with no bound
    at all (`Sum_i`, no follow-up mark or trailing `=`) is left alone
    too rather than misread, since resolving it against a separately-
    declared domain isn't supported yet."""
    def rewrite(m):
        name, after = m.group(1), m.end()
        if after < len(text) and text[after] == "(":
            found = _find_balanced_call(text, _SUM_PROD_NAME, m.start())
            if found is None:
                return None   # unbalanced call: left for ast.parse downstream
            _, expr, j = found
            resolved = _resolve_sum_prod_bounds(text, j)
            if resolved is None:
                return text[m.start():j], j
            index, lo, hi, end = resolved
            return f"{name}({expr}, {index}, {lo}, {hi})", end
        resolved = _resolve_sum_prod_bounds(text, after)
        if resolved is None:
            return None
        index, lo, hi, end = resolved
        expr, end2 = _scan_trailing_expr(text, end)
        return f"{name}({expr}, {index}, {lo}, {hi})", end2

    return _rewrite_matches(text, _SUM_PROD_WORD, rewrite)


def _expand_prime(text: str) -> str:
    """`f'(x)` -> `d(f(x), x)`, `f''(x)` -> `d(f(x), x, x)`, and so on;
    one apostrophe per differentiation, the variable inferred from
    `f(x)`'s own single free name (`_extract_single_free_identifier`).
    Left alone wherever that inference is ambiguous or empty
    (`f'(x, y)`, `f'(3)`), the primed call simply isn't rewritten (the
    same "left alone on failure" convention every other sugar in this
    module follows), and `unexpanded_prime_message` names it for
    `claim()` to refuse."""
    def rewrite(m, args, call_end):
        name, order = m.group(1), len(m.group(2))
        var = _extract_single_free_identifier(args)
        if var is None:
            return None
        return f"d({name}({args}), {', '.join([var] * order)})"

    return _rewrite_balanced_calls(text, _PRIME_NAME, rewrite)


def unexpanded_prime_message(text: str) -> str | None:
    """The claim-error message for the first primed call left in
    already-normalized `text`, or `None` when there is none.

    Intent:
        Prime notation reads its differentiation variable from the
        call's single free name, so `f'(v0, theta, g)` (three free
        names) and `f'(3)` (none) have no derivative variable and
        `_expand_prime` leaves them as written. This names such a call
        and the explicit `d(...)` spelling that states the variable,
        one `<var>` per prime.

    Notes:
        Only a balanced primed call is reported; an unbalanced one is
        left for the parser to reject, as `_find_balanced_call` does.
    """
    found = _find_balanced_call(text, _PRIME_NAME, 0)
    if found is None:
        return None
    m, args, _ = found
    name, primes = m.group(1), m.group(2)
    explicit = f"d({name}({args}), {', '.join(['<var>'] * len(primes))})"
    count = "none" if _IDENTIFIER.search(args) is None else "more than one"
    return (f"prime notation {name}{primes}({args}) differentiates with "
            f"respect to the call's single free variable, and ({args}) "
            f"has {count}; name the variable explicitly: {explicit}")


def _expand_d_single_var(text: str) -> str:
    """`d(f(x))` -> `d(f(x), x)`: a `d(...)` call with exactly one
    argument (no comma at all; an explicit `d(<expr>, var)` is left
    untouched) infers the differentiation variable from that argument's
    own single free name, the same way prime notation does
    (`_extract_single_free_identifier`). No function-signature
    knowledge is needed or used here: if the inferred name isn't
    actually one of the real function's parameters, the rewritten
    `d(f(x), x)` fails downstream exactly like any other undefined-name
    claim already does, not a new error path. Left alone (zero or more
    than one free name) wherever that inference doesn't resolve, same
    as every other sugar in this module."""
    def rewrite(m, args, call_end):
        if len(_split_commas(args)) != 1:
            return None
        var = _extract_single_free_identifier(args)
        if var is None:
            return None
        return f"d({args}, {var})"

    return _rewrite_balanced_calls(text, _D_NAME, rewrite)


def _expand_d_at(text: str) -> str:
    """`d(f(x,y), x)@{x=a, y=b}` / `d(f(x,y), x) at {x=a, y=b}` ->
    `d(f(x,y), x, __at__, x, a, y, b)`, sugar for "differentiate, then
    substitute". `@` and the word `at` are pure synonyms, either with
    optional whitespace around the marker. The private `__at__`
    sentinel separates the differentiation-variable arguments from the
    (var, value) substitution pairs appended after it, so
    `_law_to_sympy`'s own `d` handler can tell the two apart
    positionally without keyword-argument parsing; this codebase
    deliberately avoids `node.keywords` everywhere in claim-law calls.
    The sentinel form is never user-facing; only this expansion
    produces it. Left alone wherever the `@{...}`/`at {...}` suffix
    isn't there; the plain differentiation form keeps working exactly
    as before."""
    def rewrite(m, args, call_end):
        sm = _D_AT_MARK.match(text, call_end)
        if sm is None:
            return None
        pairs: list[str] = []
        for part in _split_commas(sm.group(1)):
            var, sep, val = part.partition("=")
            if not sep:
                return None
            pairs.append(f"{var.strip()}, {val.strip()}")
        return f"d({args}, {_D_AT_SENTINEL}, {', '.join(pairs)})", sm.end()

    return _rewrite_balanced_calls(text, _D_NAME, rewrite)


def _scan_bar_bounds(text: str, pos: int) -> tuple[str, str, int] | None:
    """`|_<lo>^<hi>` starting at `pos`, `(lo, hi, end)`, or `None` if
    that shape isn't there at all. Both bounds use the same bare-or-
    braced scan (`_scan_bound`): a plain token needs no braces
    (`|_0^oo`), only a bound with its own space or comma does
    (`|_{0}^{n + 1}`), length alone never forces braces. Shared by
    `_expand_integrate_at` (attached directly to a parenthesized call)
    and `_expand_integral_bare` (chained after each bracket-free
    differential marker)."""
    pm = _EVAL_BAR_PREFIX.match(text, pos)
    if pm is None:
        return None
    lo_scan = _scan_bound(text, pm.end())
    if lo_scan is None:
        return None
    lo, k = lo_scan
    if k >= len(text) or text[k] != "^":
        return None
    hi_scan = _scan_bound(text, k + 1)
    if hi_scan is None:
        return None
    hi, end = hi_scan
    return lo, hi, end


def _expand_integrate_at(text: str) -> str:
    """`integrate(f(x), x)|_{a}^{b}` (or bare-token bounds, `|_a^b`, see
    `_scan_bar_bounds`) -> the already-existing 4-argument bounded form
    `integrate(f(x), x, a, b)`, pure sugar, matching LaTeX's own
    `\\big|_a^b` convention for a definite integral's bounds; the
    bounded form was already fully built, this just spells it the way a
    reader used to that convention would expect. A single-argument call
    (`integrate(f(x))|_a^b`, the variable omitted entirely) infers it
    from that argument's own single free name
    (`_extract_single_free_identifier`), the same inference `d(<expr>)`
    and prime notation both use. Left alone wherever the `|_...^...`
    suffix isn't there, or (for the single-argument shape) wherever
    that inference doesn't resolve."""
    def rewrite(m, args, call_end):
        bounds = _scan_bar_bounds(text, call_end)
        if bounds is None:
            return None
        lo, hi, end = bounds
        if len(_split_commas(args)) == 1:
            var = _extract_single_free_identifier(args)
            if var is None:
                return None
            return f"integrate({args}, {var}, {lo}, {hi})", end
        return f"integrate({args}, {lo}, {hi})", end

    return _rewrite_balanced_calls(text, _INTEGRATE_NAME, rewrite)


def _expand_integral_bare(text: str) -> str:
    """`integral f(x,y) dx|_b^a dy|_b2^a2` -> the flat call
    `integrate(f(x,y), x, b, a, y, b2, a2)`, sympy's own native support
    for repeating `(var, lo, hi)` triples in one `integrate()` call
    (equivalent to nesting: `_law_to_sympy` passes them straight
    through). `integral f(x)|_0^oo` (the differential marker omitted
    entirely) infers the sole variable from `f(x)`'s own single free
    name, the same inference `d(<expr>)`/prime notation/`integrate`'s
    own single-argument form all use. Each `d<var>|_{lo}^{hi}` segment
    is applied in the order written, left to right (leftmost is the
    innermost/first-performed integration). `integral(` (immediately
    followed by a paren, no space) is left alone here; that is the
    ordinary call-form spelling, converted to `integrate(` by a plain
    substitution elsewhere in `normalize()`. Left alone wherever no
    bound-bar is found at all, or wherever the variable-omitted
    inference fails, downstream parsing rejects the untouched text
    with its own error, same as every other sugar in this module."""
    def rewrite(m):
        after = m.end()
        if after < len(text) and text[after] == "(":
            return None
        expr, end = _scan_trailing_expr(text, after, stop=_INTEGRAL_EXPR_STOP)
        if not expr or end >= len(text):
            return None
        if text[end] == "|":
            var = _extract_single_free_identifier(expr)
            if var is None:
                return None
            bounds = _scan_bar_bounds(text, end)
            if bounds is None:
                return None
            lo, hi, bar_end = bounds
            return f"integrate({expr}, {var}, {lo}, {hi})", bar_end
        triples: list[tuple[str, str, str]] = []
        pos = end
        while True:
            dm = _D_MARKER_BAR.match(text, pos)
            if dm is None:
                break
            bounds = _scan_bar_bounds(text, dm.end())
            if bounds is None:
                break
            lo, hi, bar_end = bounds
            triples.append((dm.group(1), lo, hi))
            pos = bar_end
        if not triples:
            return None
        triple_args = ", ".join(f"{v}, {lo}, {hi}" for v, lo, hi in triples)
        return f"integrate({expr}, {triple_args})", pos

    return _rewrite_matches(text, _INTEGRAL_WORD, rewrite)


def apply_unicode_synonyms(text: str) -> str:
    """The `_UNICODE` substitution table (Unicode/LaTeX-command math
    symbols, including the backslash Greek-letter names, to this
    grammar's own canonical spelling) applied on its own, factored out
    of `normalize()` so `extract_let_bindings()` can call it directly on
    raw text, before its own `\\w+`-based name matching runs. A
    backslash-spelled binding name (`let \\alpha = alpha, ...`) needs
    its leading backslash resolved to a plain Unicode letter for
    `\\w+` to recognize it as a name at all, and `extract_let_bindings`
    parses raw text ahead of `normalize()`'s own call to this same
    substitution; calling it here first is what makes that binding
    name visible in time. Idempotent, like `normalize()` itself: none
    of this table's own output strings are also keys elsewhere in it,
    so calling it twice (once here, once inside `normalize()`'s own
    call) on the same text is harmless. Also converts a run of Unicode
    superscript digits to `^<digits>` (`_SUPERSCRIPT_RUN`), the same
    idempotence holds, since a superscript digit is never itself one of
    this table's keys or values. Collapses any `∫`/`∬`/`∭` run (see
    `_collapse_integral_marks`) *first*, strictly before that
    superscript-digit conversion: a decorated `∫₀¹` has to become the
    plain word `integral` before its own superscript half could
    otherwise be converted to `^<digits>` and glued onto `integral`
    with no separator."""
    def substitute(masked: str) -> str:
        masked = _desuperscript_spaces(masked)
        masked = _radical_to_call(_collapse_integral_marks(masked))
        masked = _LATEX_COMMAND.sub(
            lambda m: _LATEX_COMMANDS.get(m.group(0), m.group(0)), masked)
        for sym, repl in _UNICODE.items():
            if sym not in _LATEX_COMMANDS:
                masked = masked.replace(sym, repl)
        return _SUPERSCRIPT_RUN.sub(
            lambda m: "^" + m.group(0).replace("⁻", "-").translate(
                _SUPERSCRIPT_TO_DIGIT),
            masked)

    return outside_strings(substitute, text)


def normalize(text: str) -> str:
    """Map any accepted spelling of a law to its canonical form: `let
    <bindings> in ...` expanded first; `lim`'s arrow/bracket-free sugar
    (the variable always named explicitly); `Sum(f(i))_{i=0}^n`/`Prod(...)_{..}^..`
    subscript/superscript sugar (`Σ`/`Π` synonyms folded in first);
    `∂(...)` (call-form alias for `d(...)`) resolved; prime notation
    (`f'(x)`) and `d(<expr>)`'s own variable-omitted inference;
    `d(...)@{v=val, ...}`/`at {...}` (differentiate, then substitute);
    `∫`/`integral` (synonyms for `integrate`) folded
    in, then `integrate`'s own bracket-free and `|_{lo}^{hi}`
    evaluation-bar sugar; Unicode math symbols to ASCII; `||x||`/`|x|`/
    `⌊x⌋`/`⌈x⌉` to `norm(x)`/`abs(x)`/`floor(x)`/`ceil(x)` (double bars
    matched before single, so they can never be misread as nested
    single bars); `^` to `**`. Idempotent. `extract_diff_fraction_sugar()`
    (the `d(<expr>/d<var>)` fraction spelling) and `extract_let_bindings()`
    are separate, `claim()`-level passes that run on raw text *before*
    this function ever sees it, see their own docstrings.

    `∂(...)` is deliberately only a call-prefix alias, not a
    traditional, *unscoped* `∂f/∂x` fraction spelling: that notation is
    ambiguous with ordinary division at the text level (`df/dx` reads
    as `(d*f)/(d*x)`, not a derivative) with no calling context to
    disambiguate it, and isn't attempted here, the fraction spelling
    this grammar *does* accept is always scoped to inside a `d(...)`
    call (`extract_diff_fraction_sugar`, run before this function). The
    `Sum`/`Prod` subscript sugar, and the `d`/`integrate` evaluation-bar
    sugars, are all expanded before the trailing `^` -> `**` power
    swap, so their own `^` is consumed here and never reaches that
    generic substitution, and before the abs/norm bar substitutions
    below, since an evaluation bar's own literal `|` would otherwise
    risk pairing up with an unrelated `|x|` elsewhere in the same
    claim. `∂` is resolved to `d` before any of `d`'s own sugar runs, so
    `∂(f(x,y), x)@{x=a}` is recognized the same as the `d(...)`
    spelling, not just the literal `d(` one.

    The pipeline itself is `_NORMALIZE_PASSES` below: a flat, ordered
    tuple of text -> text passes, each one sugar. Order carries real
    meaning (the tuple's own comments state each constraint); a new
    sugar is added as a new entry in the right position, never by
    editing an existing pass."""
    def run_passes(masked: str) -> str:
        for sugar_pass in _NORMALIZE_PASSES:
            masked = sugar_pass(masked)
        return masked

    return outside_strings(run_passes, text)


def _replace_sigma_pi(text: str) -> str:
    """Σ/Π -> the word forms _expand_sum_prod recognizes, before it
    runs, so `Σ(f(i))_{i=0}^n` gets the identical subscript/
    superscript sugar `Sum(f(i))_{i=0}^n` already has, not just the
    bare 4-argument call form. Unconditional: Σ/Π have no other meaning
    in this grammar (see _UNICODE's own comment on why they're excluded
    from the plain-variable Greek letter table)."""
    return text.replace("Σ", "Sum").replace("Π", "Prod")


def _replace_partial_call(text: str) -> str:
    """`∂(` -> `d(` before any of `d`'s own sugar runs, so
    `∂(f(x,y), x)@{x=a}` is recognized the same as the `d(...)`
    spelling. Only the call-prefix alias, see normalize()'s docstring
    on why the unscoped `∂f/∂x` fraction spelling is not attempted."""
    return text.replace("∂(", "d(")


def _fold_dim_sugar(text: str) -> str:
    """`len(...)`/`rows(...)` -> `dim(..., 0)` and `cols(...)` ->
    `dim(..., 1)`: dimension access has ONE canonical spelling, the
    axis-explicit `dim`, and the three familiar words are sugar for
    it. The words are grammar vocabulary here, the way `len` always
    was: a bound function of the same name is not referenceable in
    claim text."""
    for name, axis in (("len", 0), ("rows", 0), ("cols", 1)):
        text = _rewrite_balanced_calls(
            text, re.compile(rf"\b{name}\("),
            lambda m, args, call_end, axis=axis: f"dim({args}, {axis})")
    return text


def _replace_pv_call(text: str) -> str:
    """`P.V.(` -> `cauchy_pv(`: the principal-value operator renders
    and reads as the traditional `P.V.` spelling, but that text isn't
    valid Python call syntax, so the canonical internal form is
    `cauchy_pv(`; deliberately NOT `PV(`, which stays an ordinary
    name (a present-value function's own parameter is commonly called
    PV, and a reserved meaning there would collide)."""
    return re.sub(r"P\.V\.\s*\(", "cauchy_pv(", text)


_SPACED_PREDICATES = {
    "is defined": "is_defined",
    "is pole safe": "is_pole_safe",
    "is builtin safe": "is_builtin_safe",
    "is missing safe": "is_missing_safe",
    "is extremity safe": "is_extremity_safe",
    "is representation safe": "is_representation_safe",
    "is empty safe": "is_empty_safe",
    "is arbitrary input safe": "is_arbitrary_input_safe",
    "is compendium safe": "is_compendium_safe",
    "excluded outside domain": "excluded_outside_domain",
}


def _spaced_predicate_calls(text: str) -> str:
    """`is defined(f)` -> `is_defined(f)` (and the other is_* predicate
    spellings): the unicode rendering displays these names with spaces;
    the way they read, so the spaced form must parse back. Only
    the known predicate vocabulary, only in call position: an ordinary
    variable named `defined` is untouched."""
    for spaced, joined in _SPACED_PREDICATES.items():
        text = re.sub(rf"\b{spaced}\s*\(", f"{joined}(", text)
    return text


def _integral_word_to_call(text: str) -> str:
    """Any leftover call-form `integral(...)` (not consumed by the
    bracket-free shape, which runs first) -> `integrate(` directly."""
    return re.sub(r"\bintegral\(", "integrate(", text)


_IMAG_SUFFIX = re.compile(r"(?<![\w.])((?:\d+\.?\d*|\.\d+))i\b")
_IMAG_UNICODE_SUFFIX = re.compile(r"(?<![\w.])((?:\d+\.?\d*|\.\d+))\s*[ⅈ𝑖]")
_IMAG_UNICODE_BARE = re.compile(r"[ⅈ𝑖]")


def _imaginary_suffix_to_j(text: str) -> str:
    """`2i`/`1.5i` -> `2j`/`1.5j`: the mathematical spelling of an
    imaginary literal normalized to the Python one the parser reads
    natively. Only a number token immediately followed by `i` matches
    (that character sequence is not valid Python any other way), so a
    bare `i` stays an ordinary variable and identifiers are untouched.
    The unicode `ⅈ` and italic `𝑖` also normalize here: as a number's
    suffix they become the j-suffix (`3ⅈ` is three times the unit, so
    `3j`), standing alone they are the literal `1j`."""
    text = _IMAG_UNICODE_SUFFIX.sub(r"\1j", text)
    text = _IMAG_UNICODE_BARE.sub("1j", text)
    return _IMAG_SUFFIX.sub(r"\1j", text)


def _caret_to_power(text: str) -> str:
    """`^` -> `**`, last of all: the Sum/Prod subscript sugar and the
    d/integrate evaluation-bar sugars consume their own `^` first, so
    it never reaches this generic swap."""
    return text.replace("**", "^").replace("^", "**")


_EQUIV_WORD = re.compile(
    r"([\w)\]])\s+equiv\s+(?!(?:in|be)\b|∈)(?=[\w(\[])")


def _equiv_alias(text: str) -> str:
    """`f equiv g` -> `f =:= g`: the word alias for the equivalence
    relation (canonical ascii spelling =:=, unicode ≡). Only the infix
    word between two operands is the relation, so a parameter named
    `equiv` (`for equiv in [0, 1]`, `f(equiv)`) stays a name."""
    return _EQUIV_WORD.sub(r"\1 =:= ", text)


def _lim_arrow(text: str) -> str:
    return _LIM_ARROW.sub(r"\1\2, \3\4", text)


_LIM_CALL = re.compile(r"\blim\(")
# a one-sided limit's direction: a trailing sign on the point
# (`lim(f(x), x, 0+)`, after the arrow sugar also `x -> 0-`, `x -> a+`)
#, the conventional 0^+/0^- reading, caret optional. Only a sign that
# trails a value character (a word character or closing bracket, never
# an operator) counts, so an ordinary `a+b` point is untouched.
_LIM_POINT_SIGN = re.compile(r"^(.*[\w)\]])\s*\^?\s*([+-])\s*$")


def _lim_direction(text: str) -> str:
    """`lim(f(x), x, 0+)` / `lim(f(x), x, 0^-)` -> the 4-argument form
    `lim(f(x), x, 0, '+')`: the direction becomes a quoted argument so
    the point stays a plain parseable expression. Runs after the arrow
    and bracket-free lim sugars, which produce the 3-argument call this
    reads. A call whose point carries no trailing sign, or with any
    other argument count, is left alone."""
    out, pos = [], 0
    while True:
        found = _find_balanced_call(text, _LIM_CALL, pos)
        if found is None:
            out.append(text[pos:])
            return "".join(out)
        m, inner, call_end = found
        args, depth, start = [], 0, 0
        for i, ch in enumerate(inner):
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "," and depth == 0:
                args.append(inner[start:i])
                start = i + 1
        args.append(inner[start:])
        sign = _LIM_POINT_SIGN.match(args[2]) if len(args) == 3 else None
        if sign is not None:
            call = f"lim({args[0]},{args[1]},{sign.group(1)}, '{sign.group(2)}')"
            out.append(text[pos:m.start()] + call)
        else:
            out.append(text[pos:call_end])
        pos = call_end


# a bar is OPENING when what precedes it cannot end an operand: the
# start of the text, an operator, an opening bracket, a comma, another
# opening bar, or one of these words
_BAR_OPENING_CHARS = frozenset("([{,+-*/^%=<>&@~:")
_BAR_OPENING_WORDS = frozenset({"not", "and", "or", "in", "if", "else",
                                "is", "return", "lambda"})


def _bar_pairs(text: str) -> "list[tuple[int, int]] | None":
    """Intent:
        The matched `|...|` pairs in `text` as (open, close) index
        pairs, or None when the bars do not pair up.

    Notes:
        A bar opens when what precedes it cannot end an operand (see
        `_BAR_OPENING_CHARS`/`_BAR_OPENING_WORDS`) and closes otherwise,
        so `|x - |y||` and `|x| + |y|` both read the way they are
        written.
    """
    stack: list = []
    pairs: list = []
    kinds: dict = {}
    for i, ch in enumerate(text):
        if ch != "|":
            continue
        j = i - 1
        while j >= 0 and text[j] == " ":
            j -= 1
        if j < 0:
            opening = True
        elif text[j] == "|":
            opening = kinds[j] == "open"
        elif text[j] in _BAR_OPENING_CHARS:
            opening = True
        elif text[j].isalnum() or text[j] == "_":
            k = j
            while k >= 0 and (text[k].isalnum() or text[k] == "_"):
                k -= 1
            opening = text[k + 1:j + 1] in _BAR_OPENING_WORDS
        else:
            opening = False
        if opening:
            kinds[i] = "open"
            stack.append(i)
        else:
            if not stack:
                return None
            kinds[i] = "close"
            pairs.append((stack.pop(), i))
    return None if stack else pairs


def _fold_bars(text: str) -> str:
    """`|expr|` -> `abs(expr)` for any expression between the bars, and
    `||expr||` -> `norm(expr)`: a pair whose content is exactly one
    further pair reads as a norm, so `||a| - |b||` (content not a
    single pair) stays an absolute value of a difference. Text whose
    bars do not pair up is returned unchanged for the claim parser to
    refuse. A matrix operand turns `abs` into `det` later, by type."""
    if "|" not in text:
        return text
    pairs = _bar_pairs(text)
    if not pairs:
        return text
    close_of = dict(pairs)
    replace: dict = {}
    for o, c in pairs:
        if o in replace:
            continue
        inner = close_of.get(o + 1)
        if inner is not None and inner == c - 1:
            replace[o], replace[c] = "norm(", ")"
            replace[o + 1] = replace[c - 1] = ""
        else:
            replace[o], replace[c] = "abs(", ")"
    return "".join(replace.get(i, ch) for i, ch in enumerate(text))


def _fold_brackets(text: str, opening: str, closing: str, name: str) -> str:
    """`⌊expr⌋` -> `floor(expr)` (and ceiling the same way) for any
    expression, the opening and closing marks being distinct; text
    whose marks do not balance is returned unchanged."""
    if opening not in text:
        return text
    depth = 0
    for ch in text:
        depth += (ch == opening) - (ch == closing)
        if depth < 0:
            return text
    if depth:
        return text
    return text.replace(opening, f"{name}(").replace(closing, ")")


def _floor_bars(text: str) -> str:
    return _fold_brackets(text, "⌊", "⌋", "floor")


def _ceil_bars(text: str) -> str:
    return _fold_brackets(text, "⌈", "⌉", "ceil")


# normalize()'s pipeline as data: applied top to bottom, order
# load-bearing throughout. `let` first (its bindings' names must be
# substituted before any sugar reads the text); the lim/Sum/Prod/d/
# integral families each desugar before the generic unicode-synonym
# pass; every bar sugar (`|_a^b` evaluation bars via the integral
# family) resolves before the abs/norm bar substitutions, so an
# evaluation bar's own literal `|` can never pair with an unrelated
# `|x|`; `^ -> **` dead last, after every sugar that consumes a `^` of
# its own.

_POSTFIX_FACTORIAL_ATOM = re.compile(
    r"(?<![\w!])([A-Za-z_]\w*|\d+(?:\.\d+)?)!(?![=!])")


def _postfix_factorial(text: str) -> str:
    """`n!`/`5!`/`(n-1)!` -> `factorial(...)`: the traditional postfix
    spelling, folded to the call form the rest of the pipeline (and
    both adjudication routes) already understand. `!=` is never
    touched (the `!` is followed by `=`), and `n!!` (double factorial,
    a different function) is deliberately left alone rather than
    misread as factorial(factorial(n)); it surfaces as an ordinary
    parse error instead. A parenthesized operand keeps exactly its
    inner expression: `(n-1)!` becomes `factorial(n-1)`."""
    # parenthesized operands first, innermost-last via repeated scan:
    # each `)!` wraps its own balanced group
    while True:
        idx = text.find(")!")
        if idx == -1 or text[idx + 2:idx + 3] in ("=", "!"):
            # a lone trailing `)!=` / `)!!` would loop forever; the
            # find below skips only the first hit, so scan onward
            nxt = text.find(")!", idx + 1) if idx != -1 else -1
            while nxt != -1 and text[nxt + 2:nxt + 3] in ("=", "!"):
                nxt = text.find(")!", nxt + 1)
            if nxt == -1:
                break
            idx = nxt
        depth = 0
        start = None
        for j in range(idx, -1, -1):
            if text[j] == ")":
                depth += 1
            elif text[j] == "(":
                depth -= 1
                if depth == 0:
                    start = j
                    break
        if start is None:
            break
        # a call operand (`abs(x)!`) keeps its name inside the wrap:
        # factorial(abs(x)), never abs glued to factorial(x)
        k = start
        while k > 0 and (text[k - 1].isalnum() or text[k - 1] == "_"):
            k -= 1
        if k < start:
            inner = text[k:idx + 1]
        else:
            inner = text[start + 1:idx]
        text = text[:k] + "factorial(" + inner + ")" + text[idx + 2:]
    return _POSTFIX_FACTORIAL_ATOM.sub(r"factorial(\1)", text)

_NORMALIZE_PASSES: tuple = (
    _expand_let,
    _equiv_alias,
    _lim_arrow,
    _expand_lim_bare,
    _lim_direction,
    _replace_sigma_pi,
    _expand_sum_prod,
    _replace_partial_call,
    _replace_pv_call,
    _fold_dim_sugar,
    _spaced_predicate_calls,
    _expand_prime,
    _expand_d_single_var,
    _expand_d_at,
    # `∫`/`∬`/`∭` -> the word `integral`: a whole run of the symbols
    # collapses to ONE trigger (`∫∫(` is not `integralintegral(`); the
    # differential markers/bound-bars that follow determine how many
    # variables are integrated over. Bracket-free form expands next
    # (it looks for `integral` specifically, not `integrate`), then the
    # leftover call form folds into `integrate(`.
    _collapse_integral_marks,
    _expand_integral_bare,
    _integral_word_to_call,
    _expand_integrate_at,
    apply_unicode_synonyms,
    _fold_bars,
    _floor_bars,
    _ceil_bars,
    # after the bar sugars (so `|x|!` sees the already-folded
    # `abs(x)!`), before the power swap
    _postfix_factorial,
    _caret_to_power,
    _imaginary_suffix_to_j,
)




_ASSUMING_PREFIX = re.compile(r"^\s*assuming\s+", re.DOTALL)


def extract_assuming_clause(text: str) -> tuple[str | None, str]:
    """Peels a leading `assuming <raw>,` segment off `text`; one
    top-level, comma-terminated segment, itself free to contain further
    `and`-joined conditions (`assuming X is proven and Y holds,`) since
    those never introduce a *top-level* comma of their own. Returns
    `(None, text)` unchanged when `text` doesn't start with `assuming`.

    The segment is returned verbatim, keyword included; this function
    does no interpretation. `conjecture._interpret_assumption` reads it
    at adjudication time, where the sibling claims and the function's
    own facts are in hand, a relation constrains the region, a
    `<name> holds`/`is proven` reference consults that claim's
    verdict."""
    if _ASSUMING_PREFIX.match(text) is None:
        return None, text
    segments = _split_commas(text)
    return _canonical_assuming(segments[0].strip()), ", ".join(segments[1:]).strip()


#: `is_defined(f)` reads as a call, `f is defined` as the claim it
#: stands for. Both are accepted input; the second is the stored and
#: rendered spelling, so the two never produce different statements,
#: different fingerprints, or two claims where there is one.
_DEFINED_CALL = re.compile(r"\bis[_ ]defined\(\s*([A-Za-z_]\w*)\s*\)")


def _canonical_assuming(clause: str) -> str:
    """One spelling per premise, so an authored `assuming is_defined(f)`
    and an authored `assuming f is defined` are the same claim
    everywhere downstream, same statement, same fingerprint. The
    dimension sugar (`len`/`rows`/`cols`) folds to canonical `dim`
    here too, for the same reason: a length premise has one identity
    however it was spelled."""
    return _fold_dim_sugar(_DEFINED_CALL.sub(r"\1 is defined", clause))


_OUTCOME_MARKER = re.compile(r"=>|-->|⟹|\\implies")


def extract_outcome_clause(text: str) -> tuple[str | None, str]:
    """Stub, no semantics yet: splits `text` at a top-level `=>`
    (or one of its
    accepted spellings, `-->`/`⟹`/`\\implies`, matched directly here
    rather than relying on normalize() to have already unified them
    first, so this can run on raw text before let/for extraction, the
    same claim.grammar staging every other section already has to
    respect), capturing everything after it verbatim as the outcome
    clause. Depth-aware the same way `_split_commas` is: a marker
    nested inside `(...)`/`[...]`/`{...}` is never mistaken for this
    marker, so a future claim quoting one inside, say, a string or
    nested call is safe. Returns `(None, text)` unchanged when no
    top-level marker is found."""
    for m in _OUTCOME_MARKER.finditer(text):
        prefix = text[:m.start()]
        depth = (prefix.count("(") + prefix.count("[") + prefix.count("{")
                - prefix.count(")") - prefix.count("]") - prefix.count("}"))
        if depth == 0 and re.match(r"\s*self\.", text[m.end():]):
            # only an outcome-shaped right side (`=> self.<claim> ...`,
            # the documented grammar) is an outcome clause, a
            # top-level `-->` with any other right side belongs to the
            # text it sits in (an `assuming <name> --> <region>` pin
            # renders exactly that shape)
            return text[m.end():].strip(), prefix.strip()
    return None, text


def _split_top_level(text: str, tokens: tuple) -> "tuple | None":
    """Intent:
        (lhs, token, rhs) at the first occurrence of any token OUTSIDE
        every bracket pair, so a comparison inside parentheses (a
        generator expression's filter, a call argument) can never be
        mistaken for the law's own relation. None when no token occurs
        at the top level. A token inside a quoted literal is data and
        never splits.
    """
    masked, literals = mask_strings(text)
    depth = 0
    for i, ch in enumerate(masked):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0:
            for tok in tokens:
                if masked.startswith(tok, i):
                    return (unmask_strings(masked[:i], literals), tok,
                            unmask_strings(masked[i + len(tok):], literals))
    return None


def split_relation(law: str) -> tuple[str, str, str]:
    """Split a normalized law into (lhs, relation, rhs), at the first
    relation OUTSIDE every bracket pair. A single `=` reads as `==`.
    A law whose only comparison sits inside parentheses (an
    `all(f(v) >= 0 for v in xs)` shape) has no relation of its own and
    says so honestly; comprehensions are not claim syntax; quantify
    the element domain or use Sum(expr, var, lo, hi)."""
    text = law.strip()
    hit = _split_top_level(text, RELATIONS)
    if hit is not None:
        lhs, rel, rhs = hit
        return lhs.strip(), rel, rhs.strip()
    hit = _split_top_level(text, ("=",))
    if hit is not None:
        lhs, _tok, rhs = hit
        return lhs.strip(), "==", rhs.strip()
    if any(rel in text for rel in RELATIONS):
        raise NoRelation(
            f"the only comparison in {law!r} sits inside parentheses, "
            f"a comprehension or quantified expression is not claim "
            f"syntax; quantify the element domain (a `for xs in "
            f"[lo, hi], ...` element bound) or state the sum with "
            f"Sum(expr, var, lo, hi)")
    raise NoRelation(f"no relation (==, !=, <=, >=, <, >) in {law!r}")


_AST_REL = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
            ast.Eq: "==", ast.NotEq: "!="}


def split_relation_chain(law: str) -> list[tuple[str, str, str]]:
    """Intent:
        A normalized law as its chain of pairwise relation links: one
        (lhs, relation, rhs) triple for an ordinary claim, and one per
        adjacent operator pair for a chained comparison
        (`a <= b <= c` -> [(a, <=, b), (b, <=, c)]). The links are a
        conjunction; the claim holds iff every link does.

    Notes:
        A single-relation law delegates to `split_relation` byte for
        byte (including the bare `=` -> `==` reading), so every existing
        caller is unaffected. A chain is recognized only via a
        well-formed `ast.Compare` with more than one operator; `==`/`!=`
        inside a chain is refused (a chained equality is not this
        grammar's shape). Middle terms are shared between adjacent links
        and rendered once via `ast.unparse`.
    """
    text = law.strip()
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        # not a parseable expression (e.g. a bare `=`): the string
        # splitter is the single-relation authority
        return [split_relation(text)]
    if not isinstance(node, ast.Compare) or len(node.ops) < 2:
        return [split_relation(text)]
    if any(type(op) in (ast.Eq, ast.NotEq) for op in node.ops):
        raise NoRelation(
            f"a chained comparison must use only ordering relations "
            f"(<, <=, >, >=), not == or != in {law!r}")
    if any(type(op) not in _AST_REL for op in node.ops):
        raise NoRelation(f"unsupported comparison operator in {law!r}")
    terms = [node.left, *node.comparators]
    return [(ast.unparse(terms[i]), _AST_REL[type(node.ops[i])],
             ast.unparse(terms[i + 1])) for i in range(len(node.ops))]


def _verbatim_atom(node: ast.AST):
    """A subtree with no sympy model (a subscript like `x[-1]`, a
    string literal, an unknown call), kept as one opaque atom whose
    name is its exact source spelling. The printer emits a Symbol's
    name verbatim, so the construct renders as itself and re-parses to
    itself: the renderer is total by preservation, never by refusal.
    Rendering is spelling, not validation; what such a subtree means
    is the adjudicator's question, and two atoms compare equal exactly
    when their spellings do.

    A truth-valued subtree (a comparison, a boolean connective) keeps
    its parentheses: `ast.unparse` strips them as redundant, but in
    claim text they are load-bearing, `f(x) = (a <= b)` reparses as one
    relation with a boolean value, `f(x) = a <= b` re-splits at the
    first relation and means something else."""
    text = ast.unparse(node)
    if isinstance(node, (ast.Compare, ast.BoolOp)):
        text = f"({text})"
    return sympy.Symbol(text, real=True)


def _node_to_sympy(node: ast.AST, funcs: frozenset = frozenset({"f"}),
                   matrix_names: frozenset = frozenset()):
    """Convert a law-expression AST node to sympy with every bound function
    letter (`f` by default; `g`, `h`, ... when a claim binds them) left
    uninterpreted, enough structure to render, no lifting required.

    `matrix_names` are the parameter names a caller has found to denote
    matrices (see `_matrix_names`); each is lifted to a
    `sympy.MatrixSymbol` so the matrix vocabulary (`A.T`, `A @ B`,
    `det`/`inv`/`trace`/`transpose`, `I(n)`) renders through sympy's own
    matrix printing. Empty (the default) leaves every existing caller's
    scalar reading byte-for-byte unchanged."""
    if isinstance(node, ast.Expression):
        return _node_to_sympy(node.body, funcs, matrix_names)
    if matrix_names:
        if isinstance(node, ast.Attribute) and node.attr == "T":
            return sympy.Transpose(
                _node_to_sympy(node.value, funcs, matrix_names))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.MatMult):
            return (_node_to_sympy(node.left, funcs, matrix_names)
                    * _node_to_sympy(node.right, funcs, matrix_names))
    if isinstance(node, ast.Constant):
        if isinstance(node.value, complex) and not isinstance(node.value, (int, float)):
            v = node.value
            return (sympy.Rational(str(v.real)) if v.real else sympy.Integer(0)) \
                + sympy.I * sympy.Rational(str(v.imag))
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            return _verbatim_atom(node)
        return sympy.sympify(node.value)
    if isinstance(node, ast.Name):
        # deliberately no reserved-name check here: this function has no
        # concept of a specific function's real parameter names (a bare
        # `to_canonical`/`render_law_expr` call isn't tied to any one
        # function), so it can't safely tell "d used as a genuine
        # misspecification" apart from "d used because some function's
        # own real parameter happens to be named d"; that distinction
        # needs `param_names`, which only `check_conjectures()`'s own
        # early check, `_validate`, and `_law_to_sympy` actually have.
        # This is fine: by the time text reaches this function, it's
        # either already-adjudicated Conjecture text (misspecification
        # would have been caught earlier) or a caller's own direct,
        # exploratory use, not itself a claim-validation surface.
        if node.id in _MATH_ATTRS:
            return _MATH_ATTRS[node.id]
        if node.id in matrix_names:
            return sympy.MatrixSymbol(node.id, _MATRIX_RENDER_DIM,
                                      _MATRIX_RENDER_DIM)
        return sympy.Symbol(node.id, real=True)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _node_to_sympy(node.operand, funcs, matrix_names)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](
            _node_to_sympy(node.left, funcs, matrix_names),
            _node_to_sympy(node.right, funcs, matrix_names))
    if isinstance(node, ast.Call):
        fname = node.func.id if isinstance(node.func, ast.Name) else None
        arg_nodes = node.args
        if (fname == "lim" and len(arg_nodes) == 4
                and isinstance(arg_nodes[3], ast.Constant)):
            # the one-sided direction argument is a bare string, not an
            # expression; held back here, read by _render_lim_call
            # straight off the node
            arg_nodes = arg_nodes[:3]
        args = [_node_to_sympy(a, funcs, matrix_names) for a in arg_nodes]
        if matrix_names and len(args) == 1 and fname in _MATRIX_RENDER_CALLS:
            return _MATRIX_RENDER_CALLS[fname](args[0])
        special = _SPECIAL_RENDER_CALLS.get(fname)
        if special is not None:
            rendered = special(node, args)
            if rendered is not None:
                return rendered
            # an arity the special form doesn't define falls through to
            # the ordinary bound-function/vocabulary lookups below, the
            # same as any other unrecognized call.
        if fname in funcs:
            return sympy.Function(fname)(*args)
        name = _call_name(node)
        if name in ("min", "max") and len(args) == 1:
            # `min(xs)` over a SEQUENCE is an aggregation, a fold over
            # the elements. sympy's Min/Max are the n-ary SCALAR
            # versions and collapse at arity one (`Min(x)` is `x`),
            # which would canonicalise the claim into `x <= f(x)`: a
            # different, elementwise, usually false assertion. The
            # record stores the canonical text, so the collapse would
            # make a record state something nobody adjudicated. Held
            # uninterpreted instead, which prints back as written.
            return sympy.Function(name)(*args)
        if name == "norm":
            # a norm and an absolute value agree on scalars but not on
            # vectors, so `||x||` keeps its own name in claim text
            return sympy.Function(name)(*args)
        if name in _SYMPY_FUNCS:
            return _SYMPY_FUNCS[name](*args)
    return _verbatim_atom(node)


def _render_d_call(node, args):
    if len(args) < 2:
        return None

    def _diff_symbol(k):
        # A differentiation (or evaluation-point) variable is always a
        # bare parameter name, so force it to a Symbol from its own name,
        # never the value `_node_to_sympy` resolved the bare token to. A
        # parameter literally named `e` (eccentricity), `pi`, or `oo` is
        # then the variable itself, not the math constant: sympy rejects
        # `Derivative(expr, E)` outright, which is the crash this avoids.
        a = node.args[k]
        return sympy.Symbol(a.id, real=True) if isinstance(a, ast.Name) else args[k]

    # `_expand_d_at` rewrites `d(...)@{v=val, ...}` into this same call
    # with a private `__at__` sentinel name separating the
    # differentiation variables from the trailing (var, value)
    # substitution pairs (see that function's own docstring),
    # reconstructed here as an unevaluated `sympy.Subs` (never actually
    # substituted/evaluated, since this is a rendering path, not the
    # derive route's own evaluation of the same sentinel in
    # _law_to_sympy) so `_CanonicalPrinter._print_Subs` can print it
    # back out as `d(...)@{...}` rather than leaking the sentinel name.
    at_idx = next((k for k, a in enumerate(node.args[1:])
                  if isinstance(a, ast.Name) and a.id == _D_AT_SENTINEL), None)
    if at_idx is None:
        diff_args = [_diff_symbol(k) for k in range(1, len(node.args))]
        return sympy.Derivative(args[0], *diff_args)   # unevaluated: ∂-notation
    diff_args = [_diff_symbol(k) for k in range(1, 1 + at_idx)]
    sub_start = 2 + at_idx
    sub_vars = [_diff_symbol(k) for k in range(sub_start, len(node.args), 2)]
    sub_vals = args[sub_start + 1::2]
    deriv = sympy.Derivative(args[0], *diff_args)
    return sympy.Subs(deriv, sub_vars, sub_vals)


def _render_lim_call(node, args):
    if len(args) != 3:
        return None
    if (len(node.args) == 4 and isinstance(node.args[3], ast.Constant)
            and node.args[3].value in ("+", "-")):
        # one-sided form: the direction argument was held back from
        # sympy conversion (a bare string, not an expression) and is
        # read off the AST here; sympy.Limit renders it as 0^+/0^-
        return sympy.Limit(args[0], args[1], args[2], dir=node.args[3].value)
    # sympy's own default direction is "+", so a two-sided limit states
    # "+-" explicitly and stays distinct from the one-sided one
    return sympy.Limit(args[0], args[1], args[2], dir="+-")


def _render_integrate_call(node, args):
    if len(args) == 2:
        return sympy.Integral(args[0], args[1])            # unevaluated: ∫ dx
    if len(args) >= 4 and (len(args) - 1) % 3 == 0:
        # a single 4-argument bound, or (from the bracket-free
        # multivariable sugar) repeating (var, lo, hi) triples,
        # sympy.Integral accepts multiple limit tuples natively, the
        # same way sympy.integrate() does in _law_to_sympy.
        rest = args[1:]
        triples = [tuple(rest[k:k + 3]) for k in range(0, len(rest), 3)]
        return sympy.Integral(args[0], *triples)
    return None


def _render_pv_call(node, args):
    if len(args) != 1 or not isinstance(args[0], sympy.Integral):
        return None
    return sympy.Function("P.V.")(args[0])   # unevaluated: P.V.(∫ ...)


def _render_sum_prod_call(node, args):
    if len(args) != 4:
        return None
    op = sympy.Sum if node.func.id == "Sum" else sympy.Product   # unevaluated
    return op(args[0], (args[1], args[2], args[3]))


# the special call forms of the claim grammar, dispatched by name: each
# handler returns an unevaluated sympy object, or None for an arity the
# form doesn't define (falling through to the ordinary lookups).
_SPECIAL_RENDER_CALLS = {
    "d": _render_d_call,
    "lim": _render_lim_call,
    "integrate": _render_integrate_call,
    "cauchy_pv": _render_pv_call,
    "Sum": _render_sum_prod_call,
    "Prod": _render_sum_prod_call,
}


def parse_raises(law: str) -> tuple[str, str | None] | None:
    """Recognize the raises(...) predicate form (declared-schema.md,
    "Domain is a claim field"): `raises(f(x))` asserts the call raises,
    `raises(f(x), ValueError)` asserts it raises specifically that.
    Returns (call_source, exception_name | None), or None when the law
    isn't a raises predicate at all."""
    try:
        tree = ast.parse(normalize(law).strip(), mode="eval")
    except SyntaxError:
        return None
    node = tree.body
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "raises" and node.args
            and isinstance(node.args[0], ast.Call)):
        return None
    if len(node.args) == 1:
        return ast.unparse(node.args[0]), None
    if len(node.args) == 2 and isinstance(node.args[1], ast.Name):
        return ast.unparse(node.args[0]), node.args[1].id
    return None




def parse_domain_safety(law: str) -> tuple[str, str] | None:
    """Recognize the `is_pole_safe(param)`/`is_builtin_safe(param)`/
    `is_missing_safe(param)` predicate forms: a family-adjudicated fact
    about param's own declared domain, whether it excludes every pole,
    fits a restricted-domain builtin it's passed to, or (for
    `is_missing_safe`) whether the function's runtime behavior on a
    missing input honors the domain's resolved missing-value policy.
    Not ordinary `lhs op rhs` comparison text, same as `raises(...)`.
    Accepts the call form (`is_pole_safe(x)`, the canonical raw
    spelling) and the postfix reading (`x is pole safe`, the preferred
    unicode display, normalize() folds the spaced words first).
    Returns (predicate_name, param), or None when law isn't one of
    these predicates at all."""
    text = normalize(law).strip()
    spellings = "|".join(p.replace("_", "[_ ]")
                         for p in sorted(_domain_safety_predicates()))
    postfix = re.match(rf"^(not\s+)?(.+?)\s+({spellings})$", text)
    if postfix is not None:
        neg, subject, predicate = postfix.groups()
        predicate = predicate.replace(" ", "_")
        prefix = "not " if neg else ""
        subject = subject.strip()
        if subject.isidentifier():
            return prefix + predicate, subject
        # a non-bare subject (`f(A) is symmetric`, `A @ B is symmetric`)
        # is a matrix predicate examining a VALUE; a safety predicate is
        # a fact about the code for one bare argument, never an
        # expression.
        if predicate in _MATRIX_PREDICATES | _OUTPUT_PREDICATES:
            try:
                ast.parse(subject, mode="eval")
            except SyntaxError:
                return None
            return prefix + predicate, subject
        return None
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        return None
    node = tree.body
    negated = ""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        # the grammar not-form: `not is_pole_safe(x)` asserts the
        # predicate's negation (the discovery path's corrected shape).
        negated = "not "
        node = node.operand
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _domain_safety_predicates()
            and len(node.args) == 1 and not node.keywords):
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Name):
        return negated + node.func.id, arg.id
    # a matrix structure predicate may examine an EXPRESSION, not only
    # a bare parameter: `is_symmetric(f(A))` claims the output is
    # symmetric, `is_symmetric(A @ B)` the product is. A safety
    # predicate stays bare-parameter-only (it is a fact about the code
    # for one argument, with nothing to compute).
    if node.func.id in _MATRIX_PREDICATES | _OUTPUT_PREDICATES:
        return negated + node.func.id, ast.unparse(arg)
    return None



def to_latex(law: str, funcs: frozenset = frozenset({"f"})) -> str:
    """Render a full law as LaTeX: `lhs rel rhs`, or the partiality
    notation f(x)↑ for a raises predicate. The matrix vocabulary
    (`A.T`, `A @ B`, `det`/`inv`/`trace`, `I(n)`) renders through sympy's
    matrix printing (`A^{T}`, `|A|`, juxtaposition), decided per law from
    the names `_matrix_names` finds under a matrix operator."""
    def side(src: str, mats: frozenset = frozenset()) -> str:
        tree = ast.parse(src, mode="eval")
        if mats:
            try:
                return sympy.latex(_node_to_sympy(tree, funcs, mats))
            except Exception:
                # a mixed matrix/scalar expression sympy's matrix algebra
                # rejects: fall back to the plain scalar reading, never
                # worse than a render with no matrix awareness at all.
                pass
        return sympy.latex(_node_to_sympy(tree, funcs))
    r = parse_raises(law)
    if r is not None:
        call_src, exc = r
        sub = rf"_{{\mathrm{{{exc}}}}}" if exc else ""
        return rf"{side(call_src)}\,\uparrow{sub}"
    ds = parse_domain_safety(law)
    if ds is not None:
        predicate, param = ds
        return rf"\mathrm{{{predicate}}}({param})"
    lhs, rel, rhs = split_relation(normalize(law))
    mats = (_matrix_names(ast.parse(lhs, mode="eval"))
            | _matrix_names(ast.parse(rhs, mode="eval")))
    return f"{side(lhs, mats)} {_REL_LATEX[rel]} {side(rhs, mats)}"


def _integral_bound_marker(limit: tuple) -> str:
    """`(var, lo, hi)` -> a subscript-lower/superscript-upper decoration
    for `_print_Integral`'s own `∫`, when both bounds are plain sympy
    integers, `""` for an indefinite limit (`(var,)`, no bounds at
    all) or a definite one with any non-integer bound (a symbol, `oo`,
    a fraction), where there's no reliable digit-only spelling to
    attach."""
    if len(limit) != 3:
        return ""
    lo, hi = limit[1], limit[2]
    if not (isinstance(lo, sympy.Integer) and isinstance(hi, sympy.Integer)):
        return ""
    lo_text = ("₋" if lo < 0 else "") + str(abs(int(lo))).translate(_DIGIT_TO_SUBSCRIPT)
    hi_text = ("⁻" if hi < 0 else "") + str(abs(int(hi))).translate(_DIGIT_TO_SUPERSCRIPT)
    return lo_text + hi_text


class _CanonicalPrinter(StrPrinter):
    """sympy's own `StrPrinter`, overridden node-by-node wherever mathema's
    claim-grammar spelling differs from sympy's default `str()`, the
    literal inverse of `_node_to_sympy`'s vocabulary (`_SYMPY_FUNCS`/
    `_MATH_ATTRS`, `_math_vocab.py`). Everything `StrPrinter` already gets
    right unassisted (`sqrt(x)`, `x - y`, `x**2`, a bare `f(x)` for an
    uninterpreted `Function`) is left untouched, reimplementing N-ary
    `Add`/`Mul` flattening, subtraction/division reconstruction, and
    precedence-aware parenthesization from scratch would just be redoing
    real, already-correct work."""
    def __init__(self, funcs, unicode: bool = True, suppress_glyphs: frozenset = frozenset()):
        super().__init__()
        self._funcs = funcs
        self._unicode = unicode
        # names ("pi", "oo") whose unicode glyph is suppressed for this
        # render even though self._unicode is True, see _print_Pi's
        # own note on why this exists.
        self._suppress_glyphs = suppress_glyphs

    def _print_Abs(self, expr):
        return f"abs({self._print(expr.args[0])})"

    def _print_Min(self, expr):
        return f"min({self.stringify(expr.args, ', ')})"

    def _print_Max(self, expr):
        return f"max({self.stringify(expr.args, ', ')})"

    def _print_ceiling(self, expr):
        return f"ceil({self._print(expr.args[0])})"

    def _print_loggamma(self, expr):
        return f"lgamma({self._print(expr.args[0])})"

    def _print_Exp1(self, expr):
        return "e"

    def _print_Pi(self, expr):
        # unicode only, "π" already round-trips back to "pi" on input
        # (see _UNICODE), so this is a pure output-spelling preference,
        # not a new glyph the grammar has to learn to parse. Mul/Add
        # printing (`pi/2`, `-pi`, ...) already calls self._print on
        # each factor/term, so this alone is enough for a compound
        # expression built from pi to read naturally too, no separate
        # override needed for those.
        #
        # Suppressed (falls back to the plain word) when "pi" is also a
        # real parameter's own name elsewhere in the same claim;
        # _node_to_sympy has no concept of any one function's real
        # parameters (a bare call isn't tied to a specific function), so
        # a genuine `pi`-named parameter and the math constant become
        # the exact same sympy object here, indistinguishable by the
        # time this printer runs; showing the glyph in that case would
        # misread as "evaluated at the constant" instead of "this
        # varying parameter". The real proof machinery is unaffected,
        # symbolic/_prove.py's own law-to-sympy walker checks a
        # function's real param_names first, so a `pi`-named parameter
        # is already proven/disproven correctly regardless of this.
        if "pi" in self._suppress_glyphs:
            return super()._print_Pi(expr)
        return "π" if self._unicode else super()._print_Pi(expr)

    def _print_ImaginaryUnit(self, expr):
        # italic 𝑖 in unicode output (it round-trips: _UNICODE maps it
        # straight to the 1j literal); ascii output uses the literal
        # itself so rendered text stays parseable; a bare "i" would
        # read back as an ordinary variable, never the unit.
        return "\U0001d456" if self._unicode else "1j"

    def _print_Infinity(self, expr):
        if "oo" in self._suppress_glyphs:
            return super()._print_Infinity(expr)
        return "∞" if self._unicode else super()._print_Infinity(expr)

    def _print_NegativeInfinity(self, expr):
        if "oo" in self._suppress_glyphs:
            return super()._print_NegativeInfinity(expr)
        return "-∞" if self._unicode else super()._print_NegativeInfinity(expr)

    def _print_Derivative(self, expr):
        var_args = [a for spec in expr.variable_count for a in ((spec[0],) * spec[1])]
        if not self._unicode:
            return f"d({self.stringify((expr.expr, *var_args), ', ')})"
        total_order = len(var_args)
        if len(expr.expr.free_symbols) <= 1:
            # a genuinely single-variable function: prime notation reads
            # the way this is conventionally spoken, but only up to a
            # third derivative; f''''(x) starts to blur into a run of
            # ticks, and only when expr.expr is itself one plain call
            # (`AppliedUndef`, the class every claim-bound function
            # letter; f, g, h, ...; actually is): a *named* sympy
            # function (`sin`, `Abs`, ...) has its own display spelling
            # elsewhere in this class, which reading `.func.__name__`
            # directly here would bypass and get wrong (`Abs` instead of
            # `abs`), so those fall through to the plain call form too.
            if total_order <= 3 and isinstance(expr.expr, sympy.core.function.AppliedUndef):
                name = expr.expr.func.__name__
                args = self.stringify(expr.expr.args, ", ")
                return f"{name}{chr(0x27) * total_order}({args})"
            return f"d({self.stringify((expr.expr, *var_args), ', ')})"
        # a genuine partial derivative (the differentiated expression
        # has more than one free variable, regardless of how many are
        # actually being differentiated with respect to here), always
        # the curly fraction form, at every order, restating the total
        # order on the leading ∂ (redundant with the denominator's own
        # exponents, but matching how this is conventionally written).
        order_marker = str(total_order).translate(_DIGIT_TO_SUPERSCRIPT) if total_order > 1 else ""
        denom = "".join(
            f"∂{var}{str(count).translate(_DIGIT_TO_SUPERSCRIPT) if count > 1 else ''}"
            for var, count in expr.variable_count)
        return f"∂{order_marker}({self._print(expr.expr)}/{denom})"

    def _print_Subs(self, expr):
        inner, variables, points = expr.args
        pairs = ", ".join(f"{self._print(v)}={self._print(p)}"
                          for v, p in zip(variables, points))
        marker = " at " if self._unicode else " @ "
        return f"{self._print(inner)}{marker}{{{pairs}}}"

    def _print_Limit(self, expr):
        # a one-sided limit carries its side as a sign trailing the
        # point (`lim(f(x), x, 0+)`), the same spelling the input reads;
        # a limit at infinity has only one side to approach from
        e, z, z0, direction = expr.args
        side = (str(direction) if str(direction) in ("+", "-")
                and not z0.is_infinite else "")
        return (f"lim({self._print(e)}, {self._print(z)}, "
                f"{self._print(z0)}{side})")

    def _print_Integral(self, expr):
        parts = [expr.function]
        for lim in expr.limits:
            parts.extend(lim if len(lim) == 3 else (lim[0],))
        args = self.stringify(parts, ", ")
        if not self._unicode:
            return f"integrate({args})"
        # one ∫ per integration variable, traditional multi-integral
        # notation (`∬f(x,y) dx dy`) written with the plain symbol
        # repeated rather than a dedicated ligature glyph, since this
        # grammar's own input already accepts any run of `∫`/`∬`/`∭` as
        # the same single trigger regardless of count (the integral-
        # symbol collapse in `normalize()`), the flat comma form after
        # it is unchanged from ascii mode, since the bound-bar spelling
        # has no unicode-specific glyph of its own to prefer over it. A
        # definite integral's own plain-integer bounds are additionally
        # attached to that same ∫, subscript lower and superscript
        # upper (`∫₀¹`), purely decorative, redundant with the
        # identical bounds already spelled out in the arguments, so a
        # non-integer bound (a symbol, `oo`, a fraction) simply isn't
        # decorated at all rather than guessing at a subscript/
        # superscript spelling for it.
        symbols = "".join("∫" + _integral_bound_marker(lim) for lim in expr.limits)
        return f"{symbols}({args})"

    def _print_Sum(self, expr):
        (var, lo, hi), = expr.limits
        return f"Sum({self.stringify((expr.function, var, lo, hi), ', ')})"

    def _print_Product(self, expr):
        (var, lo, hi), = expr.limits
        return f"Prod({self.stringify((expr.function, var, lo, hi), ', ')})"

    def _print_Function(self, expr):
        # StrPrinter has no bespoke _print_<name> for most of sympy's own
        # named functions (exp, sin, cos, sqrt is special-cased elsewhere,
        # ...); they all fall through to this same generic handler and
        # print correctly unchanged. Only a genuinely *uninterpreted*
        # function (built via sympy.Function('f'), the claim grammar's own
        # bound-function vocabulary) needs the funcs membership check.
        if isinstance(expr, sympy.core.function.AppliedUndef):
            name = expr.func.__name__
            if (name not in ("P.V.", "min", "max", "norm")
                    and name not in self._funcs):
                # "P.V." is the grammar's own principal-value operator
                # (an uninterpreted sympy.Function internally, but a
                # reserved call form, never a user binding). `min`/`max`
                # over a sequence are held uninterpreted for the same
                # reason: they are reserved aggregation forms, not
                # bindings, and sympy's scalar Min/Max would collapse
                # them (see _node_to_sympy).
                raise ValueError(f"unrenderable syntax: bound function {name!r} "
                                 f"not in funcs={self._funcs!r}")
        return super()._print_Function(expr)

    def _print_Piecewise(self, expr):
        raise ValueError("Piecewise has no claim-grammar spelling, "
                         "the claim-law grammar has no conditional syntax")


def to_canonical(expr: "sympy.Expr", funcs: frozenset = frozenset({"f"}),
                 unicode: bool = True, suppress_glyphs: frozenset = frozenset()) -> str:
    """The literal inverse of `_node_to_sympy`: a real sympy `Expr` back to
    mathema's own canonical claim-law text (`sympy.Abs(x)` -> `"abs(x)"`,
    not sympy's own `"Abs(x)"`). Raises `ValueError`, the same posture
    `_node_to_sympy` itself already has for unrenderable syntax, on a
    `Piecewise` (no claim-grammar spelling exists for a conditional) or an
    uninterpreted `Function` not in `funcs`; every string this returns
    is real, reparseable claim-grammar text, never a best-effort guess.

    `unicode` governs a `Derivative`'s own spelling (see
    `_CanonicalPrinter._print_Derivative`), every other node prints
    identically regardless. `suppress_glyphs` (`"pi"`/`"oo"`) forces the
    plain word instead of the usual unicode glyph for that constant,
    see `_CanonicalPrinter._print_Pi`'s own note on why a caller would
    ever want this."""
    return _CanonicalPrinter(funcs, unicode, suppress_glyphs).doprint(expr)


def render_canonical(expr: "sympy.Expr", funcs: frozenset = frozenset({"f"}),
                     unicode: bool = True) -> tuple[str, bool]:
    """`to_canonical(expr)`, with a fallback for the one shape it
    deliberately refuses: a `Piecewise` lift result (a whole function's
    closed form, not claim-law text; `to_canonical` itself must stay
    strict, since every string it returns has to be real, reparseable
    claim-grammar text). Falls back to `symbolic._humanize()` (plain
    English, e.g. "when cond: value; otherwise: value", already built
    for exactly this, a display sketch rather than a sympy REPL). Returns
    `(text, is_canonical_grammar)` so a caller can tell which one it got;
    `is_canonical_grammar=False` means `text` is not reparseable."""
    try:
        return to_canonical(expr, funcs, unicode), True
    except ValueError:
        from .symbolic import _humanize
        return _humanize(expr), False


_ABS_CALL = re.compile(r"\babs\(")


def _abs_calls_to_bars(text: str) -> str:
    """Intent:
        Every `abs(...)` call in `text`, nested ones included, rendered
        as `|...|` when its argument is a single bar term, and left as
        the `abs(...)` call otherwise.

    Notes:
        A single bar term is what `_BAR_TOKEN` accepts: a name, a
        number, one call, or one parenthesised group, containing no
        bar of its own. `|x - 1|` is not one, so `abs(x - 1)` keeps
        the call spelling (the grammar reads `|x - 1|` on input too);
        every string this returns folds back to the same `abs(...)`
        calls under `_fold_bars`. The scan is by balanced parens
        (`_find_balanced_call`), since an argument can itself contain
        parens, and inner calls are rewritten first, so an outer
        argument holding an inner `|y|` keeps the call spelling too.
    """
    def rewrite(m, args, call_end):
        inner = _abs_calls_to_bars(args)
        if "|" not in inner and re.fullmatch(_BAR_TOKEN, inner):
            return f"|{inner}|"
        return f"abs({inner})"

    return _rewrite_balanced_calls(text, _ABS_CALL, rewrite)


def render_law_expr(text: str, funcs: frozenset = frozenset(), unicode: bool = True,
                    suppress_glyphs: frozenset = frozenset()) -> str:
    """One side of a claim (`cj.lhs`/`cj.rhs`) -> preferred-spelling claim
    text: parsed and re-emitted through the same sympy round trip
    identity/fingerprinting already uses (`_node_to_sympy`/
    `to_canonical`), then this module's own math-over-python spelling
    preferences layered on top (`**` -> `^`; `abs(x)` -> `|x|`, in both
    modes, when the argument is a single bar term, `abs(x - 1)` staying
    the call; `floor(x)`/`ceil(x)` stay as the plain call in both modes
    too, never the `⌊x⌋`/`⌈x⌉` bracket notation, even though that's
    accepted *input*: rendered small, a floor/ceil bracket reads too
    easily as a single `|`, indistinguishable from `abs`). Going
    through sympy means the output is a *canonical*
    re-rendering, not a literal echo of `text`, equivalent but
    differently-written input (`x + 0`, term order) can come out
    differently spelled, which is expected, not a bug: `render_claim_text()`
    callers should compare re-parsed *meaning*, never rendered text
    byte-for-byte.

    `norm(x)` (the `||x||` input spelling) renders as the `norm(x)` call
    in both modes, kept apart from `abs(x)`: the two agree on a scalar
    and differ on a vector, so they are different claims.

    In ASCII mode, a Greek-letter identifier that has a known backslash
    spelling (`α` -> `\\alpha`, see `_GREEK_TO_BACKSLASH`) is converted
    back to it; input can spell the same letter three ways (plain
    Greek, math-italic, `\\name`), but only one, the plain letter,
    survives internally, so this is the one place that needs to know
    the reverse mapping. Any *other* Unicode identifier (Chinese,
    Cyrillic, ...) has no defined ASCII spelling and is left exactly as
    written, ASCII mode governs this grammar's own glyphs, not
    arbitrary identifier spelling in general.

    `suppress_glyphs` forwards to `to_canonical`; see
    `_CanonicalPrinter._print_Pi`'s own note on why a caller (spec.
    render_claim_text) would ever pass `{"pi"}`/`{"oo"}` here."""
    funcs = funcs | {"f"}
    expr = _node_to_sympy(ast.parse(text, mode="eval"), funcs)
    def respell(s: str) -> str:
        s = _abs_calls_to_bars(s.replace("**", "^"))
        if not unicode:
            for symbol, backslash_name in _GREEK_TO_BACKSLASH.items():
                s = s.replace(symbol, backslash_name)
        return s

    return outside_strings(
        respell, to_canonical(expr, funcs, unicode, suppress_glyphs))
