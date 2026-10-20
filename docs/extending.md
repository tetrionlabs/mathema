# Extending mathema

mathema discovers extensions through entry points. A package that
registers one can add a claim family, replace how something is shown,
or contribute MCP tools, without mathema knowing anything about it
beyond the name it registered under.

This page is for people writing such a package. It is not the API
reference: [that page](api.md) covers what you use to write and check
claims. The surface here is narrower in audience and wider in what it
exposes.

## The five entry-point groups

| Group | What it registers | Discovered by |
|---|---|---|
| `mathema.claim_families` | a claim-adjudication strategy: can this claim be proven, and by which routes | `mathema.families` |
| `mathema.capabilities` | a presentation hook: how should something already computed be shown | `mathema._providers` |
| `mathema.mcp_tools` | extra tools for the MCP server | `mathema.interfaces.mcp.server` |
| `mathema.target_resolvers` | a resolver for tagged target keys (`<tag>:...`) | `mathema._target_resolvers` |
| `mathema.runtime_types` | a runtime type adapter: how a vector, matrix or table is realised as the object a function receives (see [runtime types](runtime-types.md#adding-a-runtime-type)) | `mathema.runtime_types` |
| `mathema.languages` | a named language a claim quantifies over with `L[<name>]` | `mathema.languages` |
| `mathema.language_adaptors` | an adaptor turning an imported object (a schema class, a type) into a language, or `None` for an object it does not handle | `mathema.languages` |
| `mathema.language_refinements` | a refinement key inside `L[...]` (`len`, `depth`), the entry point's name being the key | `mathema.languages` |
| `mathema.lexicon` | worked claims (rows, sections, tags, example functions) that join mathema's lexicon | `mathema.lexicon` |

A claim family answers "can this be proven." A capability answers "how
should this be shown." They are separate mechanisms with separate
groups on purpose, and nothing is discoverable through both.

Discovery is fail-soft everywhere. A provider that raises on import is
skipped with a warning, and mathema falls back to its own behaviour.
Your extension being broken or absent never crashes someone's run.

## Runtime type adapters

An adapter registered under `mathema.runtime_types` follows the
`mathema.runtime_types.RuntimeTypeAdapter` protocol, described with
its `name`, `kinds`, `requires`, `detect`, `realise` and `observe` in
[runtime types](runtime-types.md#adding-a-runtime-type). Besides
`ALIASES`, it may state `USES`, a `BodyUses` naming the uses of a
parameter its type supports and a list does not:

```python
from mathema.runtime_types import BodyUses


class TorchTensorAdapter:
    name = "torch.Tensor"
    kinds = frozenset({"vec", "mat"})
    requires = ("torch",)
    ALIASES = {"th": "torch"}
    USES = BodyUses(
        attributes=frozenset({"T", "shape", "device"}),
        methods=frozenset({"mean", "sum", "numel", "detach"}),
        matmul=True,
        described="a torch tensor")
    ...
```

`attributes` are names read off the parameter (`x.shape`), `methods`
names called on it (`x.mean()`), `keyed` methods called with a column
name as the first argument (`df.groupby("k")`), and `matmul` says the
type can be an operand of `@`. `described` is how the record names the
type: `the body uses it as a torch tensor`.

An unannotated parameter is drawn as the adapter's type when every use
the body makes of it (apart from what every Python object has, such as
`.__class__`) is one the adapter declares, the function's module
imports the adapter's library, and no other imported library's adapter
supports the same uses. An attribute or method the adapter does not
declare rules it out, and the hint names that use; with two matching
libraries the parameter is drawn as a list and the hint names both. Declare only names your type has and a list lacks: a name a list
also has (`index`, `copy`, `sort`) would draw a list-using function as
your type. An adapter without `USES` is never chosen this way.

## Target resolvers

A fourth group, `mathema.target_resolvers`, turns a tagged
target key (`<tag>:src/ema#ema`) into ordinary callables. The entry
point's name is the tag it serves; the loaded object is a callable
`resolver(target, root)` returning a `Target` (from the `targets`
seam) whose values are Python callables standing in for the foreign
functions, or `None` for a target it does not handle, in which case resolution falls
through to the normal import path. The seam is consulted by
`mathema check`'s target resolution and by `verify`'s store-key
sweep, and it is fail-soft: a resolver that fails to load warns and
is skipped, and an unregistered tag fails (exit 2) with a message
naming the tag and the entry-point group an adaptor package registers
under.

What the returned callables must satisfy is the runtime contract in
`mathema.interfaces.runtime`: raise real exceptions for the failure
kinds, return non-finite floats for non-finite markers, and return
plain values otherwise. Calls arrive positionally.

## Registered safety predicates

A claim family registered under a name shaped like `is_<slug>_safe`
contributes that name to the safety-predicate vocabulary: the grammar
recognizes the claim form (`is_cyber_safe(x)`, or the postfix
`x is cyber safe`), and the claim adjudicates through the family's own
derive and probe halves, exactly as mathema's built-in members do. The
registered name IS the predicate, the same name-is-the-contract rule
target resolvers use, so a family owning several predicates registers
one entry point per predicate (they may load the same object).
`mathema.claim_families.SafetyFamily` is the assembly kit: pass the
base name, the derive half, and optionally the probe half, and the
family verdict contract (a falsification must carry its witness) is
enforced for you. The static tables (`routes.SAFETY_PREDICATES` and
kin) keep meaning core's own vocabulary; live membership is read
through `routes.safety_predicates()` / `routes.examine_predicates()`.

## Registered languages and adaptors

`L[<name>]` in a claim resolves through the registry in
`mathema.languages`: an in-process `register_language(name, obj)`
first, then the `mathema.languages` entry point of that name, then a
dotted path to a `Language` object, and last the `mathema.language_adaptors`
adaptors, each called as `adapt(obj)` on the imported object and
answering a `Language` or `None`. The adaptors are asked in an explicit
order: an adaptor may carry `__mathema_adaptor_priority__`, an int
(0 when absent), and a higher one is asked first, ties going to the
entry-point name. An adaptor that recognises a library's own model
classes sets a higher priority than a structural one, so a SQLAlchemy
class that is also a dataclass goes to the SQLAlchemy adaptor rather
than the dataclass one; `language_adaptors()` returns the registry in
that order, for a package that builds on the adaptors itself. A language is any object satisfying
the `Language` protocol; `language_problems(obj)` lists what one is
missing, and a registered or loaded object that fails it is skipped
with a warning, never served. Core ships no language: the alphabets,
predicate languages, hazard families and schema adaptors are the
`mathema-language` package's, and an unknown name is refused with the
vocabulary and the group to register under. An output-contract
predicate registered under a name shaped `output_<slug>` or
`is_<slug>_output` joins the grammar the way `is_<slug>_safe` does.

A language may also declare how a function over it refuses a value
outside it and what counts as answering a member, as two optional
attributes: `refusal`, a `Refusal`, and `defined_answer`, a
`DefinedAnswer`. `excluded_outside_domain` then holds an outside draw
to the declared refusal instead of any raise, and `is_language_defined`
holds a member to the declared answer instead of no unguarded crash.
Each names the exception classes that count (optionally narrowed by a
`when` test on the exception) and a `returns` test on a returned value,
and its `text` is how a witness names it. `Refusal.exit(2)` and
`DefinedAnswer.exit(0, 1)` are a command-line program's: `SystemExit`
with exit code 2, and a return or `SystemExit` with exit code 0 or 1.

```python
from mathema.interfaces.extension import DefinedAnswer, Refusal

class ArgvLanguage:
    ...
    refusal = Refusal.exit(2)
    defined_answer = DefinedAnswer.exit(0, 1)
```

Either may be absent or `None`, which keeps the claims' default reading,
and `language_problems` reports one of the wrong type.

## What a family probe returns

A family's empirical half is the callable it registers under
`"probe:algorithmic"`, called as `probe(fn, facts, claim, domain, rng,
trials)`, and it answers `None` to decline or a tuple:

| Form | Meaning |
|---|---|
| `(verdict, checked, cx)` | the verdict, how many trials ran, and the witness (a falsification must carry one) |
| `(verdict, checked, cx, established)` | the same, with `established` naming why the coverage was exhaustive, which is the only way a probe may say `proven` |
| either form, then a mapping | the mapping is merged into the record's `meta` |

The trailing mapping is how a probe states what it resolved while it
ran, the target language it held the output to, say, so that a `holds`
record is not silent about what held. Use namespaced keys
(`"my_package.target"`), since the record is shared with everything
else that writes to it. The mapping reaches the record whichever
report stands: when the probe's verdict stands it is the probe's meta,
and when the probe skipped and derive's `unknown` stands instead, it
is merged in beneath derive's own keys, which win on a clash. It is
copied, never shared. One key merges rather than
replaces: under `"mathema.language"` core already writes a description
of every `L[...]` binding, one entry per parameter, and a family's
entries sit beside those, so `{"mathema.language": {"return": [...]}}`
from `output_in_language` lands next to the parameter's own entry.
The mapping is an addition to the return shape, so a probe written
against the three- or four-element forms keeps working unchanged and
the extension API version stays where it is.

## Registered refinements

`L[json, depth <= 6]` hands the refinement `depth <= 6` to whatever is
registered under the key `depth`: `register_refinement(key, refine)` in
the process, or a `mathema.language_refinements` entry point named by
the key. `refine(language, interval)` returns the refined language, and
`RefinedLanguage(language, key, interval, measure=..., plain=...,
build=..., schema=..., hazard_kind=...)` builds one from a measure: it
keeps the members whose measure lies in the interval, samples by
rejection and then from `build`, visits the members at each bound first
(`plain`, else `build`), draws one past a bound as the outside member,
and merges `schema` into the persisted form. mathema registers no key;
`refinement_keys()` lists what is served, and a key nothing serves
raises `UnknownRefinement` naming them.

## Registered lexicons

A package's worked claims join mathema's lexicon through the
`mathema.lexicon` group. The entry point's name is the lexicon's name,
and the object it loads (a module is the usual choice) provides
`LEXICON`, a mapping of row keys to claim text, and optionally
`SECTIONS`, `TAGS` and `EXAMPLE_FUNCTIONS`, in the shapes
`mathema.lexicon` uses for its own. Installed, the rows are included in
`entries()`, `search()`, `find()`, `get()` and `show()`, a section reads
`<name>/<section>`, `find()` marks each row with the lexicon it came
from, and `origin(key)` says the same. A row reusing a key another
lexicon already has is skipped with a warning, mathema's own rows
winning. mathema's `LEXICON` and its golden snapshot stay mathema's
alone, so nothing about them depends on what is installed.

A package lexicon is held to the checks mathema's own is, by the same
code: `lexicon_problems(lexicon_source(name, module), golden=path,
expected=verdicts)` returns every check with a problem (it parses and
renders in both forms, matches its own golden snapshot, is a fixed
point of render and parse in both modes, has a stable canonical form
that reaches the same verdict, survives the declared store and the
verified record, states its missing-value policy, has sections that
partition it and tags that find it, has an example function for every
row, and lands on every pinned verdict and witness), and
`write_lexicon_golden` writes the snapshot for review. A row with an
example function is rendered and round-tripped as that function
completes it, so `for n in N` against `n: int` stays `N`, the form its
record states; a row without one renders the unannotated default.

## Injected facts

A resolver-built proxy may carry a `__mathema_facts__` attribute
holding a `Facts` instance (the `facts_ir` seam): what its frontend
could honestly state, with `tree=None` and a namespaced form hash
(`"<frontend>:<sha>"`). `mathema.analyze` returns it outright when present,
which is richer than the documentation-only fallback a source-less
callable would otherwise get. Form hashes are compared only within a
namespace, never across.

Every part of mathema that reads a callable's facts reads the injected
ones when they are present: checking and proving its claims, a
`funcs=`-bound function in another function's claim, suggestions,
docstring scoring, `describe`, `audit` and `status`. None of them
analyses the proxy's own Python source in their place. A derive route
that needs a body to lift finds `tree=None` and declines, saying so.
`docsync --write-docstrings` refuses such a callable with an error,
since the proxy's source file is not where the function it stands for
is written.

## Lifted bodies

A resolver that lifts a foreign function's body hands the engine a
document, carried in the `koine` field of the `Facts` it injects, as a
document or as its text. Two calls on the surface take such documents
as they stand.

`sibling_scope(fn, siblings)` binds the other functions of the program
a lifted body calls. `fn` is the proxy (or its `Facts`); `siblings`
maps the locator the body calls each one by to that function, as its
document or as a callable. The result is the scope the body is read
in, with each called function under the name the engine's rendering
gives it; set it on the proxy and derive reads through the calls:

```python
from mathema.interfaces.extension import sibling_scope

proxy.__mathema_scope__ = sibling_scope(proxy, {"src/shapes#scaled": scaled_doc})
```

A document is bound as the engine's rendering of it, with its own calls
bound from the same mapping; a callable is bound as given. A call whose
locator is not in the mapping stays unbound, and derive declines to read
through it rather than guessing.

`prove_bodies_equal(left, right, domain)` asks whether two lifted
bodies compute the same function on a domain, which is how an
equivalence family can record `proven` for a pair whose sides were
lifted by different frontends. `domain` maps the left body's parameter
names to bounds (a claim's bound, its text such as `"(0, inf)"`, or a
list `[lo, hi]` for a closed interval); the right body's parameters
align by position, and `siblings=` binds the functions either body
calls, as `sibling_scope` takes them. It answers for the mathematics
line of `f =:= g` alone, which is exact and takes no tolerance: a
falsification stands where the two bodies, executed at derive's witness
and compared exactly, disagree, however small the gap, and since it
samples nothing there is no computation line to report. The answer is a `BodyEquivalence`:

| Field | What it holds |
|---|---|
| `verdict` | `proven`, `falsified` or `unknown` |
| `rung` | the rung that reached it: `form`, `symbolic`, `closed-forms`, or `None` |
| `sketch` | the derivation, or why it stopped |
| `witness`, `point` | for `falsified`: what each body did at the executed point, and the point by parameter name |
| `meta` | `mathema.domain` (each bound as read), `mathema.corroboration`, and `mathema.timeout` when the cap fired |

```python
from mathema.interfaces.extension import prove_bodies_equal

answer = prove_bodies_equal(left_doc, right_doc, {"x": [-4, 4]})
if answer.verdict == "proven":
    ...  # record proven, naming answer.rung
```

Only the derive rungs run, under the extensive wall-clock cap; nothing
is sampled, which stays the family's own work. A falsification stands
only at a point both bodies were executed at; a disproof that no
executed point reproduces is `unknown`, flagged as a likely engine bug.
Two bodies that both raise at a point agree there when they raise the
same exception. When the documents name different languages the bodies
run in different runtimes, so their exception names are not compared:
a raise on one side matches any raise on the other, and the regions
where each side raises must still coincide.

## The extension surface

Everything a provider may import lives in
`mathema.interfaces.extension`, grouped into seams:

| Seam | Names |
|---|---|
| `source_text` | `analyze_source`, `SourceUnavailable`, `strip_docstring`, `local_names` |
| `loop_structure` | `classify_loop_header`, `bare_seq_name`, `seq_one_colon`, `diagnose_fold` |
| `claim_text` | `normalize`, `split_quantifier`, `split_relation`, `parse_raises` |
| `domain_shape` | `bound_to_sympy_set`, `domain_bound_from_json` |
| `rendering` | `render_loop_header`, `render_condition`, `Rendered`, `unparse_normalized`, `LOOP_KIND_LABEL` |
| `lift_structure` | `ConditionedLift`, `lift_conditioned` |
| `runtime` | `PointRuntime`, `POINT_RUNTIME_PROTOCOL`, `RUNTIME_CAPABILITIES`, `runtime_problems`, `verdict_ceiling` |
| `facts_ir` | `Facts`, `LoopFact` |
| `targets` | `Target`, `TargetError` |
| `inventory` | `function_dependencies` |
| `store` | `load_declared`, `load_verified`, `save_verified_entry` |
| `index` | `build_index` |
| `evidence` | `evidence_rank`, `SUPPORTED_VERDICTS` |
| `languages` | `Language`, `LanguageRef`, `StringLanguage`, `Problem`, `HazardValue`, `KINDS`, `LEVELS`, `HAZARD_KINDS`, `STRING_HAZARDS`, `language_problems`, `register_language`, `unregister_language`, `resolve_language`, `describe_language`, `language_vocabulary`, `UnknownLanguage`, `language_adaptors`, `RefinedLanguage`, `register_refinement`, `unregister_refinement`, `refinement_keys`, `UnknownRefinement`, `REFINEMENT_GROUP`, `Refusal`, `DefinedAnswer` |
| `lexicon` | `LEXICON_GROUP`, `LexiconSource`, `lexicon_source`, `lexicon_problems`, `write_lexicon_golden` |
| `families` | `SafetyFamily`, `OutputPredicateFamily`, `ProofResult`, `probe_trials`, `call_with_target`, `synth_other_params`, `format_point`, `pinned_float_env` |
| `sampling` | `sample_bound`, `shrink` |
| `body_scope` | `sibling_scope` |
| `body_equivalence` | `prove_bodies_equal`, `BodyEquivalence` |

`evidence_rank` ranks a route or an intent class, strongest lowest. A
compendium definition row's route, `axiom`, ranks with trusted testimony,
level with `probe`: a definition is trusted, not adjudicated, so it never
ranks above a plain `holds`.

Import from `mathema.interfaces.extension`, not from the module a name
happens to live in today. The module is free to move; the name on this
surface is not.

Anything not on this surface and not in the API reference is internal.
It may be renamed or deleted in any release, and no test anywhere will
warn you.

## Stability, and how it differs from the public API

The public API moves with mathema's own version. The extension surface
has its own counter, `EXTENSION_API_VERSION`, because it changes for
different reasons and on a different cadence.

- Adding a name or a seam leaves the version alone.
- Removing or renaming a name, or changing a signature or return
  shape, raises it. The previous spelling stays for one minor release
  and warns.

Declare the versions you support and check at import:

```python
from mathema.interfaces.extension import EXTENSION_API_VERSION

SUPPORTED = (1,)
if EXTENSION_API_VERSION not in SUPPORTED:
    raise ImportError(
        f"this package needs mathema extension API {SUPPORTED}, "
        f"found {EXTENSION_API_VERSION}")
```

Fail at import rather than at first call. A provider that half-works
against a mismatched mathema is harder to diagnose than one that
refuses to load.

## What mathema calls back on you

Registering a capability is a two-way contract. `SURFACE` says what you
may import; the other direction is what mathema calls on the object you
registered. One capability is called today, `symbology`, which renders
claim text in your own notation:

| Member | Called as | Returns |
|---|---|---|
| `symbol_for_param` | `symbol_for_param(name)`, once for each real parameter in the claim | the symbol, or `None` to decline |
| `symbol_for_func` | `symbol_for_func(name)`, once for each bound function name | the symbol, or `None` to decline |
| `show_missing` | `show_missing(claim)`, once per rendered claim | whether an unbounded domain prints its missing-values side, or `None` to keep the default |

All three members are optional, and the name is passed positionally. mathema
calls them on the object the entry point loads, so a module, a class
with static methods, or an instance all work. If either hook raises,
the provider is skipped for that render with a warning naming your
entry point, and the claim renders with mathema's own names. [Symbology and
rendering](symbology.md) covers which symbols are accepted and how the
renames appear in the claim text.

`CAPABILITY_PROTOCOLS` is the machine-readable form of this direction,
and `capability_problems(provider, capability)` checks a provider
against an entry in it. The registry is empty today, since `symbology`
is not declared in it, so there is no capability to check a provider
against yet, and `capability_problems` raises `KeyError` for any name.

## A minimal capability

```python
# my_package/symbology.py

class UnitsSymbology:
    """Symbols for a mechanics package."""

    @staticmethod
    def symbol_for_param(name: str) -> str | None:
        return {"mass": "m", "velocity": "v"}.get(name)
```

```toml
# pyproject.toml
[project.entry-points."mathema.capabilities"]
symbology = "my_package.symbology:UnitsSymbology"
```

With the package installed, the claim `for mass in [0, 10], velocity
in [0, 5], f(mass, velocity) >= 0` renders with your symbols, each
declared as a `let` binding. With it uninstalled, mathema renders its
own names:

```text
default        : ∀ mass ∈ [0.0, 10.0] ⊂ ℝ ∪ {absent, ∅}, velocity ∈ [0.0, 5.0] ⊂ ℝ ∪ {absent, ∅}, f(mass, velocity) ≥ 0
with provider  : let m = mass, let v = velocity, ∀ m ∈ [0.0, 10.0] ⊂ ℝ ∪ {absent, ∅}, v ∈ [0.0, 5.0] ⊂ ℝ ∪ {absent, ∅}, f(m, v) ≥ 0
```

## Reference

::: mathema.interfaces.extension
    options:
      members:
        - EXTENSION_API_VERSION
        - SURFACE
        - CAPABILITY_PROTOCOLS
        - capability_problems
