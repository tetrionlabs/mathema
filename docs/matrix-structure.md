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

A matrix parameter is drawn as nested lists unless its signature names
another runtime type: `A: np.ndarray`, or `Mat("n", "n",
runtime="numpy.ndarray")` beside the structure markers, samples it as a
2-D array, so `def transpose(A: np.ndarray): return A.T` holds `for A
in R^(n,n), f(f(A)) == A` where a list of lists would raise at `.T`.
Nested lists are drawn up to 64 per axis. See [runtime
types](runtime-types.md).

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
narrows a domain away from `nan`/`inf`, fast via numpy. On an expression
(`is_finite(f(x))`) the check reads the claim's `assuming` clause like
every other claim, and a raise from `f` at a point inside it falsifies
the claim, naming the exception.

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

### What each operator means

The operators read the way numpy reads them, whatever the function's
own runtime type: a list-of-lists matrix is evaluated as an array, so
`x + y` never concatenates two lists.

| spelling | on vectors and matrices |
|---|---|
| `A @ B` | the matrix product; two vectors give their dot product |
| `A * B` | elementwise (the Hadamard product); `c * A` scales |
| `A ** k` | elementwise power; the matrix power is `matrix_power(A, k)` |
| `A + B`, `A - B`, `-A` | elementwise; `A + c` shifts every element |
| `abs(A)` | elementwise absolute value |
| <code>&#124;A&#124;</code> | the determinant of a declared matrix (sugar, below) |
| `norm(x)` | Euclidean on a vector, Frobenius on a matrix |
| `norm(A, 2)`, `norm(A, 1)`, `norm(A, inf)` | spectral, largest column sum, largest row sum |
| `A ~= B` | element by element, with the scalar tolerance |

An ordering between a matrix or vector and anything (`A >= 0`,
`A * A >= 0`) is not defined, and the claim is refused as misspecified
with the reason; compare a number drawn from it instead (`det`,
`trace`, `norm`, an element). An elementwise reading spelled
`all(...)` is future work. The scalar derive route never reads a
vector or matrix as a number: a claim that uses one as a value goes
to the matrix algebra below or, when that cannot close it, to
sampling.

<!-- example: semantics run -->
```python
from mathema.types import Mat, Vec

def two(A: Mat("n", "n"), B: Mat("n", "n")):
    return A

def vecs(x: Vec("n"), y: Vec("n")):
    return x
```

<!-- example: semantics verdicts fn=two -->
```
A * B == B * A   # proven
A @ B == B @ A   # falsified
A ** 2 == A * A   # proven
matrix_power(A, 2) == A @ A   # proven
matrix_power(A, 2) == A * A   # falsified
```

<!-- example: semantics verdicts fn=vecs -->
```
norm(x + y) <= norm(x) + norm(y)   # holds
norm(x + y)**2 == norm(x)**2 + norm(y)**2   # falsified
norm(x + y)**2 == norm(x)**2 + norm(y)**2 + 2*dot(x, y)   # holds
```

### The vocabulary

Beyond `det`, `inv`, `trace`, `transpose` and `I(n)`:

| word | meaning |
|---|---|
| `dot(x, y)`, `outer(x, y)`, `kron(A, B)` | inner, outer and Kronecker products |
| `diag(A)`, `diag(v)` | the diagonal of a matrix; the diagonal matrix of a vector |
| `rank(A)`, `cond(A)` | numerical rank; the 2-norm condition number |
| `eigvals(A)`, `eigvalsh(A)` | eigenvalues (complex in general); of a symmetric matrix, real and ascending |
| `solve(A, b)`, `pinv(A)` | the solution of `A @ x == b`; the pseudo-inverse |
| `A[i, :]`, `A[:, j]` | a row, a column |
| `sum(A, axis=0)`, `mean(A, axis=1)` | reductions along an axis (also `prod`, `min`, `max`) |
| `x.T @ A @ x` | a quadratic form, a number (a 1-by-1 result is its element) |

A decomposition is a claim about its factors, with the numpy function
bound by `let`: `let q = numpy.linalg.qr, q(A)[0] @ q(A)[1] ~= A`. A
vector of the claim's own is declared with `let b be R^n`, and takes
the size the parameters give `n`. `x != 0` over a vector says it is not
the zero vector.

<!-- example: vocabulary run -->
```python
from mathema.types import Mat, Vec

def one(A: Mat("n", "n")):
    return A

def form(A: Mat("n", "n"), x: Vec("n")):
    return A
```

<!-- example: vocabulary verdicts fn=one -->
```
trace(A) ~= sum(eigvals(A))   # proven
det(A) ~= prod(eigvals(A))   # proven
trace(A) ~= prod(eigvals(A))   # falsified
let b be R^n, assuming det(A) != 0, A @ solve(A, b) ~= b   # proven
A @ pinv(A) @ A ~= A   # holds
sum(A, axis=0) ~= sum(A.T, axis=1)   # holds
let q = numpy.linalg.qr, q(A)[0] @ q(A)[1] ~= A   # holds
let q = numpy.linalg.qr, q(A)[1] @ q(A)[0] ~= A   # falsified
```

<!-- example: vocabulary verdicts fn=form -->
```
assuming A is positive definite and x != 0, x.T @ A @ x > 0   # holds
assuming A is symmetric and x != 0, x.T @ A @ x > 0   # falsified
```

A structure premise and a relation premise combine with `and`:
`assuming A is symmetric and det(A) != 0, inv(A) ~= inv(A).T`. The identity and
skew-symmetric premises reach the derive route as exact rewrites
(`A` is `I(n)`; `A.T` is `-A`), since sympy has no assumption for them;
positive semidefiniteness has none either, so it narrows sampling only.

### Real matrices only

Matrices and vectors are real in this release: a claim over `C^n` or
`C^(m,n)` is refused as misspecified, with the reason "matrices and
vectors are real-only in this release". Complex scalars are unaffected.

### Sugar

Three math-paper spellings are accepted as sugar. Each is **ambiguous**
against a scalar reading, so mathema resolves it from the operand's
declared type: on a matrix it is the matrix operation, on a scalar the
ordinary one.

| sugar | on a matrix | on a scalar |
|---|---|---|
| `A^T` | `A.T` (transpose) | `A ** T` (power) |
| <code>&#124;A&#124;</code> | `det(A)` | `abs(A)` |
| `A^-1` | `inv(A)` | `1 / A` (reciprocal) |

The type is known from a signature marker, an `R^(m,n)` domain, or a
`let ... be R^(m,n)` declaration:

```
let A be R^(n,n), A^T == A          #  ->  A.T == A
for A in R^(n,n), |A| >= 0          #  ->  det(A) >= 0
```

The bars are the determinant only as written: an explicit `abs(A)`
is always elementwise, and a rendered claim keeps the `abs(...)`
spelling for a matrix.

Because the reading is per-operand, one expression can mix the two:
with `A` a matrix and `c` a scalar, `inv(c * A) == c^-1 * A^-1` reads
`c^-1` as a reciprocal and `A^-1` as an inverse, and the record writes
it `inv(A*c) = inv(A)/c`.

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
decided by sympy's assumption engine. The identities below are checked
against a function of two square matrices of a shared dimension:

<!-- example: identities run -->
```python
from mathema.types import Mat

def f(A: Mat("n", "n"), B: Mat("n", "n")):
    return A
```

<!-- example: identities verdicts fn=f -->
```
det(A @ B) == det(A) * det(B)   # proven
(A @ B).T == B.T @ A.T   # proven
trace(A + B) == trace(A) + trace(B)   # proven
assuming A is symmetric, A.T == A   # proven
assuming A is orthogonal, A.T @ A == I(n)   # proven
assuming A is positive definite, det(A) > 0   # proven
assuming A is positive definite, trace(A) > 0   # proven
```

A relation sympy cannot close falls to the matrix-value probe: concrete
matrices are sampled (structure-narrowed, as above), both sides
evaluated, and the claim either holds across the draws or is falsified
with the witnessing matrices. A strict `derive` route reports the
honest `unknown` instead of sampling.

### Facts proven for every size

sympy's matrix algebra does not apply every fact of real matrices on
its own, so mathema adds a layer of lemmas, each true of real square
matrices of any size, before the two sides are compared:

| lemma | example |
|---|---|
| trace cyclicity (cyclic rotations of a product only) | `trace(A @ B @ C) == trace(C @ A @ B)` |
| trace of a transpose | `trace(A @ B.T) == trace(B @ A.T)` |
| linearity of trace | `trace(c*A + B) == c*trace(A) + trace(B)` |
| `@` distributes over `+`, on both sides | `(A + B) @ C == A @ C + B @ C` |
| scaling through a product | `(c*A) @ B == c*(A @ B)` |
| transpose of a sum and of a product | `(A @ B).T == B.T @ A.T` |
| a Gram product `A @ A.T` or `A.T @ A` is positive semidefinite | `det(A @ A.T) >= 0` |
| the trace is the sum of the eigenvalues, the determinant their product | `det(A) == prod(eigvals(A))` |
| the determinant of a scaled matrix | `det(c*A) == c**n * det(A)` |
| the rank of a Gram product is the rank of its factor | `rank(A @ A.T) == rank(A)` |

A proof that used one names it in its sketch and in the record's
`mathema.matrix_lemmas` meta. Each lemma is exact, so a relation it
does not close is not thereby false: the claim is sampled as before.

<!-- example: lemmas run -->
```python
from mathema.types import Mat, Vec

def f(A: Mat("n", "n"), B: Mat("n", "n"), C: Mat("n", "n"), c: float):
    return A

def form(A: Mat("n", "n"), x: Vec("n")):
    return A
```

<!-- example: lemmas verdicts fn=f route=derive -->
```
trace(A @ B) == trace(B @ A)   # proven
trace(A @ B @ C) == trace(C @ A @ B)   # proven
A @ (B + C) == A @ B + A @ C   # proven
(A + B) @ (A + B) == A @ A + A @ B + B @ A + B @ B   # proven
trace(A @ A.T) >= 0   # proven
det(A @ A.T) >= 0   # proven
trace(A) == sum(eigvals(A))   # proven
det(A) == prod(eigvals(A))   # proven
det(c*A) == c**n * det(A)   # proven
rank(A @ A.T) == rank(A)   # proven
```

<!-- example: lemmas verdicts fn=form route=derive -->
```
x.T @ (A @ A.T) @ x >= 0   # proven
```

What looks like a sibling of a lemma but is false is never proven, and
on the default route its sampling finds the witness:

<!-- example: lemmas verdicts fn=f -->
```
trace(A @ B @ C) == trace(B @ A @ C)   # falsified
trace(A @ B) == trace(A) * trace(B)   # falsified
det(A + B) == det(A) + det(B)   # falsified
A @ B == B @ A   # falsified
(A + B) @ (A + B) == A @ A + 2*(A @ B) + B @ B   # falsified
det(A @ A.T) > 0   # falsified
A * B == A @ B   # falsified
```

`det(A @ A.T) > 0` fails exactly where `A` is singular. A random matrix
is almost never singular, so one draw in eight of a matrix with no
declared structure has a zeroed row, the matrix analogue of the
boundary values a scalar draw includes.

Structure predicates are proven the same way when the structure
follows from the operands', by rules of their own (a product of two
symmetric matrices is not symmetric in general, and is never proven
so): a Gram product is symmetric and positive semidefinite, and
positive definite when its factor is invertible; `Y @ M @ Y.T` has the
symmetry and semidefiniteness of `M`; a transpose, inverse or power
keeps symmetry, orthogonality and definiteness, and swaps upper and
lower triangularity; products keep orthogonality, diagonality and
triangularity their factors share.

<!-- example: lemmas verdicts fn=f route=derive -->
```
is_symmetric(A @ A.T)   # proven
is_positive_semidefinite(A.T @ A)   # proven
assuming det(A) != 0, is_positive_definite(A.T @ A)   # proven
assuming A is orthogonal, is_orthogonal(A.T)   # proven
assuming A is positive definite, is_positive_definite(inv(A))   # proven
assuming A is upper triangular and B is upper triangular, is_upper_triangular(A @ B)   # proven
```

<!-- example: lemmas verdicts fn=f -->
```
is_symmetric(A @ B)   # falsified
assuming A is symmetric and B is symmetric, is_symmetric(A @ B)   # falsified
is_positive_definite(A.T @ A)   # falsified
```

A claim about `f(A)` stays sampled: the derive route reads the claim's
own matrix algebra, not the function's body. What stays sampled for
every claim: norms, the condition number, eigenvalues other than their
sum and product, `solve`, `pinv` and the decompositions.

### Through numpy's own functions

A function that calls numpy is read through numpy's
[definition rows](claims-transfer.md#definition-rows): `np.matmul(A,
A.T)` becomes `A @ transpose(A)`, and the claim is decided by the
matrix algebra above. `numpy.linalg.solve`'s definition row,
`f(a, b) ~= solve(a, b)` where `det(a) != 0`, is stated over a matrix
and a vector together, which a proof through definition rows does not
read, so a claim about a function calling it is decided by sampling.
The same identity in the grammar's own words, `A @ solve(A, b) ~= b`,
is proven (see the vocabulary above).

<!-- example: numpy-functions run requires=numpy -->
```python
import numpy as np

def gram(A: np.ndarray):
    return np.matmul(A, A.T)

def solve_for(A: np.ndarray, b: np.ndarray):
    return np.linalg.solve(A, b)
```

<!-- example: numpy-functions verdicts fn=gram -->
```
for A in R^(n,n), f(A).T == f(A)   # proven
for A in R^(n,n), f(A) == A   # falsified
```

<!-- example: numpy-functions verdicts fn=solve_for -->
```
for A in R^(n,n), b in R^n, assuming det(A) != 0, A @ f(A, b) == b   # holds
for A in R^(n,n), b in R^n, assuming det(A) != 0, f(A, b) == b   # falsified
```

## Runtime enforcement

`@enforce_structure` is the structure analogue of `@enforce_domain` and
`@enforce_dimensions`: it reads a parameter's structure markers and any
declared `is_<prop>(param)` claim, checks each matrix argument at call
time, and raises `ValueError` naming the property and the failing
argument before the function runs. It auto-declares the matching
predicate claim, so the precondition and its runtime guard are one
statement.

<!-- example: enforce-structure run inline requires=numpy -->
```python
from typing import Annotated

from mathema import enforce_structure
from mathema.types import PositiveDefinite, Shape

@enforce_structure()
def cholesky(A: Annotated[list, Shape("n", "n"), PositiveDefinite]): ...

cholesky([[1, 2], [2, 1]])   # ValueError: cholesky: A is not is_positive_definite (positive definite)
```

A property the registry cannot decide (a spectral check with no numpy)
is skipped, never a false rejection.

## Rendering

The matrix vocabulary renders through sympy's matrix printing, produced
on demand from the canonical claim rather than stored: `A.T` as `A^{T}`,
`det(A)` as `|A|`, a product as juxtaposition, `x.T @ A @ x` as
`x^{T} A x`, and the elementwise product `A * B` as `A \circ B`.
Nothing per-claim is kept in the record; the canonical statement is
the source, and `grammar.to_latex` renders it.

A matrix never reads as a commuting number in any rendering: a
product over the names a claim's domain, a signature marker or a
runtime type makes matrices keeps its written order, so
`A * B == B * A` (true, since `*` is elementwise) is recorded as
`A*B = B*A` and never as the tautology `A*B = A*B`, and
`C * (A @ B)` keeps its parentheses.

## Limits

The dependency `numpy` is optional (the `test` extra); element-wise and
structural checks fall back to pure Python, spectral checks decline
without it. Determinant and inverse sampling need numpy. Bars around any
matrix expression are its determinant, so `|A @ B|` is the same claim as
`det(A @ B)`, and the record writes it with the `det` spelling. A
matrix ordering (`A > B`) is undefined and refused as misspecified;
only scalar comparisons (a determinant, a trace, a norm) are decided.
A probe draw whose two sides differ by no more than the round-off its
own magnitudes produce (entries near `1e6` and `1e-9` cancelling in a
determinant) is not a counterexample, and the note says so; a loss of
precision that matters is the float companion's claim. Numerical rank
is `numpy.linalg.matrix_rank` with its default tolerance, so a rank
identity the derive route cannot close can fail at a draw whose
condition number a product squares past that tolerance;
`rank(A @ A.T) == rank(A)` itself is proven, and the proof is the
verdict.
