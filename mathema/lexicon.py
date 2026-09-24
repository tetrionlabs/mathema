# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A curated, runnable set of example claims spanning the claim grammar
(`grammar.py`/`conjecture.claim()`), documentation of the grammar by
example, not test fixture data. `tests/test_lexicon.py` and any future
docs generation both extract from this module; it is the source of
truth for what a claim looks like, they are downstream consumers of it.

`LEXICON` is ordered deliberately: early entries are simple, one
construct at a time, meant to read well as a first introduction to the
grammar; later entries combine several constructs at once and are
there to stress the parser, not to teach. `EXAMPLE_FUNCTIONS` pairs a
few real Python functions with the `LEXICON` keys they demonstrate;
a claim checked against nothing is just text, checking it against a
real function is what makes it a working example, including of
`claim()`'s own inference (a literal argument implying a domain, an
`int`-annotated parameter needing no domain restated at all).

Four ways in, depending on what you already know. `show(key)` prints one
entry with both rendered forms, for a key you can name. `entries(
"domains", ...)` takes a whole section. `find(query)` is for the usual
case of not knowing the key: it searches the keys, the law text, the
section names and a table of everyday synonyms (`TAGS`), forgivingly
enough that "modulo", "round down" or a typo still land. And
`EXAMPLE_FUNCTIONS` goes the other way, from a function to the keys it
demonstrates.

This is a first, deliberately small slice (`render_claim_text()`'s own
preferred spellings are expected to change once real rendered output
has been reviewed), see `spec.render_claim_text()` for the renderer
this module exercises."""
from __future__ import annotations

LEXICON: dict[str, str] = {
    # one construct at a time -----------------------------------
    "relation_eq": "f(x) == x",
    "odd_function": "f(-x) == -f(x)",
    "relation_le_unicode": "f(x) ≤ 1",
    # function equivalence: two implementations of the same
    # mathematics (g bound via funcs= at adjudication time), the
    # canonical ascii token, its word alias, and the unicode ≡ all
    # spell one relation
    "equivalence_canonical": "f =:= g",
    "equivalence_word_alias": "f equiv g",
    # a let binding beside the equivalence relation: the `=` in `=:=`
    # must never read as a binding continuation
    "equivalence_with_let": "let g = numpy.sum, f =:= g",
    "power_caret": "f(x)^2 >= 0",
    "abs_bars": "|f(x)| <= 1",
    # bars wrap any expression, not only one term
    "abs_bars_compound": "for x in [0, 1], y in [0, 1], |x + y - f(x, y)| <= ε",
    "factorial_postfix": "for n in [1, 5] subset Z, f(n) <= n!",
    # dimensional access: `dim(x, axis)` is canonical; `len`/`rows`/
    # `cols` are sugar folding to it. A dimension premise over two
    # sequences is drawn to hold by construction, never rejection-
    # sampled (see the probe sampler's shape plan)
    "dim_length_premise": "assuming len(x) == len(y), f(x, y) == f(y, x)",
    # matrix conformability: cols/rows fold to dim axis 1/0, and the
    # shared dimension is synthesised to agree for a Shape-marked pair
    "dim_conformability": "assuming cols(A) == rows(B), f(A, B) == f(A, B)",
    # a marker dimension name (Shape("m","n")) as a first-class symbol
    # in a premise, bound from the argument's real shape each trial
    "dim_marker_premise": "assuming n >= 2, f(a) >= 0",
    # the vector SPACE form: a domain raised to a dimension. The
    # element domain is the base, the dimension the exponent; unicode
    # renders the exponent as a superscript (ℝ^n -> ℝⁿ), and a shared
    # dimension name across two parameters draws them to one length
    "space_vector_real": "for v in R^n, f(v) >= 0",
    "space_vector_bounded": "for xs in [0, 1]^n, f(xs) <= 1",
    "space_matrix": "for A in R^(m*n), f(A) == f(A)",
    "space_shared_dim": "for x in R^n, y in R^n, f(x, y) == f(y, x)",
    "domain_closed_interval": "for x in [0, 1], f(x) >= 0",
    "domain_open_interval": "for x in (0, 1), f(x) >= 0",
    "domain_subset_integer": "for n in [0, 100] subset Z, f(n) >= 0",
    # a subscripted sequence element: no algebraic reading, carried
    # verbatim through parse and render alike
    "relation_indexing": "f(x, 1.0) == x[-1]",
    # a truth-valued law: the parenthesised comparison is the claimed
    # VALUE (Python's bool is an int), lifted as the 0/1 indicator on
    # the derive route and evaluated directly on the probe route
    "relation_boolean_rhs": "f(mi, chance) == (mi <= chance)",
    # the outcome clause: everything after `=>` names a sibling claim
    # that should follow when this one holds (captured, no semantics
    # adjudicate it yet)
    "outcome_reference": "f(x) > 0 => self.stays_positive",
    "raises_typed": "raises(f(x), ValueError)",
    "is_pole_safe": "is_pole_safe(x)",
    "negated_predicate": "not is_pole_safe(x)",
    "is_extremity_safe": "is_extremity_safe(x)",
    "is_representation_safe": "is_representation_safe(x)",
    "is_empty_safe": "is_empty_safe(xs)",
    "is_arbitrary_input_safe": "is_arbitrary_input_safe(s)",
    "is_compendium_safe": "is_compendium_safe(numpy)",
    "is_compendium_safe_scoped":
        "for x in [0, 1e6], is_compendium_safe(numpy)",
    "is_arbitrary_input_safe_postfix": "s is arbitrary input safe",
    # the function-wide spelling: the predicate over f is the
    # conjunction over every numeric parameter
    "safety_predicate_function_wide": "is_missing_safe(f)",
    # matrix structure predicates: a property of a matrix VALUE, on a
    # bare parameter (a precondition) or an f(...) output. The postfix
    # `A is symmetric` is sugar folding to the canonical call form.
    "matrix_symmetric": "is_symmetric(A)",
    "matrix_symmetric_postfix": "A is symmetric",
    "matrix_symmetric_output": "is_symmetric(f(A))",
    "is_sorted_output": "is_sorted_output(f(xs))",
    "output_never_none": "output_never_none(f(x))",
    "matrix_positive_definite": "is_positive_definite(A)",
    "matrix_finite": "is_finite(A)",
    # matrix ALGEBRA identities: the Python-flavoured vocabulary (`@`,
    # `.T`, `det`/`inv`/`trace`, `I(n)`) over matrix parameters, proven
    # in sympy's matrix algebra on the derive route
    "matrix_determinant_product":
        "for A in R^(n*n), B in R^(n*n), det(A @ B) == det(A) * det(B)",
    "matrix_transpose_product":
        "for A in R^(n*n), B in R^(n*n), (A @ B).T == B.T @ A.T",
    "matrix_trace_additive":
        "for A in R^(n*n), B in R^(n*n), trace(A + B) == trace(A) + trace(B)",
    # an inverse needs its premise: inv raises on a singular matrix
    "matrix_inverse_identity":
        "assuming det(A) != 0, for A in R^(n*n), inv(A) @ A == I(n)",
    # the postfix reading of an OUTPUT structure claim: `f(A) is
    # symmetric` folds to `is_symmetric(f(A))`
    "matrix_output_symmetric_postfix": "for A in R^(n*n), f(A) is symmetric",
    # the math-paper sugar, resolved from whether the operand is a
    # declared matrix: `A^T` -> `A.T` (transpose), `|A|` -> `det(A)`. A
    # scalar operand keeps power / absolute value. The record's grammar
    # is tagged `mathema/linalg` for these
    "matrix_transpose_sugar": "let A be R^(n*n), A^T == A",
    "matrix_determinant_sugar": "for A in R^(n*n), |A| >= 0",
    # the same bars around a matrix expression are its determinant
    "matrix_determinant_bars_compound":
        "for A in R^(n*n), B in R^(n*n), |A @ B| == |A| * |B|",
    "inferred_literal_domain": "raises(f(50, 0), ValueError)",
    # let: alias, function binding, free variable -----------------
    "let_alias": ("let m = m1, for m1 in [0.1,1000], x1 in [-100,100], "
                 "x2 in [-100,100], f(m,x1,m,x2) == (x1+x2)/2"),
    "let_function_dotted": "let g = math.sqrt, for x in (0,100], g(x) >= 0",
    # notation: the mathematical spelling of forms already curated in
    # ASCII above. Each is the SAME claim as its ASCII twin (the grammar
    # page's equivalence table pins that), kept here so the symbol set
    # the parser accepts is exercised rather than only described.
    "forall_symbol": "∀ x ∈ [0, 1], f(x) ≥ 0",
    "domain_subset_symbol": "∀ n ∈ [0, 100] ⊂ ℤ, f(n) ≥ 0",
    "domain_blackboard_reals": "∀ x ∈ ℝ, f(x) == 2*x",
    "relation_approx_unicode": "f(x) ≈ 2*x",
    "power_superscript": "f(x)² ≥ 0",
    "sqrt_symbol": "∀ x ∈ [0, 1], √(f(x)) ≥ 0",
    "multiply_dot": "∀ x ∈ [0, 1], f(x) · 2 == 4*x",
    "infinity_symbol": "∀ x ∈ [0, ∞), f(x) ≥ 0",
    "floor_brackets_unicode": "∀ x ∈ [0, 1], ⌊f(x)⌋ ≥ 0",
    "latex_command_forall": "\\forall x \\in [0, 1], f(x) \\geq 0",

    # `f` is shorthand, never a requirement: the function under test
    # answers to its own name, and `let` renames it to whatever reads
    # best in the claim
    "named_under_test": ("for price in [0,1000], rate in [0,1], "
                        "discounted_price(price, rate) <= price"),
    "let_alias_for_under_test": ("let net = f, for price in [0,1000], "
                                "rate in [0,1], net(price, rate) <= price"),
    "let_free_var_closed": "let c be [-1e6,1e6], for x in [0,10], f(x) + c >= 0",
    "let_free_var_typed": ("let c be [1,100] subset integer, for x in [0,10], "
                          "f(x) + c >= 0"),
    # let: the operational meaning of infinity ---------------------
    # the bars mean magnitude, applied symmetrically, deliberately
    # the ONE claim-text spelling (a bare or signed `inf` is refused:
    # it reads too much like the domain-endpoint spelling)
    "let_pseudo_infinity": ("let |inf| be 1e12, for x in [0, oo], "
                           "f(x) >= 0"),
    # stress tests: several constructs combined at once -----------
    "stress_gauge_invariance": (
        "let c be [-1e6,1e6], for dh in [-1e6,1e6], t in [0,1000], "
        "ds in [-1e6,1e6], d(f(dh+c,t,ds), t) == d(f(dh,t,ds), t)"),
    "stress_mixed_let_and_types": (
        "let g = math.sqrt, let c be [1,100] subset integer, for x in (0, 100], "
        "g(x) + c >= 0"),
    # auto-let: a Greek-word-spelled real parameter, unicode only -----
    "auto_let_greek_param": "for theta in [0, 1], f(theta) >= 0",
    # auto-let: a long name auto-lets to a short spelling -------------
    # a real parameter only auto-lets in unicode (ASCII has no
    # single-letter convention for an ordinary variable); a function
    # alias is part of the claim's identity and renders as written, see
    # spec.render_claim_text's own docstring.
    "auto_let_long_param": "for acceleration in [0, 100], f(acceleration) >= 0",
    "auto_let_long_func": ("let compute_square_root = numpy.sqrt, for x in [0, 100], "
                          "compute_square_root(x) >= 0"),
    # mixed unicode/ascii spelling in the input --------------------
    # the grammar accepts either spelling for most tokens; these mix
    # them within one claim on purpose, to check that the *output*
    # still commits fully to one mode (never a mix of its own) no
    # matter how inconsistently the input was spelled.
    "mixed_membership_and_relation": "for x ∈ [0, 1], f(x) <= 1",
    "mixed_ascii_for_unicode_relation": "for x in (0,100], f(x) ≥ 0",
    "mixed_backslash_greek_and_unicode_relation": r"f(\alpha) ≤ 1",
    # more domain shapes -------------------------------------------
    "domain_excluded_point": r"for x in [-1, 1] \ {1}, f(x) >= 0",
    "domain_discrete_strings": 'for scale in {"info", "linear"}, f(r, scale) >= 0',
    "domain_natural_numbers": "for n in N, f(n) >= 0",
    "domain_complex": "for z in C, f(z) == z",
    "relation_approx": "f(x) ~= x",
    # the claim's own tolerance by name: the declared `tolerance`, else
    # the 1e-9 default `==` and `~=` use, never a free variable
    "tolerance_epsilon": "for x in [0, 1], abs(f(x) - x) <= ε",
    "tolerance_eps_ascii": "for x in [0, 1], abs(f(x) - x) <= eps",
    "tolerance_epsilon_word": "for x in [0, 1], abs(f(x) - x) <= epsilon",
    "tolerance_epsilon_latex": "for x in [0, 1], abs(f(x) - x) \\leq \\epsilon",
    # derivatives: one primitive, many spellings -------------------
    "derivative_call": "d(f(x), x) >= 0",
    "derivative_prime": "f'(x) >= 0",
    "derivative_partial_symbol": "∂(f(x, y), x) == y",
    "derivative_second_mixed": "d(f(x, y), x, y) == 0",
    "derivative_at_point": "d(f(x), x) @ {x = 1} == 2",
    "derivative_at_word": "d(f(x), x) at {x = 1} == 2",
    # limits and integrals -----------------------------------------
    "limit_call": "lim(f(x), x, oo) == 0",
    "limit_arrow": "lim(f(x), x -> 0) == 0",
    "integrate_definite": "integrate(f(x), x, 0, 1) == 1",
    "integral_symbol": "∫(f(x), x, 0, 1) == 1",
    "integrate_evaluation_bar": "integrate(f(x), x)|_{0}^{1} == 1",
    "sum_subscript": "Sum(f(i))_{i=1}^n == n*(n+1)",
    "prod_call": "Prod(f(i), i, 1, n) >= 0",
    "principal_value": "P.V.(integrate(1/(x - c), x, -1, 1)) == f(c)",
    # assuming: a claim states its own precondition ----------------
    "assuming_inequality": ("assuming b^2 - 4*a*c >= 0.01, for a in [1,10], "
                           "b in [-10,10], c in [-10,10], d(f(a,b,c), c) <= 0"),
    "assuming_nonzero": "assuming k != 0, f(x, k) == x/k",
    "assuming_named_claim": ("assuming real_roots, for a in [1,10], "
                            "b in [-10,10], c in [-10,10], d(f(a,b,c), c) <= 0"),
    "assuming_prerequisite_holds": ("assuming grows holds, for x in [0,10], "
                                   "f(x) == 2*x"),
    # a premise resting on ANOTHER function's claim, the key dotted
    # before the claim name; resolution prefers an in-batch sibling,
    # then the verified layer (materialised library-stub rows included)
    "assuming_qualified_prerequisite": (
        "assuming numpy.clip.clip_lower holds, "
        "for w in [-50, 50], f(F0,k,m,-w,c) == f(F0,k,m,w,c)"),
    "assuming_prerequisite_proven": ("assuming base_case is proven, "
                                    "for n in [2, 30] subset Z, "
                                    "f(n) == f(n-1) + f(n-2)"),
    "assuming_is_defined": ("assuming is_defined(f), for w in [-50, 50], "
                           "f(F0,k,m,-w,c) == f(F0,k,m,w,c)"),
    "assuming_is_defined_postfix": ("assuming f is defined, for w in [-50, 50], "
                                   "f(F0,k,m,-w,c) == f(F0,k,m,w,c)"),
    # the pinned form a RECORD's statement carries: the region after
    # --> is validated against the live code on reparse; it is kept
    # verbatim while it still agrees, recomputed (with a note) when
    # the code has moved out from under it
    "assuming_is_defined_pinned": (
        "assuming is_defined(f) --> sqrt(c^2*w^2 + (k - m*w^2)^2) != 0, "
        "for w in [-50, 50], f(F0,k,m,-w,c) == f(F0,k,m,w,c)"),
    # certificates: a proof that names the sound rule that closed it
    "certificate_convex_lower": ("for alpha in [0, 1], "
                                "min(x) <= f(x, alpha)"),
    "certificate_convex_upper": ("for alpha in [0, 1], "
                                "f(x, alpha) <= max(x)"),
    "certificate_quadratic": ("let |inf| be 1e100, "
                              "for s1 in [0.05,0.5], s2 in [0.05,0.5], "
                             "rho in [-0.9,0.9], "
                             "d(f(w,s1,s2,rho), w, w) >= 0"),
    # case studies: real formulae from openly licensed references,
    # each claim executed by the lexicon tests
    "parity_identity": ("for s in [50,150], k in [50,150], r in [0.0,0.1], "
                 "t in [0.1,2], sigma in [0.05,0.8], "
                 "f(s,k,r,t,sigma) == s - k*exp(-r*t)"),
    "greek_delta_lower": ("for s in [50,150], k in [50,150], r in [0.0,0.1], "
                 "t in [0.1,2], sigma in [0.05,0.8], "
                 "∂(f(s,k,r,t,sigma), s) >= 0"),
    "greek_delta_upper": ("for s in [50,150], k in [50,150], r in [0.0,0.1], "
                 "t in [0.1,2], sigma in [0.05,0.8], "
                 "∂(f(s,k,r,t,sigma), s) <= 1"),
    "sigmoid_derivative": "for x in [-700, 700], d(f(x), x) == f(x)*(1 - f(x))",
    "sigmoid_symmetry": "for x in [-700, 700], f(-x) == 1 - f(x)",
    "sigmoid_limit_upper": "lim(f(x), x -> oo) == 1",
    "sigmoid_limit_lower": "lim(f(x), x -> -oo) == 0",
    "sigmoid_density_integrates": "∫(d(f(x), x), x, -oo, oo) == 1",
    "sigmoid_bounded_below": "for x in [-30, 30], f(x) > 0",
    "sigmoid_bounded_above": "for x in [-30, 30], f(x) < 1",
    "descent_converges": ("for alpha in [0.01,1.9], q in [0.5,1.0], "
                         "|f(alpha,q)| < 1"),
    # several functions in one claim -------------------------------
    # a bare call name binds from f's module or the calling scope at
    # check time; `let g = <name>` aliases it; `funcs=` on claim() is
    # the explicit spelling (not expressible in claim text alone)
    "second_function_by_name": "d(budget_line(x, I, px, py), x) == -px/py",
    "let_function_bare_name": ("let g = budget_line, "
                              "d(g(x, I, px, py), x) == -px/py"),
    "two_function_equality": "f(x) == g(x)",
    "bound_function_nested_in_f": (
        "let I be [10,1000], let px be [0.5,20], let py be [0.5,20], "
        "for a in [0.1,0.9], "
        "d(f(x, budget_line(x,I,px,py), a), x) @ {x = a*I/px} == 0"),
    # recurrences ---------------------------------------------------
    "recurrence_identity": ("for n in [2, 30] subset Z, "
                           "f(n) == f(n-1) + f(n-2)"),
    # chained comparison: a conjunction of pairwise links -----------
    "chained_comparison": ("for a in [0.1,10], b in [0.1,10], "
                          "2/(1/a+1/b) <= f(a,b) <= (a+b)/2"),
    # Euler's number, collision-free: exp(1) can never be a param ---
    "euler_via_exp": "for x in [1, 5], f(x) == exp(1)",
    # a FINITE domain is proved by visiting all of it ---------------
    # an integer-typed domain with finitely many points needs no
    # symbolic argument at all: every point is checked, so the verdict
    # is `proven` on route `derive:brute_force`, not the `holds` a
    # sampling loop earns. A single-point domain is the extreme case,
    # and the one where "check it" and "prove it" are the same act.
    "finite_domain_pinned": "for n in [30,30] subset Z, f(n) == 8",
    "finite_domain_small_range": "for n in [2,30] subset Z, f(n) >= 2",
    "finite_domain_discrete_set": "for n in {6, 28, 496}, f(n) >= 4",
    # the same domain written with the real-typed default is NOT
    # finite: [2,30] over the reals has uncountably many points, so
    # this one cannot take that route however small it looks
    "real_domain_is_not_finite": "for n in [2,30], f(n) >= 2",
    # integer parts: floor, ceiling and the remainder ---------------
    # `//` normalizes to floor(), `%` to Mod(), and the ordinary facts
    # about each are decided by relaxing the integer part to its exact
    # bounds (floor(u) = u - t for some t in [0,1))
    "floor_below_argument": "for x in [-20, 20], floor(x) <= x",
    "ceiling_above_argument": "for x in [-20, 20], ceil(x) >= x",
    # `//` is accepted input sugar and renders as `floor(n/2)`; both
    # spellings evaluate at a concrete point, so both reach the probe,
    # the corroborating witness and the brute-force sweep.
    "floor_div_sugar": "for n in [1,100] subset Z, f(n) == n // 2",
    "floor_div_evaluable": "for n in [1,100] subset Z, f(n) == floor(n/2)",
    "remainder_below_modulus": "for n in [0,1000] subset Z, n % 24 <= 23",
    "ceil_div_lower_bound": ("for a in [1,500] subset Z, b in [1,30] subset Z, "
                            "f(a,b) >= a/b"),
    # dimension premises pin a sequence's own length ----------------
    # `len(x)` is sugar for `dim(x, 0)` and both fold to one form. As a
    # premise a dimension does more than narrow the region: it pins the
    # length the derive route reasons about. Pinned to a literal, a
    # claim naming x[0] and x[1] proves instead of being falsified
    # against some other length; equating two lengths ties the two
    # sequences to one symbol, which is what stops a witness with
    # mismatched lengths, though the symmetry itself may still only
    # reach `holds`
    "dim_premise_pins_length": ("assuming len(x) == 2, "
                               "f(x) == x[0]^2 + x[1]^2"),
    "dim_premise_ties_two_lengths": ("assuming len(x) == len(y), "
                                    "f(x, y) == f(y, x)"),
    # a premise relating two PARAMETERS is not a box at all, so it
    # reaches the prover as an assumption rather than by narrowing
    "premise_relates_two_params": "assuming hi >= lo, f(xs, lo, hi) >= 0",
}

# The grammar's own table of contents: every LEXICON key, grouped by
# the construct it teaches, so a test (or a reader) can take one
# section at a time. `test_lexicon` pins this as an exact partition of
# LEXICON, so a new entry that forgets its section fails loudly.
SECTIONS: dict[str, tuple[str, ...]] = {
    "relations": (
        "odd_function",
        "relation_eq", "relation_le_unicode", "equivalence_canonical",
        "equivalence_word_alias", "equivalence_with_let",
        "power_caret", "abs_bars", "abs_bars_compound",
        "factorial_postfix", "dim_length_premise",
        "dim_conformability", "dim_marker_premise",
        "space_vector_real", "space_vector_bounded", "space_matrix",
        "space_shared_dim",
        "domain_closed_interval",
        "domain_open_interval", "domain_subset_integer",
        "relation_indexing", "relation_boolean_rhs",
        "outcome_reference", "raises_typed",
        "is_pole_safe", "negated_predicate", "is_extremity_safe",
        "is_representation_safe", "is_empty_safe",
        "is_arbitrary_input_safe", "is_arbitrary_input_safe_postfix",
        "is_compendium_safe", "is_compendium_safe_scoped",
        "is_sorted_output", "output_never_none",
        "safety_predicate_function_wide", "matrix_symmetric",
        "matrix_symmetric_postfix", "matrix_symmetric_output",
        "matrix_positive_definite", "matrix_finite",
        "matrix_determinant_product", "matrix_transpose_product",
        "matrix_trace_additive", "matrix_inverse_identity",
        "matrix_output_symmetric_postfix", "matrix_transpose_sugar",
        "matrix_determinant_sugar", "matrix_determinant_bars_compound",
        "inferred_literal_domain"),
    "lets": (
        "let_alias", "let_function_dotted", "let_free_var_closed",
        "named_under_test", "let_alias_for_under_test",
        "let_free_var_typed", "let_pseudo_infinity",
        "auto_let_greek_param", "auto_let_long_param",
        "auto_let_long_func"),
    "notation": (
        "forall_symbol", "domain_subset_symbol",
        "domain_blackboard_reals", "relation_approx_unicode",
        "power_superscript", "sqrt_symbol", "multiply_dot",
        "infinity_symbol", "floor_brackets_unicode",
        "latex_command_forall"),
    "domains": (
        "domain_excluded_point", "domain_discrete_strings",
        "domain_natural_numbers", "domain_complex", "relation_approx",
        "tolerance_epsilon", "tolerance_eps_ascii", "tolerance_epsilon_word",
        "tolerance_epsilon_latex",
        "finite_domain_pinned", "finite_domain_small_range",
        "finite_domain_discrete_set", "real_domain_is_not_finite"),
    "integer_parts": (
        "floor_below_argument", "ceiling_above_argument",
        "floor_div_sugar", "floor_div_evaluable",
        "remainder_below_modulus",
        "ceil_div_lower_bound"),
    "calculus": (
        "derivative_call", "derivative_prime",
        "derivative_partial_symbol", "derivative_second_mixed",
        "derivative_at_point", "derivative_at_word", "limit_call",
        "limit_arrow", "integrate_definite", "integral_symbol",
        "integrate_evaluation_bar", "sum_subscript", "prod_call",
        "principal_value", "recurrence_identity"),
    "case_studies": (
        "parity_identity", "greek_delta_lower", "greek_delta_upper",
        "sigmoid_derivative", "sigmoid_symmetry",
        "sigmoid_limit_upper", "sigmoid_limit_lower",
        "sigmoid_density_integrates", "sigmoid_bounded_below",
        "sigmoid_bounded_above", "descent_converges",
        "certificate_quadratic", "certificate_convex_lower",
        "certificate_convex_upper"),
    "assuming": (
        "assuming_inequality", "assuming_nonzero",
        "assuming_named_claim", "assuming_prerequisite_holds",
        "assuming_prerequisite_proven", "assuming_qualified_prerequisite",
        "assuming_is_defined",
        "assuming_is_defined_postfix", "assuming_is_defined_pinned",
        "dim_premise_pins_length", "dim_premise_ties_two_lengths",
        "premise_relates_two_params"),
    "functions": (
        "second_function_by_name", "let_function_bare_name",
        "two_function_equality", "bound_function_nested_in_f"),
    "mixed": (
        "mixed_membership_and_relation", "mixed_ascii_for_unicode_relation",
        "mixed_backslash_greek_and_unicode_relation",
        "stress_gauge_invariance", "stress_mixed_let_and_types",
        "chained_comparison", "euler_via_exp"),
}


# Words a reader is likely to search for that do not appear literally in
# an entry's key or its law text. The key, the law and the section name
# are already searchable, so this table carries only the synonyms and
# the spoken-aloud names of symbols: someone looking for "modulo" should
# find `%`, and someone looking for "for all" should find `∀`. Keep it
# to vocabulary a newcomer would actually type.
TAGS: dict[str, tuple[str, ...]] = {
    "relation_le_unicode": ("unicode", "symbols", "less than or equal"),
    "equivalence_canonical": ("equivalence", "two implementations",
                              "same mathematics", "refactor"),
    "power_caret": ("exponent", "power", "caret"),
    "abs_bars": ("absolute value", "magnitude", "bars"),
    "factorial_postfix": ("factorial", "combinatorics"),
    "domain_closed_interval": ("quantifier", "for all", "range", "bounds"),
    "domain_open_interval": ("open", "exclusive", "endpoint"),
    "domain_subset_integer": ("integer", "whole numbers", "type refinement"),
    "domain_excluded_point": ("exclusion", "except", "singularity", "hole"),
    "domain_natural_numbers": ("natural", "counting", "nonnegative integer"),
    "domain_complex": ("complex numbers", "imaginary", "plane"),
    "raises_typed": ("exception", "error", "raises", "precondition"),
    "relation_indexing": ("subscript", "element", "sequence", "vector"),
    "dim_length_premise": ("length", "shape", "conformable", "size"),
    "dim_conformability": ("shape", "conformable", "matching lengths"),
    "space_vector_real": ("vector space", "free dimension", "R^n"),
    "space_matrix": ("matrix space", "shape", "R^(m*n)"),
    "let_alias": ("alias", "abbreviation", "shorthand", "naming"),
    "let_pseudo_infinity": ("infinity", "unbounded", "limit of the range"),
    "derivative_call": ("derivative", "differentiate", "gradient", "slope"),
    "derivative_prime": ("derivative", "prime notation", "f'"),
    "limit_call": ("limit", "asymptote", "approaches", "tends to"),
    "integrate_definite": ("integral", "area under", "antiderivative"),
    "sum_subscript": ("sum", "series", "sigma", "summation"),
    "prod_call": ("product", "pi notation"),
    "recurrence_identity": ("recurrence", "recursive", "fibonacci"),
    "chained_comparison": ("sandwich", "between", "two sided bound",
                           "AM GM", "means"),
    "assuming_inequality": ("premise", "precondition", "assumption",
                            "given that"),
    "assuming_nonzero": ("premise", "nonzero", "division by zero"),
    "assuming_named_claim": ("premise", "another claim", "depends on"),
    "is_pole_safe": ("pole", "singularity", "divide by zero", "safety"),
    "is_extremity_safe": ("extremes", "overflow", "large values", "safety"),
    "is_arbitrary_input_safe": ("fuzz", "robustness", "arbitrary input",
                                "safety"),
    "is_empty_safe": ("empty", "empty list", "degenerate", "safety"),
    "matrix_symmetric": ("symmetric", "structure", "matrix property"),
    "matrix_determinant_product": ("determinant", "det", "multiplicative"),
    "matrix_transpose_product": ("transpose", "reverse order"),
    "matrix_trace_additive": ("trace", "linear"),
    "inferred_literal_domain": ("inference", "implied domain",
                                "literal argument", "terse"),
    # this campaign's own additions
    "finite_domain_pinned": ("finite", "brute force", "exhaustive",
                             "single point", "enumerate", "every point"),
    "finite_domain_small_range": ("finite", "brute force", "enumerate",
                                  "integer range", "every point"),
    "finite_domain_discrete_set": ("finite", "discrete", "set of values",
                                   "brute force", "perfect numbers"),
    "real_domain_is_not_finite": ("real", "uncountable", "not enumerable",
                                  "why it declines"),
    "floor_below_argument": ("floor", "round down", "integer part"),
    "ceiling_above_argument": ("ceiling", "round up", "integer part"),
    "floor_div_sugar": ("floor division", "integer division", "//",
                        "round down", "input only", "not evaluable"),
    "floor_div_evaluable": ("floor division", "integer division",
                            "round down", "evaluable spelling"),
    "remainder_below_modulus": ("modulo", "remainder", "mod", "%",
                                "clock arithmetic", "wrap around"),
    "ceil_div_lower_bound": ("ceiling division", "round up", "bin packing",
                             "how many buckets"),
    "dim_premise_pins_length": ("length", "pin the dimension", "fixed size",
                                "premise", "vector of known length"),
    "dim_premise_ties_two_lengths": ("same length", "shared dimension",
                                     "conformable", "premise", "symmetry"),
    "premise_relates_two_params": ("premise", "relates two parameters",
                                   "ordering premise", "not a box"),
}


def _searchable(key: str) -> str:
    """Everything one entry can be found by, as one lowercased blob:
    its key, its law text, the section it belongs to, and any `TAGS`
    synonyms. Underscores become spaces so a key reads as words."""
    section = next((name for name, keys in SECTIONS.items() if key in keys), "")
    parts = [key.replace("_", " "), LEXICON.get(key, ""), section,
             " ".join(TAGS.get(key, ()))]
    return " ".join(parts).lower()


def search(query: str, *, limit: int = 8) -> list[tuple[str, str]]:
    """Intent:
        `[(key, law), ...]` for the lexicon entries best matching
        `query`, most relevant first: the way to find an example
        without already knowing its key.

        Matching is deliberately forgiving, since the point is to find
        an example from a half-remembered word:

            search("modulo")        -> remainder_below_modulus, ...
            search("round down")    -> floor_div_sugar, ...
            search("divide by 0")   -> is_pole_safe, assuming_nonzero, ...
            search("evry point")    -> finite_domain_pinned, ...

    Notes:
        Each entry is matched on its key, its law text, its section name
        and its `TAGS` synonyms. A query word found as a substring
        scores highest; otherwise `difflib` scores it against the
        entry's individual words, which is what lets a typo or a near
        miss still land. Multi-word queries score per word and take the
        mean, so every word has to pull its weight.

        `difflib` is the same tool `families.close_keyword` uses for
        did-you-mean on a keyword. This is ordinary text search over a
        static table of examples, nothing to do with comparing claims
        or functions to each other.
    """
    import difflib

    words = [w for w in query.lower().replace("_", " ").split() if w]
    if not words:
        return []
    scored: list[tuple[float, str]] = []
    for key in LEXICON:
        blob = _searchable(key)
        haystack = blob.split()
        key_text = key.replace("_", " ").lower()
        per_word = []
        for word in words:
            if word in blob:
                per_word.append(1.0)
                continue
            best = max((difflib.SequenceMatcher(None, word, h).ratio()
                        for h in haystack), default=0.0)
            per_word.append(best)
        score = sum(per_word) / len(per_word)
        # a word found in the KEY counts for more than the same word
        # found in a tag or a section name: the key is the most
        # identifying text an entry has, so "round down" ranks
        # `floor_below_argument` above an entry that merely mentions
        # rounding in a tag.
        score += 0.05 * sum(1 for word in words if word in key_text)
        if score >= 0.6:
            scored.append((score, key))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [(key, LEXICON[key]) for _score, key in scored[:limit]]


def find(query: str, *, limit: int = 8) -> None:
    """Prints `search(query)` legibly, the interactive companion to
    `show()`: `mathema.lexicon.find("modulo")` when you know roughly
    what you want and not what it is called."""
    hits = search(query, limit=limit)
    if not hits:
        print(f"no lexicon entry matches {query!r}; "
              f"`list(mathema.lexicon.LEXICON)` lists every key")
        return
    width = max(len(key) for key, _law in hits)
    for key, law in hits:
        print(f"  {key:<{width}}  {law}")


def entries(*sections: str) -> dict[str, str]:
    """The lexicon, or just the named `SECTIONS` of it, as key -> law.
    No argument means everything: a full-sweep test iterates
    `entries()`, a targeted one `entries("domains", "assuming")`.
    An unknown section name raises with the roster."""
    if not sections:
        return dict(LEXICON)
    out: dict[str, str] = {}
    for name in sections:
        if name not in SECTIONS:
            raise KeyError(f"unknown lexicon section {name!r}; "
                           f"sections: {', '.join(SECTIONS)}")
        for key in SECTIONS[name]:
            out[key] = LEXICON[key]
    return out



def add_two(x: float, y: float) -> float:
    """The sum of two numbers."""
    return x + y


def matmul(A, B):
    """The matrix product."""
    return A @ B


def nearly_identity(x: float) -> float:
    """The identity plus an offset far below the default tolerance."""
    return x + 1e-10


def double(x: float) -> float:
    """f(x) = 2x, the plain function every single-construct LEXICON
    entry above (relation/power/abs/domain shapes) is checked against."""
    return 2 * x


def discount(price: float, code: float) -> float:
    """Raises when `code` is 0, what "inferred_literal_domain"
    demonstrates: `raises(f(50, 0), ValueError)` needs no explicit
    domain quantifier at all, `claim()` infers a degenerate domain for
    `code` from the literal `0` in the claim's own text."""
    if code == 0:
        raise ValueError("discount code required")
    return price / code


def center_of_mass_two_body(m1: float, x1: float, m2: float, x2: float) -> float:
    """(m1*x1 + m2*x2) / (m1 + m2), what "let_alias" demonstrates:
    forcing m1 == m2 via a shared free name covers the equal-masses
    boundary case with one claim instead of a separate one."""
    return (m1 * x1 + m2 * x2) / (m1 + m2)


def gibbs_free_energy(dh: float, t: float, ds: float) -> float:
    """delta-G = delta-H - T*delta-S, undefined below absolute zero,
    what "stress_gauge_invariance" demonstrates: a free variable (`c`,
    an arbitrary enthalpy-reference shift) with no real parameter to
    alias, whose own declared bound is otherwise inert on the derive
    route; the claim holds regardless of `c`'s value, which is
    exactly what gauge invariance means here."""
    if t < 0:
        raise ValueError("absolute temperature cannot be negative")
    return dh - t * ds


def quadratic_root_plus(a: float, b: float, c: float) -> float:
    """(-b + sqrt(b^2 - 4ac)) / 2a, what the `assuming_*` entries
    demonstrate: the unconditional monotonicity claim falsifies (the
    sqrt raises where the discriminant goes negative), while the same
    claim under `assuming b^2 - 4*a*c >= 0.01` proves."""
    import math
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def budget_line(x: float, I: float, px: float, py: float) -> float:   # noqa: E741
    """y = (I - px*x)/py, the second function the multi-function
    entries call by bare name: it binds from this module's own scope at
    check time, no funcs= needed."""
    return (I - px * x) / py


def cobb_douglas_utility(x: float, y: float, a: float) -> float:
    """x^a * y^(1-a), what "bound_function_nested_in_f" demonstrates:
    utility along the budget line, the budget bound inside f's own
    second argument, stationary at the optimal x* = a*I/px."""
    return x ** a * y ** (1 - a)


def oscillator_amplitude(F0: float, k: float, m: float, w: float,
                         c: float) -> float:
    """Driven-oscillator amplitude, singular exactly at undamped
    resonance, what "assuming_is_defined" demonstrates: the claim
    quantifies over the exact region where every call returns, and the
    computed region (the denominator's nonvanishing) is rendered into
    the statement, never left as an opaque "wherever defined"."""
    import math
    return F0 / math.sqrt((k - m * w * w) ** 2 + (c * w) ** 2)


def fib(n: float) -> float:
    """Naive fibonacci, what "recurrence_identity" demonstrates: the
    recurrence lifter closes the recursion to Binet's formula and the
    claim proves over an integer domain."""
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)


def geometric_mean_two(a: float, b: float) -> float:
    """The geometric mean of two positive reals, what
    "chained_comparison" demonstrates: the HM <= GM <= AM chain as one
    claim, decomposed into conjoined pairwise links."""
    import math
    return math.sqrt(a * b)


def discounted_price(price: float, rate: float) -> float:
    """A price with a discount rate applied. Never exceeds the original
    price for a rate in [0, 1], which is what "named_under_test" and
    "let_alias_for_under_test" state: the first calls the function by
    its own name, the second renames it with `let`, and `f` is only ever
    a shorthand for the same thing."""
    return price * (1.0 - rate)


def cubed(x: float) -> float:
    """f(x) = x^3, an odd function: negating the input negates the
    result, which is what "odd_function" states. The plainest example of
    a symmetry claim, and the one most of this project's documentation
    reaches for. Written as a product, which overflows to a signed
    infinity rather than raising, so the symmetry holds for every
    float."""
    return x * x * x


def unit_sqrt(x: float) -> float:
    """numpy.sqrt returns nan for x < 0 without raising, so
    "is_compendium_safe_scoped" holds only because the domain [0, 1e6]
    excludes that region: is_compendium_safe(numpy) over a guarded
    domain. numpy is imported lazily so the lexicon stays import-free of
    it."""
    import numpy as np
    return float(np.sqrt(x))


def clipped_ratio(x: float) -> float:
    """numpy.clip keeps the result finite for every input, so
    "is_compendium_safe" holds unconditionally: a covered numpy call that
    can never leak a nan/inf."""
    import numpy as np
    return float(np.clip(x, 0.0, 1.0))


def unguarded_arcsin(x: float) -> float:
    """numpy.arcsin returns nan for abs(x) > 1 without raising, so
    "is_compendium_safe" FALSIFIES here (the unguarded counterpart to
    unit_sqrt): the bound `for x in [-1, 1], is_compendium_safe(numpy)`,
    or a guard, supersedes the finding once re-verified."""
    import numpy as np
    return float(np.arcsin(x))


def divisor_count(n: float) -> float:
    """How many positive divisors n has. A guarded fold over a range,
    which the symbolic lifter cannot close, so a claim about it over a
    FINITE integer domain is settled by visiting every point instead
    ("finite_domain_pinned": 30 has eight divisors)."""
    total = 0
    for d in range(1, int(n) + 1):
        if int(n) % d == 0:
            total += 1
    return float(total)


def half_down(n: float) -> float:
    """Floor of n/2, spelled with Python's floor division, which the
    grammar normalizes to `floor(n/2)` ("floor_div_sugar")."""
    return float(int(n) // 2)


def ceil_div(a: float, b: float) -> float:
    """a divided by b, rounded up. The two bounds every ceiling
    satisfies (`>= a/b` and `<= a/b + 1`) are decided by relaxing the
    integer part to its own exact range ("ceil_div_lower_bound")."""
    import math
    return float(math.ceil(a / b))


def sum_of_squares(x: list) -> float:
    """Sum of squares of a vector. Without a length premise a claim
    naming x[0] and x[1] is about some other length and falsifies; with
    `assuming len(x) == 2` the length is pinned and it proves
    ("dim_premise_pins_length")."""
    total = 0.0
    for i in range(len(x)):
        total = total + x[i] * x[i]
    return total


def dot_product(x: list, y: list) -> float:
    """Dot product. Symmetric only where the two lengths agree, which
    is what the premise supplies ("dim_premise_ties_two_lengths")."""
    total = 0.0
    for i in range(len(x)):
        total = total + x[i] * y[i]
    return total


def spread_total(xs: list, lo: float, hi: float) -> float:
    """Accumulate the gap (hi - lo) once per element. Nonnegative only
    when hi >= lo, a premise relating two parameters rather than
    bounding either one ("premise_relates_two_params")."""
    total = 0.0
    for _i in range(len(xs)):
        total = total + (hi - lo)
    return total


def weighted_average(x: list, alpha: float) -> float:
    """An exponentially weighted moving average: each step is a convex
    combination of the new element and the accumulator. What the
    "certificate_convex_*" entries demonstrate: the fold's bounds are
    proven by induction, not sampled, because both weights are
    nonnegative and sum to one on the declared domain."""
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def portfolio_variance(w: float, s1: float, s2: float, rho: float) -> float:
    """Two-asset portfolio variance. What "certificate_quadratic" shows:
    read as a quadratic in w, the second derivative is nonnegative
    because the leading coefficient is nonnegative and the discriminant
    settles the sign, which is a certificate rather than a sample."""
    return (w ** 2 * s1 ** 2 + (1 - w) ** 2 * s2 ** 2
            + 2 * w * (1 - w) * rho * s1 * s2)


def black_scholes_call(s: float, k: float, r: float, t: float,
                       sigma: float) -> float:
    """A European call priced by Black-Scholes. The Greeks ARE its
    partial derivatives, which is what the "greek_*" entries state in
    the grammar's own notation: delta is the partial in the spot price
    and lies in [0, 1], vega is the partial in volatility and is
    positive. Source: Black-Scholes model and Greeks (finance),
    Wikipedia (CC BY-SA 4.0)."""
    import math
    root_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * root_t)
    d2 = d1 - sigma * root_t
    phi = lambda z: 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))   # noqa: E731
    return s * phi(d1) - k * math.exp(-r * t) * phi(d2)


def put_call_parity_gap(s: float, k: float, r: float, t: float,
                        sigma: float) -> float:
    """A European call minus a European put on the same strike, both
    legs priced by Black-Scholes. Put-call parity says the difference
    collapses to S - K*exp(-r*T), independent of volatility, which is
    what "parity_identity" proves. Source: Put-call parity and
    Black-Scholes model, Wikipedia (CC BY-SA 4.0)."""
    import math
    root_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * root_t)
    d2 = d1 - sigma * root_t
    phi = lambda z: 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))   # noqa: E731
    call = s * phi(d1) - k * math.exp(-r * t) * phi(d2)
    put = k * math.exp(-r * t) * phi(-d2) - s * phi(-d1)
    return call - put


def black_scholes_vega(s: float, k: float, r: float, t: float,
                       sigma: float) -> float:
    """Vega: the sensitivity of a European option's price to its
    volatility, one of the Greeks. Strictly positive wherever the
    option has time left, which is what "vega_positive" states.
    Source: Greeks (finance), Wikipedia (CC BY-SA 4.0)."""
    import math
    root_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * root_t)
    return s * root_t * math.exp(-0.5 * d1 * d1) / math.sqrt(2.0 * math.pi)


def logistic_standard(x: float) -> float:
    """The standard logistic function, the sigmoid of machine learning.
    Its calculus is what the "sigmoid_*" entries demonstrate: a
    derivative expressible in the function itself, limits at both
    infinities, and a derivative that integrates to one over the line.
    Source: Logistic function, Wikipedia (CC BY-SA 4.0)."""
    import math
    return 1.0 / (1.0 + math.exp(-x))


def gd_convergence_factor(alpha: float, q: float) -> float:
    """r = 1 - alpha*q, the per-step convergence factor of fixed-step
    gradient descent on the quadratic bowl f(t) = 0.5*q*t^2: successive
    iterates satisfy x_(n+1) = r*x_n, so the method converges exactly
    when |r| < 1. Source: Scientific Python Lectures (CC BY 4.0),
    "Mathematical optimization: finding minima of functions"."""
    return 1.0 - alpha * q


EXAMPLE_FUNCTIONS: dict[str, tuple[object, list[str]]] = {
    "add_two": (add_two, ["abs_bars_compound"]),
    "matmul": (matmul, ["matrix_determinant_bars_compound"]),
    "nearly_identity": (nearly_identity, [
        "tolerance_epsilon", "tolerance_eps_ascii", "tolerance_epsilon_word",
        "tolerance_epsilon_latex",
    ]),
    "double": (double, [
        "relation_eq", "relation_le_unicode", "power_caret", "abs_bars",
        "domain_closed_interval", "domain_open_interval",
        "domain_subset_integer",
        "forall_symbol", "domain_subset_symbol",
        "domain_blackboard_reals", "relation_approx_unicode",
        "power_superscript", "sqrt_symbol", "multiply_dot",
        "infinity_symbol", "floor_brackets_unicode",
        "latex_command_forall",
    ]),
    "discount": (discount, ["raises_typed", "inferred_literal_domain"]),
    "center_of_mass_two_body": (center_of_mass_two_body, ["let_alias"]),
    "gibbs_free_energy": (gibbs_free_energy, [
        "let_free_var_closed", "let_free_var_typed", "stress_gauge_invariance",
    ]),
    "quadratic_root_plus": (quadratic_root_plus, [
        "assuming_inequality", "assuming_named_claim",
    ]),
    "cobb_douglas_utility": (cobb_douglas_utility, [
        "bound_function_nested_in_f",
    ]),
    "fib": (fib, ["recurrence_identity"]),
    "oscillator_amplitude": (oscillator_amplitude, [
        "assuming_is_defined", "assuming_is_defined_postfix",
        "assuming_is_defined_pinned",
    ]),
    "weighted_average": (weighted_average, [
        "certificate_convex_lower", "certificate_convex_upper",
    ]),
    "portfolio_variance": (portfolio_variance, ["certificate_quadratic"]),
    "black_scholes_call": (black_scholes_call, [
        "greek_delta_lower", "greek_delta_upper",
    ]),
    "put_call_parity_gap": (put_call_parity_gap, ["parity_identity"]),
    "logistic_standard": (logistic_standard, [
        "sigmoid_derivative", "sigmoid_symmetry", "sigmoid_limit_upper",
        "sigmoid_limit_lower", "sigmoid_density_integrates",
        "sigmoid_bounded_below", "sigmoid_bounded_above",
    ]),
    "gd_convergence_factor": (gd_convergence_factor, ["descent_converges"]),
    "geometric_mean_two": (geometric_mean_two, ["chained_comparison"]),
    "discounted_price": (discounted_price, [
        "named_under_test", "let_alias_for_under_test",
    ]),
    "cubed": (cubed, ["odd_function"]),
    "unit_sqrt": (unit_sqrt, ["is_compendium_safe_scoped"]),
    "clipped_ratio": (clipped_ratio, ["is_compendium_safe"]),
    "unguarded_arcsin": (unguarded_arcsin, ["is_compendium_safe"]),
    "divisor_count": (divisor_count, [
        "finite_domain_pinned", "finite_domain_small_range",
        "finite_domain_discrete_set", "real_domain_is_not_finite",
    ]),
    "half_down": (half_down, ["floor_div_evaluable"]),
    "ceil_div": (ceil_div, ["ceil_div_lower_bound"]),
    "sum_of_squares": (sum_of_squares, ["dim_premise_pins_length"]),
    "dot_product": (dot_product, ["dim_premise_ties_two_lengths"]),
    "spread_total": (spread_total, ["premise_relates_two_params"]),
}


def get(key: str | int) -> str:
    """One `LEXICON` entry's input text, `key` a str name (dict key)
    or an int index into insertion order. `KeyError`/`IndexError` if it
    doesn't exist, same as indexing the underlying dict/list directly
    would."""
    if isinstance(key, int):
        return LEXICON[list(LEXICON)[key]]
    return LEXICON[key]


def render_both(key: str | int, *, include_internal: bool = False):
    """`(input_text, output_unicode, output_ascii)` for one `LEXICON`
    entry, `input_text` as authored, the other two from `claim()` +
    `spec.render_claim_text()`. Use this instead of `get()` to see the
    rendered shape next to the input, e.g. while reviewing whether a
    rendering choice reads right.

    `include_internal=True` appends a fourth element: a dict of the
    parsed `Conjecture`'s own fields (`lhs`, `relation`, `rhs`,
    `domain`, `funcs`, `free_vars`), the normalized internal
    representation both rendered strings are built from, useful for
    seeing exactly what a claim resolved to (an alias substituted away,
    a free variable's assumed type made explicit, ...) rather than only
    its two surface spellings."""
    from .conjecture import claim
    from .spec import render_claim_text

    text = get(key)
    cj = claim(text)
    result = (text, render_claim_text(cj, unicode=True),
             render_claim_text(cj, unicode=False))
    if not include_internal:
        return result
    internal = {"lhs": cj.lhs, "relation": cj.relation, "rhs": cj.rhs,
               "domain": cj.domain, "funcs": cj.funcs, "free_vars": cj.free_vars}
    return (*result, internal)


def show(key: str | int, *, include_internal: bool = False) -> None:
    """Prints `render_both(key)` legibly, the entry point for
    exploring the grammar interactively, e.g. `mathema.lexicon.show(
    "let_free_var_typed")` in a REPL. `list(mathema.lexicon.LEXICON)`
    already answers "what keys exist" without a separate function.
    `include_internal=True` also prints the parsed `Conjecture`'s own
    fields, see `render_both`."""
    name = key if isinstance(key, str) else list(LEXICON)[key]
    result = render_both(key, include_internal=include_internal)
    text, unicode_form, ascii_form = result[:3]
    print(f"{name}")
    print(f"  input:   {text}")
    print(f"  unicode: {unicode_form}")
    print(f"  ascii:   {ascii_form}")
    if include_internal:
        internal = result[3]
        print("  internal:")
        for field, value in internal.items():
            print(f"    {field}: {value!r}")
