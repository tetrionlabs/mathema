# Matrix structure and linear algebra

A matrix parameter can carry more than a shape. Beyond *how many axes,
how long* (see [Matrices, and named dimensions](conditional-claims.md)),
mathema tracks a matrix's **structure**: symmetric, triangular,
orthogonal, positive definite, finite. Structure is a claim kind in its
own right, and it is also a type that narrows what a claim is checked
over and what a linear-algebra identity may assume.

The claim kinds form a hierarchy, cheapest first:

| kind | example | cost |
|---|---|---|
| shape | `A ∈ ℝ^{n×n}` | axis bookkeeping |
| element-wise | `is_finite(A)` | O(n²) direct |
| structural | `A == A.T` | O(n²) direct |
| spectral | `is_positive_definite(A)` | O(n³) eigen / Cholesky |
| algebra | `det(A @ B) == det(A) * det(B)` | symbolic |

## Declaring structure

A structure is a marker in the parameter's type, alongside its shape.
The canonical spelling is an `Annotated` hint; `Mat(...)` is the sugar
that produces an equivalent annotation:

```python
from typing import Annotated
from mathema.types import Mat, Shape, Symmetric, PositiveDefinite

# canonical
def f(A: Annotated[list, Shape("n", "n"), Symmetric]): ...

# sugar (equivalent annotation)
def g(A: Mat("n", "n", Symmetric)): ...
```

The markers, by level: `Real`, `Finite` (element-wise); `Symmetric`,
`SkewSymmetric`, `Diagonal`, `UpperTriangular`, `LowerTriangular`,
`Identity` (structural); `Orthogonal`, `PositiveDefinite`,
`PositiveSemidefinite` (spectral). Each maps to a registry predicate
(`Symmetric` to `is_symmetric`, and so on).

A declared structure is **entailment-closed**: `PositiveDefinite` also
asserts `is_symmetric` (and everything symmetry implies), because a
positive-definite matrix is symmetric. Declaring the specific property
narrows the domain to everything it entails.

## Structure claims

A structure predicate is a claim about a matrix VALUE. The canonical
form is the predicate call; the postfix `is` reading is sugar for it:

```
is_symmetric(A)            # a precondition on the argument
is_symmetric(f(A))         # the output is symmetric
A is symmetric             # postfix, folds to is_symmetric(A)
f(A) is symmetric          # postfix on an output, folds to is_symmetric(f(A))
f(A) is positive definite  # a multi-word predicate reads the same way
```

On a bare parameter (`is_symmetric(A)`) the claim asks whether the
function GUARDS the property: does it reject an argument that lacks it,
the value analogue of an out-of-domain rejection. On an expression
(`is_symmetric(f(A))`, `is_symmetric(A @ B)`) it checks the resulting
value. Both adjudicate on the `examine` route: a structural check on
synthesised or real values, numpy-fast where numpy is present and a
pure-Python fallback otherwise. A spectral check with no numpy declines
(`skipped`) rather than guessing.

`is_finite(A)` is the matrix-scale sibling of the missing-value axis: it
narrows a domain away from `nan`/`inf`, fast via numpy.

## Narrowing the domain

A structure marker, or an `assuming` premise, narrows the matrices a
claim is sampled over. Under

```
assuming A is positive definite, f(A) == f(A.T)
```

the sampler synthesises `A` by construction as a positive-definite
matrix (entailment-closed, so it is symmetric too), because a random
matrix is almost never positive definite and rejection alone would
never find one. The same premise becomes a sympy assumption on the
derive route (below), so the two halves, sampling and proof, read one
declaration the same way.

## The linear-algebra grammar

The operation vocabulary is Python-flavoured, what a NumPy user writes:

```
A @ B        matrix product
A.T          transpose
det(A)       determinant
inv(A)       inverse
trace(A)     trace
I(n)         the n-by-n identity
x.T @ A @ x  a quadratic form
```

Three math-paper spellings are accepted as sugar. Each is **ambiguous**
against a scalar reading, so mathema resolves it from the operand's
declared type: on a matrix it is the matrix operation, on a scalar the
ordinary one.

| sugar | on a matrix | on a scalar |
|---|---|---|
| `A^T` | `A.T` (transpose) | `A ** T` (power) |
| <code>&#124;A&#124;</code> | `det(A)` | `abs(A)` |
| `A^-1` | `inv(A)` | `1 / A` (reciprocal) |

The type is known from a signature marker, an `R^(m*n)` domain, or a
`let ... be R^(m*n)` declaration:

```
let A be R^(n*n), A^T == A          #  ->  A.T == A
for A in R^(n*n), |A| >= 0          #  ->  det(A) >= 0
```

Because the reading is per-operand, one expression can mix the two:
with `A` a matrix and `c` a scalar, `inv(c * A) == c^-1 * A^-1` resolves
to `inv(c * A) == c ** (-1) * inv(A)`, the `c^-1` a reciprocal and the
`A^-1` an inverse.

When a claim uses the matrix vocabulary, the record's `grammar` field is
stamped `mathema/linalg`. This is informative only, a note that the
parsing was matrix-aware; it is never required to round-trip, because
the canonical statement (`det(A @ B) == det(A) * det(B)`) re-parses
under the base grammar on its own.

## Proving identities and inequalities

A matrix-algebra relation is an identity of the algebra, not a fact
about a function's body. mathema lifts the claim's own expressions to
`sympy.MatrixSymbol` terms, turns structure markers and premises into
sympy assumptions (`Q.symmetric`, `Q.positive_definite`, ...), and
decides the relation. Equalities are decided by simplifying the
difference to zero; scalar comparisons of a determinant or trace are
decided by sympy's assumption engine.

```
det(A @ B) == det(A) * det(B)                          proven
(A @ B).T == B.T @ A.T                                 proven
trace(A + B) == trace(A) + trace(B)                    proven
assuming A is symmetric, A.T == A                      proven
assuming A is orthogonal, A.T @ A == I(n)              proven
assuming A is positive definite, det(A) > 0            proven
assuming A is positive definite, trace(A) > 0          proven
```

A relation sympy cannot close falls to the matrix-value probe: concrete
matrices are sampled (structure-narrowed, as above), both sides
evaluated, and the claim either holds across the draws or is falsified
with the witnessing matrices. A strict `derive` route reports the
honest `unknown` instead of sampling.

## Runtime enforcement

`@enforce_structure` is the structure analogue of `@enforce_domain` and
`@enforce_dimensions`: it reads a parameter's structure markers and any
declared `is_<prop>(param)` claim, checks each matrix argument at call
time, and raises `ValueError` naming the property and the failing
argument before the function runs. It auto-declares the matching
predicate claim, so the precondition and its runtime guard are one
statement.

```python
@enforce_structure()
def cholesky(A: Annotated[list, Shape("n", "n"), PositiveDefinite]): ...

cholesky(non_pd_matrix)   # ValueError: cholesky: A is not is_positive_definite (positive definite)
```

A property the registry cannot decide (a spectral check with no numpy)
is skipped, never a false rejection.

## Rendering

The matrix vocabulary renders through sympy's matrix printing, produced
on demand from the canonical claim rather than stored: `A.T` as `A^{T}`,
`det(A)` as `|A|`, a product as juxtaposition, `x.T @ A @ x` as
`x^{T} A x`. Nothing per-claim is kept in the record; the canonical
statement is the source, and `grammar.to_latex` renders it.

## Limits

The dependency `numpy` is optional (the `test` extra); element-wise and
structural checks fall back to pure Python, spectral checks decline
without it. Determinant and inverse sampling need numpy. A bar-delimited
determinant wraps a single name only (`|A|`); a product's determinant is
the canonical `det(A @ B)`, exactly as a scalar `|x + y|` is written
`abs(x + y)`. A matrix ordering (`A > B`) is undefined and declined; only
scalar comparisons of determinants and traces are decided.
