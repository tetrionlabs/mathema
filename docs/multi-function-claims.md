# Multi-function claims

Most claims speak about one function, spelled `f`. A claim may also
bind further function symbols and state laws that relate them: a
composition against a library function, a comparison against a sibling
in the same module, or full behavioural equivalence between two
implementations.

## Binding a second function

Three spellings, from most to least explicit:

```
let g = math.sqrt, for x in (0, 100], g(x) >= 0
```

The `let` spelling binds `g` to an importable function by its dotted
path and is the form the record keeps: it survives every store round
trip, because the path is text.

```python
mathema.check(mine, claims=[mathema.claims.claim("f(x) == g(x)", funcs={"g": other})])
```

`funcs=` on `claim()` binds a live callable and adjudicates
identically. When the callable is a module-level function importable
by its own dotted path, the record stores the binding in the `let`
spelling (`let g = mymodule.other, f(x) = g(x)`), so the claim
rebuilds from the record alone. A callable with no such path (a
lambda, a nested function, a function defined in `__main__`) has no
text spelling: the record keeps the law but not the binding, and a
later run reconstructing the claim from the record cannot re-bind `g`.

A bare call name (`g(x)` with no `let` and no `funcs=`) binds
automatically when a function of that name is defined in `f`'s module
or the calling scope. The record keeps the bare name, which binds the
same way again from `f`'s module; a function found only in the calling
scope (a notebook cell, a script) is not there for a later run to find.

## Laws over two functions

Once bound, the second symbol participates like any expression:

```
for x in [0, 4], f(x) == g(x) + 1
for x in [1, 8], f(g(x)) >= 0
```

Both routes handle these: derive substitutes each function's lifted
body and decides the combined expression; probe executes both real
functions on shared draws.

## Behavioural equivalence

```
f =:= g
f equiv g
```

The equivalence relation asks whether two implementations are the same
mathematics, and climbs a ladder:

1. **Identical canonical form.** Both functions lift to the same
   alpha-renamed shape, and the claim is proven by the form hash
   alone: two spellings of one computation.
2. **Symbolic difference.** The two lifts, positionally aligned,
   subtract to zero under the declared domain. A symbolic
   falsification here must reproduce code-versus-code before it
   stands, like every other disproof.
3. **Code-versus-code sampling.** Both real functions executed on
   shared draws. Evidence ceiling `holds`: sampling never proves.

`f =:= g` claims `f(x) == g(x)` at every point of the domain, so a
point where one side raises and the other returns a value is a
counterexample, and the executed raise is its witness. `x / x` and `1.0` agree everywhere
except `x = 0`:

```python
import mathema


def ratio(x: float) -> float:
    return x / x


def one(x: float) -> float:
    return 1.0

(p,) = mathema.claims.check(ratio, [mathema.claim("f =:= g", funcs={"g": one})])
print(p.verdict, p.counterexample)
```

```text
falsified x=0: f raised ZeroDivisionError, g returned 1
```

A point where both sides raise is not compared, and is counted in the
record's sampling meta. A complex result from one side counts as a
raise, unless that side is annotated `complex` or the claim is over
`C`. A declared tolerance is the whole allowance the two values get;
with none declared, they may differ by 1e-9 plus 1e-9 times the
larger magnitude.

The record annotates both sides' structural complexity, so an
equivalence between a one-liner and a loop reads as what it is.

## Another language on the other side

What an equivalence licenses, and what it never does, is the subject
of [Claims transfer](claims-transfer.md).

Because `g` may be any callable, the other implementation need not be
Python: `examples/cpp-equivalence/` checks a C++ `ema` (reached
through a ctypes shim over the C ABI) equivalent to the Python
reference, landing `holds` on shared-draw sampling with no special
integration. The example's README spells out the honest reading:
sampling never proves, the shim's library handle is real out-of-walk
state, a live-callable binding does not survive the record, and
safety claims never transfer between implementations, because they
are facts about an implementation and its language rather than about
the mathematics.

## Premises over bound functions

The `assuming` machinery composes with bindings: a premise may
reference the bound function's own claims, and the definedness
machinery reads registered partiality lemmas for functions the body
calls (see [Conditional claims and lemmas](conditional-claims.md)).
