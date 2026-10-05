# The grammar's words

A claim about vectors and matrices is written with the grammar's own
words: `sum`, `mean`, `std`, `dot`, `norm`, `det`, `cumsum`,
`quantile` and the rest. Each word has one meaning, and this page
states it. Both routes read a word the same way: the probe evaluates
it exactly at every draw, and the derive route lowers it to sums over
a vector of any length, or to matrix algebra, when it proves a claim.

The words matter beyond the claims you write. A
[definition row](claims-transfer.md#definition-rows) maps a library's
function onto a word (`numpy.std` with `ddof=1` onto `std(a,
ddof=1)`), and a trusted row is taken at face value, so a proof that
reads `np.std(x, ddof=1)` through that row rests on what `std` means
here.

## Reading the table

`x` and `y` are vectors of length `n`, `A` and `B` matrices, `b` a
vector, and `x[i]` the element at position `i`, counted from 0. A
*value slot* is a position that holds a value; a *hole* is a missing
position (`None`, `nan`, `pd.NA`, see [missing values](missing-values.md)).

"Has a value" states where the word has one beyond its arguments
having the shapes its call names. Every vector in a claim's domain has
at least one element (`R^n` means `n >= 1`), so "always" means for
every such vector. Where a word has no value, a claim that uses it has
none there either: `std(x, ddof=1)` at a vector of one element, or
`inv(A)` at a singular `A`. A proof needs a premise that excludes those
inputs, stated after `assuming`: `dim(x) >= 2`, or `det(A) != 0`.

A keyword is written as in numpy, with the default shown. The derive
route reads the keywords the table names and leaves a claim with any
other (`axis=` among them) to the probe.

## The words

| Word | Computes | Has a value | Keywords | A hole | Derive reads it |
|---|---|---|---|---|---|
| `len(x)` | the number of slots of `x` | always | none | counts every slot, holes included | over vectors of any length |
| `dim(x, axis=0)` | the size of axis `axis` of `x`: a vector's length, a matrix's rows; `dim(A, 1)` its columns | always | `axis=0` | counts every slot, holes included | over vectors of any length |
| `count(x, axis=None)` | the number of value slots of `x` | always | `axis=None` | counts the value slots; 0 when every slot is a hole | over vectors of any length |
| `sum(x, axis=None)` | `x[0] + x[1] + ... + x[n-1]` | always | `axis=None` | reads the value slots; 0 when every slot is a hole | over vectors of any length |
| `prod(x, axis=None)` | `x[0] * x[1] * ... * x[n-1]` | always | `axis=None` | reads the value slots; 1 when every slot is a hole | over vectors of any length |
| `mean(x, axis=None)` | `sum(x) / n` | always | `axis=None` | reads the value slots; a hole when every slot is one | over vectors of any length |
| `var(x, ddof=0, axis=None)` | `sum((x[i] - mean(x))^2) / (n - ddof)`, the population variance at `ddof=0` and the sample variance at `ddof=1` | `n >= ddof + 1` | `ddof=0`, `axis=None` (derive reads `ddof`) | reads the value slots; a hole when every slot is one | over vectors of any length |
| `std(x, ddof=0, axis=None)` | `sqrt(var(x, ddof))` | `n >= ddof + 1` | `ddof=0`, `axis=None` (derive reads `ddof`) | reads the value slots; a hole when every slot is one | over vectors of any length |
| `min(x, axis=None)` | the least element of `x`; `min(a, b, ...)` the least of several numbers | always | `axis=None` | reads the value slots; a hole when every slot is one | over vectors of any length |
| `max(x, axis=None)` | the greatest element of `x`; `max(a, b, ...)` the greatest of several numbers | always | `axis=None` | reads the value slots; a hole when every slot is one | over vectors of any length |
| `median(x, axis=None)` | the middle element of `x` sorted, or the mean of the middle two when `n` is even | always | `axis=None` | reads the value slots; a hole when every slot is one | no, sampled only |
| `quantile(x, q)` | with `s` the sorted `x` and `h = (n - 1) * q`: `s[floor(h)] + (h - floor(h)) * (s[floor(h) + 1] - s[floor(h)])`, linear interpolation; a list of levels gives one quantile each | `0 <= q <= 1` | none | reads the value slots; a hole when every slot is one | no, sampled only |
| `cumsum(x, axis=None)` | entry `i` is `sum(x[0..i])` | always | `axis=None` | a hole stays at its position; entry `i` reads the value slots among `0..i` | over vectors of any length |
| `cumprod(x, axis=None)` | entry `i` is `prod(x[0..i])` | always | `axis=None` | a hole stays at its position; entry `i` reads the value slots among `0..i` | over vectors of any length |
| `cummax(x, axis=None)` | entry `i` is `max(x[0..i])` | always | `axis=None` | a hole stays at its position; entry `i` reads the value slots among `0..i` | over vectors of any length |
| `cummin(x, axis=None)` | entry `i` is `min(x[0..i])` | always | `axis=None` | a hole stays at its position; entry `i` reads the value slots among `0..i` | over vectors of any length |
| `abs(x)` | `abs(x[i])` at every position; the absolute value of a number | always | none | a hole stays a hole | over vectors of any length |
| `dot(x, y)` | `sum(x[i] * y[i])` for two vectors of one length; the matrix product when either argument is a matrix | the inner dimensions agree | none | reads the positions where both vectors hold a value; 0 when there is none | over vectors of any length, in matrix algebra |
| `norm(x, ord=None)` | `sqrt(sum(x[i]^2))`, the Euclidean norm of a vector and the Frobenius norm of a matrix; `ord=1` is `sum(abs(x[i]))` (a matrix's largest column sum), `ord=inf` `max(abs(x[i]))` (a matrix's largest row sum), `ord=2` on a matrix the largest singular value | always | `ord=None` (derive reads `ord`) | reads the value slots at every order; 0 when every slot is a hole; a matrix's `ord=2` norm with a hole entry is a hole | over vectors of any length, in matrix algebra |
| `outer(x, y)` | the matrix with entry `(i, j)` equal to `x[i] * y[j]` | always | none | not read over holes: a hole entry is nan | in matrix algebra |
| `kron(A, B)` | the Kronecker product: block `(i, j)` is `A[i, j] * B` | always | none | not read over holes: a hole entry is nan | in matrix algebra |
| `det(A)` | the determinant of `A` | `A` square | none | not read over holes: a hole entry is nan | in matrix algebra |
| `trace(A)` | `A[0, 0] + A[1, 1] + ... + A[n-1, n-1]` | `A` square | none | not read over holes: a hole entry is nan | in matrix algebra |
| `transpose(A)` | `A` with rows and columns exchanged, also written `A.T`; a vector is its own transpose | always | none | not read over holes: a hole entry is nan | in matrix algebra |
| `inv(A)` | the matrix `B` with `A @ B == I(n)` | `det(A) != 0` | none | not read over holes: a hole entry is nan | in matrix algebra |
| `solve(A, b)` | the `x` with `A @ x == b`, which is `inv(A) @ b` | `det(A) != 0` | none | not read over holes: a hole entry is nan | in matrix algebra |
| `I(n)` | the `n` by `n` identity matrix | `n` a whole number, `n >= 0` | none | not read over holes: a hole entry is nan | in matrix algebra |
| `matrix_power(A, k)` | `A @ A @ ... @ A`, `k` factors; `I(n)` at `k = 0`; `matrix_power(inv(A), -k)` for a negative `k` | `A` square, `k` whole; `det(A) != 0` for `k < 0` | none | not read over holes: a hole entry is nan | in matrix algebra |
| `diag(x)` | the square matrix with `x` on its diagonal and 0 elsewhere; of a matrix, the vector of its diagonal entries | always | none | not read over holes: a hole entry is nan | no, sampled only |
| `rank(A)` | the number of linearly independent rows of `A` | always | none | not read over holes: a hole entry is nan | in matrix algebra |
| `eigvals(A)` | the eigenvalues of `A`, each as often as its algebraic multiplicity, sorted by real then imaginary part | `A` square | none | not read over holes: a hole entry is nan | no, sampled only |
| `eigvalsh(A)` | the eigenvalues of a symmetric `A`, real and ascending | `A` square and symmetric | none | not read over holes: a hole entry is nan | no, sampled only |
| `cond(A)` | the largest singular value of `A` over its smallest | `A` of full rank | none | not read over holes: a hole entry is nan | no, sampled only |
| `pinv(A)` | the Moore-Penrose pseudoinverse of `A` | always | none | not read over holes: a hole entry is nan | no, sampled only |

## Exact on the mathematics line

The probe computes every word exactly and rounds the result once to
the nearest float: `mean(x)` is the exact mean of the elements drawn,
`det([[1, 2], [3, 4]])` is exactly `-2`, and `inv` of a singular matrix
has no value even where floating-point elimination would return one.
The derive route
computes over the rationals and reals, so the two routes agree on
every word, value for value.

A definition row's `~=` is exact on the mathematics line; the
tolerance applies to the computation line, which runs the library
itself.

## Words the derive route knows through bounds

`min`, `max`, `cummax`, `cummin`, `norm(x, ord=inf)` and `rank` have no
closed form as a sum, so the derive route reads each as a number known
only through facts: `min(x)` is one of the elements of `x` and at most
every one of them, so it is at most `mean(x)`; `cummax(x)[i]` is one of
`x[0..i]` and at least `x[i]`. A claim that follows from those facts is
proven; one that needs more is left to the probe.

## Words left to the probe

`median`, `quantile`, `diag`, `eigvals`, `eigvalsh`, `cond` and `pinv`
are evaluated by the probe only; a claim that uses one is never proven,
whatever its definition rows say. The exceptions are two identities the
derive route reads directly: `sum(eigvals(A))` is `trace(A)` and
`prod(eigvals(A))` is `det(A)`, the eigenvalues counted with their
algebraic multiplicity.

## Holes

The derive route reads vectors with no holes, as definition rows are
stated over inputs with nothing missing. What a word does with a hole
matters to the probe and to the missing-value lines under a claim: the
reductions read the value slots (`count`, `mean`, `std` and `sum`
count only those). Over a vector holding only holes, a reduction with
an identity gives it (`sum` 0, `prod` 1, `count` 0, `norm` 0, and
`dot` 0 where no position holds a value in both vectors), and one
without gives a hole (`mean`, `std`, `var`, `min`, `max`, `median`,
`quantile`). `len` and `dim` count every slot, and the running words
keep a hole at its own position. [Missing values](missing-values.md)
describes how a claim states what a function does with one.
