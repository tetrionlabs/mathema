# Intent, implementation and behaviour

A codebase can have every line exercised by its tests and still have very
little of what it promises stated, let alone verified, which is the gap a
single coverage percentage is worst at showing. mathema separates what you
know about code into three layers and measures each one on its own, so a
strength in one can't hide a gap in another.

| Layer | The question | Measured by |
|---|---|---|
| **Implementation** | How much of the code has anything actually exercised? | the share of statements reached by a test, a probe or a derive proof, taken together |
| **Intent** | How much of what the docstrings promise is claimed and verified? | how much of each docstring's stated behaviour has a verified claim behind it |
| **Clarity** (behaviour) | Of everything knowable about a function's behaviour, how much has been pinned down? | an information score over five dimensions: what it computes, what it accepts, its bounds and shape, how safely it runs, and where it can go wrong |

The layers are independent in practice as well as in principle. Tests that
call every function with a couple of convenient inputs push implementation to
100 without adding anything to intent, and a function with a detailed
docstring and no claims has intent on paper and nothing verified behind it.
Clarity counts a falsified claim as knowledge, because knowing exactly where a
function breaks is part of knowing the function, and leaves the question of
whether that break is acceptable to the verdicts themselves.

## Seeing all three at once

[`mathema badges`](modes/badges.md) computes the three scores for a project
and draws them as a triangle, with implementation and intent along the base
and clarity at the apex, so a lopsided profile has a lopsided shape. The
overall number is the share of the full triangle that the three scores fill,
`clarity * (implementation + intent) / 2` on the fractions, which collapses
toward zero when any layer is empty rather than averaging politely over it.
An illustrative example:

```text
        CLARITY 44
              ◆
             · ·
            ·   ·
           ·     ·
          ·       ·
         ·         ·
        ·           ·
       ·             ·
      ·       ●       ·
     ·      ···        ·
    ·     ······        ·
   ·   ·········         ·
  ·  ············         ·
 · ···············         ·
●·············+···●·········◆
  IMPL 100           INTENT 26
        overall 28
```

Every line is exercised, a quarter of what the docstrings promise is pinned
down, and the overall comes out at 28 where the mean of the three would have
said 57.

Intent and clarity roll up to the project by a mean weighted by how central
each function is in the call graph, so a function the rest of the code leans
on counts for more than a leaf helper, while implementation stays a plain
ratio of lines. Clarity has a ceiling set by how much of a function's
behaviour the claim vocabulary can express at all, so 100 belongs to pure,
fully claimed functions and anything above 60 is doing well; a function that
calls a library with no [compendium](claims-transfer.md) entry cannot reach
100 until one covers it.

[`mathema badges`](modes/badges.md) documents how each score is computed, and
[`mathema coverage`](modes/check.md) the implementation layer on its own.
