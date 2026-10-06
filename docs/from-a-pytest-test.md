# From a pytest test to a claim

An example-based test fixes what a function does at the inputs its author
chose. A claim states the same thing over a range of inputs and leaves the
choice of inputs to mathema, which looks for the ones that break it. This
guide takes one real test, writes its intent as a claim, and shows what
each of the two catches. It assumes the [quick start](quickstart.md).

## The test

numpy's `ptp` returns the range of an array, its largest value minus its
smallest. This is its own test, from
[`numpy/lib/tests/test_function_base.py`](https://github.com/numpy/numpy/blob/v2.5.3/numpy/lib/tests/test_function_base.py#L731-L744)
in numpy 2.5.3 (BSD-3-Clause, copyright NumPy Developers):

```python
class TestPtp:

    def test_basic(self):
        a = np.array([3, 4, 5, 10, -3, -5, 6.0])
        assert_equal(np.ptp(a, axis=0), 15.0)
        b = np.array([[3, 6.0, 9.0],
                      [4, 10.0, 5.0],
                      [8, 3.0, 2.0]])
        assert_equal(np.ptp(b, axis=0), [5.0, 7.0, 7.0])
        assert_equal(np.ptp(b, axis=-1), [6.0, 6.0, 6.0])

        assert_equal(np.ptp(b, axis=0, keepdims=True), [[5.0, 7.0, 7.0]])
        assert_equal(np.ptp(b, axis=(0, 1), keepdims=True), [[8.0]])
```

The test does two things well. It pins exact values at concrete arrays,
and the first array has negative entries, so its `15.0` is `10 - (-5)`
and not `10`. And its second half exercises `axis` and `keepdims` over a
two-dimensional array, which the claims below, written over vectors, do
not touch. Read as a sentence, the first assertion says: the range of a
vector is its largest value minus its smallest.

## A first attempt, and what it found

Suppose the sentence came out slightly wrong: the range is at most the
largest value. `ptp` is a library's function, so the claim goes in a
compendium file, a claims file whose keys are numpy's functions and whose
header names the library and the versions it applies to. `for a in
[-100, 100]^n` is a vector of any length with entries in that range, and
`f` is the function the key names.

<!-- example: ptp file=claims/numpy.claims.yaml -->
```yaml
compendium: numpy
versions: ">=2,<3"

numpy.ptp:
  claims:
    - name: at_most_the_largest
      statement: "for a in [-100, 100]^n, f(a) <= max(a)"
```

Naming the file adjudicates every row in it against the numpy that is
installed:

<!-- example: ptp run -->
```bash
mathema verify claims/numpy.claims.yaml --root .
```

<!-- example: ptp output wrap=80 -->
```text
note numpy.ptp: at_most_the_largest initially falsified: the installed library
    does not do what the row states:
  (i) to record the falsification as a discovery, run: mathema accept numpy.ptp
      at_most_the_largest --as discovery
  (ii) correct the row in claims/numpy.claims.yaml, then run: mathema accept
      numpy.ptp at_most_the_largest --as superseded
FAIL numpy.ptp: library claims from claims/numpy.claims.yaml; no baseline
    record; 1 proven, 1 holds, 1 falsified  <- 1 falsified claim(s)
     note definition: numpy.ptp gives no value at a = [1.7976931348623157e+308,
         -1.7976931348623157e+308], axis = None, out = None, keepdims = <no
         value>, a magnitude corner where the exact value is finite: a finding
         about its computation; the row stands
0 unchanged since the last run (not run again), 1 checked, 1 problem(s)
grammars detected: mathema; verified by this run: mathema
```

Falsified, and the record keeps the input that did it:

<!-- example: ptp run -->
```bash
grep -m1 counterexample .mathema/verified/numpy.ptp.yaml
```

<!-- example: ptp output -->
```text
      counterexample: "a = [-15.864774136188714], axis = None, out = None, keepdims = <no value>: 0.0 vs -15.864774136188714"
```

One value, and a negative one: the range of `[-54.43]` is 0, and the
largest value is -54.43. Whenever every value is negative the range sits
above the largest value. The test's own first array says the same in
another way, since its range of 15 is above its largest value of 10; the
claim found a case without anyone choosing the array. The other
parameters were passed at numpy's defaults, as the witness says.

## Record the discovery

The code is right and the claim was wrong. That is a discovery about the
function, and `mathema accept --as discovery` records it as one: the
falsified claim moves to the record's discoveries section with its
witness, and the corrected claim, adjudicated before anything is written,
takes its place in the file. `--yes` answers the confirmation prompt,
which is fine when a person types the command:

<!-- example: ptp run -->
```bash
mathema accept numpy.ptp at_most_the_largest --as discovery --corrected "for a in [-100, 100]^n, f(a) == max(a) - min(a)" --by "Ada Lovelace" --yes
```

<!-- example: ptp output match=subset wrap=80 -->
```text
accepting numpy.ptp :: at_most_the_largest (verdict falsified) as discovery, by
    Ada Lovelace
  - move at_most_the_largest to the record's discoveries section (superseded_by:
      at_most_the_largest_corrected), keeping its counterexample as the witness
  - declare the stated corrected claim 'at_most_the_largest_corrected': 'for a
      in [-100, 100]^n, f(a) == max(a) - min(a)', checked now: holds over 131
      trials
  - rewrite claims/numpy.claims.yaml: replace declared claim
      'at_most_the_largest' with 'at_most_the_largest_corrected'
written: move at_most_the_largest to the record's discoveries section
    (superseded_by: at_most_the_largest_corrected), keeping its counterexample
    as the witness; declare the stated corrected claim
    'at_most_the_largest_corrected': 'for a in [-100, 100]^n, f(a) == max(a) -
    min(a)', checked now: holds over 131 trials; rewrite
    claims/numpy.claims.yaml: replace declared claim 'at_most_the_largest' with
    'at_most_the_largest_corrected'
declared layer: claims/numpy.claims.yaml now declares
    at_most_the_largest_corrected in place of at_most_the_largest (the
    superseded claim stays in the record's discoveries section):
  - name: at_most_the_largest_corrected
    statement: "for a in [-100, 100]^n, f(a) == max(a) - min(a)"
    route: probe
```

`holds over 160 trials`, on the probe route: the corrected claim is the
test's sentence, run at 160 vectors mathema chose. The record's sampling
line says how: `a~[-100.0, 100.0]^n, seed=20260718, n=160`, vectors of
two to eight entries drawn inside the range. `axis`, `out` and `keepdims`
are not on it, since nothing drew them: the note says they were held at
numpy's defaults. It is evidence, not proof. The corrected claim carries `route:
probe`, which `accept` wrote, so the derive route was not tried for it;
the first attempt's record shows what it met: `derive: underivable (a is
a vector or matrix, which the scalar derive route does not read, and the
matrix algebra did not close the claim)`.

## Claims the test never stated

The file is yours to add to. Two more things true of a range, that no
assertion in `test_basic` states:

<!-- example: ptp file=claims/numpy.claims.yaml -->
```yaml
compendium: numpy
versions: ">=2,<3"

numpy.ptp:
  claims:
    - name: at_most_the_largest_corrected
      statement: "for a in [-100, 100]^n, f(a) == max(a) - min(a)"
      route: probe
    - name: never_negative
      statement: "for a in [-100, 100]^n, f(a) >= 0"
    - name: unchanged_by_a_shift
      statement: "for a in [-100, 100]^n, let s = mathema.f.shift_seq, let c be [-5, 5], f(s(a, c)) == f(a)"
```

<!-- example: ptp run -->
```bash
mathema verify claims/numpy.claims.yaml --root .
```

<!-- example: ptp output -->
```text
ok   numpy.ptp: library claims from claims/numpy.claims.yaml; claims changed; 1 proven, 4 holds, 0 falsified
     note definition: numpy.ptp gives no value at a = [1.7976931348623157e+308, -1.7976931348623157e+308], axis = None, out = None, keepdims = <no value>, a magnitude corner where the exact value is finite: a finding about its computation; the row stands
0 unchanged since the last run (not run again), 1 checked, 0 problem(s)
grammars detected: mathema; verified by this run: mathema
```

`let s = mathema.f.shift_seq, let c be [-5, 5]` names adding the same
constant to every entry; the range does not move. The `1 proven` is
`dependencies_current`, the claim `verify` adds to every record that what
the function depends on has not changed.

## What each one still does

The test still does what the claims do not: it fixes the exact values,
and it covers the two-dimensional cases and the `keepdims` argument. The
claims do what the test cannot: they say the sentence once, over every
vector in a range, and each sweep runs it again at inputs a person did
not pick. Keep both. When one of your own tests reads as a sentence about
every input, that sentence is a claim.

## For a function of your own

A claim about your own function does not need a compendium file. Put it
in the function's docstring under `Claims:`, as the [quick
start](quickstart.md#move-it-into-the-code) does, or in an ordinary
claims file, as [the CDD loop](tutorial.md) does; [Authoring
claims](authoring.md) lists the four places and which one wins.
[Add claims to an existing codebase](existing-codebase.md) starts from a
package with none. The compendium file stays the right place for a claim
about a library you call; [See what mathema knows about a library you
call](library-claims.md) shows what mathema already states about numpy
and how your own rows join in. [The claim grammar](grammar.md) has one
example per form used here: the `[a, b]^n` space, `let c be [-5, 5]` and
`let s = mathema.f.shift_seq`.
