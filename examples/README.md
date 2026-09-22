# examples

Three different kinds of thing live here, and they are not
interchangeable. Two run; one is written to be read.

## `cdd_workflow.py`, runnable

```bash
python examples/cdd_workflow.py
```

The whole claim-driven loop end to end, with every LLM response
hard-coded as a mock so the example is deterministic and offline: a
human states an intent, a "model" writes a buggy implementation,
claims are stated, falsifications catch the bug, the counterexamples
feed the regeneration, and the second version is recorded as provably
a different function.

## `ci/`, runnable, once adapted

`github-actions.yml` and `gitlab-ci.yml` are working starting points
for wiring `mathema check` into a pipeline, including the report
formats each platform consumes (`--format github` for Actions
annotations, `--format junit` for the GitLab test widget). Change the
target names to your own package and they run as they are.

## `claims/`, illustrative, NOT loadable

`functions.py` is real, runnable code: `python examples/claims/functions.py`
adjudicates both functions.

`great_circle.yaml` and `fourier_sum.yaml` are **sketches in a
mathematician's notation**, not claim files mathema can load. They
exist to show what a claim set for a non-trivial piece of mathematics
looks like when someone thinks it through, which is a different
question from what the grammar accepts today. Concretely, do not copy
their spellings:

- `d(p, q)` here means the distance between two points. In [mathema's
  grammar](../docs/authoring.md) `d(...)` is **differentiation**, so
  those laws parse, and mean something else entirely.
- Points are written as tuples (`d((phi1, lam1), (phi2, lam2))`) where
  `gc_distance` really takes four scalars.
- Several laws carry English inside the law string (`... for any
  sampled path gamma from p to q on the sphere`), which the parser
  swallows into the right-hand side rather than understanding.
- `when:`, `status:`, `counterexample:`, and `refined_to:` are notation
  for this document. A real claims file states a region inside the law
  (`for x in [0, 1], ...`), and verdicts are written by mathema into
  `.mathema/verified/`, never authored by hand.

For the real schema, see [authoring claims](../docs/authoring.md); for
a claims file that loads, `mathema init <target>` scaffolds one.

The reason these are kept rather than rewritten is the content:
`fourier_sum.yaml`'s `uniform-convergence` entry is the clearest
statement of claim refinement anywhere in the repository, where a
falsification (the Gibbs phenomenon, ~8.95% overshoot at a jump) does
not kill the claim but produces its true domain, and the discovery is
recorded as a refined claim plus a permanent counterexample.
