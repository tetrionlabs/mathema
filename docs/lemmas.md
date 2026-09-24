# Lemmas: one claim resting on another

A lemma in mathema is not a separate kind of object. There is no
`lemma` keyword, no lemma field in the record, and nothing to declare.
A claim becomes a lemma **by being referenced**: another claim names it
in an `assuming` clause, and from then on the two are related by
evidence.

```
assuming grows holds, for x in [0,10], f(x) == 2*x
```

That claim rests on a sibling named `grows`. If `grows` is established,
this one is adjudicated normally. If it is not, this one does not
silently proceed: it reports that what it rests on was never settled.

Two spellings, and they ask for different strengths:

```
assuming grows holds, for x in [0,10], f(x) >= 0
```

```
assuming base_case is proven, for n in [2, 30] subset Z, f(n) == f(n-1) + f(n-2)
```

`holds` accepts either a proof or empirical agreement. `is proven`
accepts only a proof. Nothing else is interpreted as a verdict
reference: `X is falsified` and `X is unknown` are not premises, because
a claim that failed is not something to build on.

## What a reference actually does

Three separate mechanisms fire, and it is worth keeping them apart
because they fail differently.

**It gates.** If the referenced claim does not reach the strength
asked for, the dependent claim comes back `unknown`, with
`meta["mathema.premise"]` naming why. The claim itself was never
attempted; only what it rests on failed. That is an undecided state,
not a refutation, and the note says which prerequisite was missing.

**It caps.** A conclusion can never be stronger than what it rests on.
A lemma established only empirically caps its dependents at `holds`
even when their own proof would otherwise be exact.

**It lends.** A discharged lemma's relation is handed to the proof as
an assumption, which is what makes this modus ponens rather than
bookkeeping. This is the part that turns a chain of claims into a
chain of reasoning.

## Chaining

Claims are adjudicated in dependency order, not declaration order, so a
lemma may be written after the claim that uses it. The results still
come back in the order you wrote them.

```python
from mathema.claims import check_conjectures, claim

def scale(x: float) -> float:
    """Twice x."""
    return 2 * x

out = {p.name: p for p in check_conjectures(scale, [
    claim("for x in [0,10], f(x) >= x", name="grows", route="derive"),
    claim("assuming grows is proven, for x in [0,10], f(x) >= 0",
          name="nonneg"),
    claim("assuming nonneg holds, for x in [0,10], f(x) + 1 > 0",
          name="offset"),
])}
for name, p in out.items():
    print(f"{name:<8} {p.verdict}")
```

Each link is proven, and `offset` is proven on the strength of
`nonneg`, which is proven on the strength of `grows`:

```text
grows    proven
nonneg   proven
offset   proven
```

## The weakest link bounds the conclusion

When a claim rests on several lemmas, the weakest one sets the ceiling.
This is the rule that stops a chain from laundering sampled evidence
into a proof.

```python
out = {p.name: p for p in check_conjectures(scale, [
    claim("for x in [0,10], f(x) >= x", name="grows", route="derive"),
    claim("for x in [0,10], f(x) >= 0", name="sampled", route="probe"),
    claim("assuming grows is proven and sampled holds, "
          "for x in [0,10], f(x) + 1 > 0", name="rests_on_both"),
])}
for name, p in out.items():
    cap = p.meta.get("mathema.capped_by")
    print(f"{name:<14} {p.verdict}" + (f"    capped_by={cap}" if cap else ""))
```

```text
grows          proven
sampled        holds
rests_on_both  holds    capped_by=sampled
```

`rests_on_both` could have been proven on its own. It is reported as
`holds` because one of the things it rests on was only sampled, and
`meta["mathema.capped_by"]` names which one. Read that field when a
claim you expected to prove came back weaker: it points at the lemma to
strengthen, not at the claim you were looking at.

## Lending has a domain guard

A lemma lends its content only where it was established. A lemma proven
over `x in [0,10]` says nothing about `x = -3`, so if the dependent
claim quantifies over a different region the lemma still gates and
still caps, but its relation is not handed to the proof. This is
deliberately strict: the bounds must agree, not merely overlap.

## When a prerequisite cannot be resolved

```python
(p,) = check_conjectures(scale, [
    claim("assuming absent holds, for x in [0,10], f(x) >= 0",
          name="orphan")])
print(p.name, p.verdict, "|", p.meta["mathema.premise"])
print("note:", p.note)
```

```text
orphan unknown | missing-prerequisite
note: prerequisite 'absent' is not a claim in this batch, nothing to rest this claim on
```

The other resolution failures report themselves the same way. A name
matching more than one claim is `ambiguous-reference` rather than being
quietly bound to the first. A cycle skips every claim in it, each
note naming both claims. A premise that mixes a verdict reference with a relation in one
clause is refused rather than half-interpreted.

A premise can also reach outside the batch, to another function's
claim, by qualifying the name:

```
assuming numpy.clip.clip_lower holds, for w in [-50, 50], f(F0,k,m,-w,c) == f(F0,k,m,w,c)
```

Resolution prefers an in-batch sibling, then the verified layer. An
external row enters at declared status and satisfies nothing until it
has been accepted or genuinely verified, so a library stub cannot
quietly discharge your premise.

## Two things that are not lemmas

**Partiality lemmas** are a different feature with a confusingly
similar name. They are Python-registered facts about where a function
raises, used by the derive route to reason about partial functions, and
they are not claims. See
[Conditional claims](conditional-claims.md).

**The outcome clause** looks like implication but is not adjudicated:

```
f(x) > 0 => self.stays_positive
```

Everything after `=>` names a sibling claim that should follow when
this one holds. It is captured verbatim and travels in the record, but
nothing currently derives the named claim from it. If you want one
claim to actually rest on another, use an `assuming` premise, which is
what this page describes.

## Limits

Resolution is by name, so names must be unique within what is being
adjudicated together. A bare sibling name without `holds` or `is
proven` is a different construct: it borrows that sibling's relation as
a region constraint rather than consulting its verdict, and it requires
the sibling to carry a plain relation.

Lending recurses as far as the chain goes, but each link is only as
good as its own evidence, and the cap propagates the whole way. A long
chain resting on one sampled lemma is a sampled result at the end of it,
which is the honest outcome rather than a limitation to work around.
