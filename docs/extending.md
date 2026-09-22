# Extending mathema

mathema discovers extensions through entry points. A package that
registers one can add a claim family, replace how something is shown,
or contribute MCP tools, without mathema knowing anything about it
beyond the name it registered under.

This page is for people writing such a package. It is not the API
reference: [that page](api.md) covers what you use to write and check
claims. The surface here is narrower in audience and wider in what it
exposes.

## The four entry-point groups

| Group | What it registers | Discovered by |
|---|---|---|
| `mathema.claim_families` | a claim-adjudication strategy: can this claim be proven, and by which routes | `mathema.families` |
| `mathema.capabilities` | a presentation hook: how should something already computed be shown | `mathema._providers` |
| `mathema.mcp_tools` | extra tools for the MCP server | `mathema.interfaces.mcp.server` |
| `mathema.target_resolvers` | a resolver for language-tagged target keys (`ts:...`) | `mathema._target_resolvers` |

A claim family answers "can this be proven." A capability answers "how
should this be shown." They are separate mechanisms with separate
groups on purpose, and nothing is discoverable through both.

Discovery is fail-soft everywhere. A provider that raises on import is
skipped with a warning, and mathema falls back to its own behaviour.
Your extension being broken or absent never crashes someone's run.

## Target resolvers

A fourth group, `mathema.target_resolvers`, turns a language-tagged
target key (`ts:src/ema.ts#ema`) into ordinary callables. The entry
point's name is the tag it serves; the loaded object is a callable
`resolver(target, root)` returning a `Target` (from the `targets`
seam) whose values are Python callables standing in for the foreign
functions, or `None` for "not mine", in which case resolution falls
through to the normal import path. The seam is consulted by
`mathema check`'s target resolution and by `verify`'s store-key
sweep, and it is fail-soft: a resolver that fails to load warns and
is skipped, and an unregistered tag fails with a message naming the
missing adaptor package.

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

## Injected facts

A resolver-built proxy may carry a `__mathema_facts__` attribute
holding a `Facts` instance (the `facts_ir` seam): what its frontend
could honestly state, with `tree=None` and a namespaced form hash
(`"ts:<sha>"`). `mathema.analyze` returns it outright when present,
which is richer than the documentation-only fallback a source-less
callable would otherwise get. Form hashes are compared only within a
namespace, never across.

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
may import; `CAPABILITY_PROTOCOLS` says what mathema calls on what you
registered, and with which keyword arguments.

```python
from mathema.interfaces.extension import capability_problems
import my_package.diagram

assert capability_problems(my_package.diagram, "describe_diagram") == []
```

`capability_problems` returns a list of strings, empty when you
conform. Put it in your own test suite. It reports a missing member, a
member that is not callable, and a member that refuses a keyword
mathema passes.

## A minimal capability

```python
# my_package/diagram.py
from mathema.interfaces.extension import Rendered


class LabelLegend:
    def render_key(self) -> str:
        return ""


def render_structure(fdef, tier, *, globals_ns, name_map=None,
                     seq_params=frozenset(), depth=3, legend=None):
    ...  # return an object with a .render() -> str method


def render_lifted_tree(expr) -> Rendered:
    return Rendered(text=str(expr), available=True)
```

```toml
# pyproject.toml
[project.entry-points."mathema.capabilities"]
describe_diagram = "my_package.diagram"
```

With the package installed, `mathema audit --describe` renders through
your code. With it uninstalled, mathema renders its own plain text and
says nothing about the difference.

## Reference

::: mathema.interfaces.extension
    options:
      members:
        - EXTENSION_API_VERSION
        - SURFACE
        - CAPABILITY_PROTOCOLS
        - capability_problems
