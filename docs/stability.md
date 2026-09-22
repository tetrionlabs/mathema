# Versioning, stability and support

This page says what may change, when you will be told, and which
versions are supported. It is deliberately specific: a tool you point
at your own code owes you a straight answer about its own churn.

## Where mathema is today

mathema is at **0.6.0 and pre-1.0**. It is feature-complete and
heavily tested (over 2,000 tests), and the concepts are settled. The
Python API is **likely to change before 1.0**. That is the honest
statement, not a formality: if you build on the library surface today,
expect to make adjustments when 1.0 lands.

What that means in practice is that the guarantees below are graded.
Some surfaces are already stable because something outside mathema
pins them; others are explicitly still moving.

## What is stable now

**The claim grammar and the record format.** These are defined by
[claim-driven development](https://github.com/aaronbyrnephd/claim-driven-development),
a separate specification that mathema implements rather than owns.
A claim you write today keeps meaning what it means, and a record
written today stays readable, because changing either would be a
change to the spec and not a change to mathema. Every record stamps
`lineage.CDD_spec_version` and carries a top-level `schema_version`,
so a record always states the vocabulary it was adjudicated under.

**The verdict vocabulary.** `proven`, `holds`, `falsified`, `skipped`
and `unknown` mean what they mean. A verdict never silently changes
meaning; new evidence strengths arrive as colon subroutes on the
`route` field, which is documented as an open string.

**Reason codes.** `ReasonCode` and `Category` values are interface.
An existing name is never repointed at a different meaning and never
renamed.

**The command line.** Flags and output shapes may gain fields, but an
existing invocation keeps working within a major version. The
`--format json` output is additive: new keys may appear, existing
keys keep their meaning.

## What may change before 1.0

**The Python API.** Function signatures, return shapes, and module
layout in the `mathema` package. `docs/api.md` documents the intended
public surface, and it is where changes will be least disruptive, but
pre-1.0 it is not frozen.

**The extension surface.** The seams a plugin imports are stated as
data in `mathema.interfaces.extension.SURFACE`, versioned separately
by `EXTENSION_API_VERSION`. Additions leave that version alone; a
removal, rename, or changed signature raises it. See
[Extending mathema](extending.md).

**Anything marked experimental** in its own documentation.

## How you will be told

Changes are recorded in [the changelog](https://github.com/tetrionlabs/mathema/blob/main/CHANGELOG.md),
which follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Once 1.0 lands, mathema follows [semantic versioning](https://semver.org/):
a breaking change to a stable surface means a major version. Before
1.0, a minor version (`0.x`) may contain breaking changes to the
surfaces listed above as still moving, and the changelog says so
explicitly for each one.

**Deprecation.** When a stable surface is retired, it is first
deprecated rather than removed: the old spelling keeps working and
emits a `DeprecationWarning` naming its replacement, for at least one
minor release before removal. A deprecation is always listed in the
changelog under the release that introduced it. Deprecation warnings
are currently rare because there is little stable surface to retire
yet; this states the policy that governs the ones that come.

## Supported versions

| mathema | Status | Fixes |
|---|---|---|
| 0.6.x | Current | Security and correctness fixes |
| < 0.6 | Unreleased | None; 0.6.0 is the first public release |

Security reports are handled per [SECURITY.md](https://github.com/tetrionlabs/mathema/blob/main/SECURITY.md).

## Compatibility

| | Supported |
|---|---|
| Python | 3.10, 3.11, 3.12, 3.13 (tested on each in CI) |
| sympy | >= 1.12, < 2 |
| PyYAML | >= 6 |
| Operating system | Linux, macOS, Windows (pure Python; CI runs Linux) |

The core install depends only on sympy and PyYAML. Everything else
(numpy, z3, the MCP server, coverage) is an optional extra, so a
capability you do not use is not a dependency you carry.

Python versions are supported while they receive upstream security
support. A Python release reaching end of life is a minor-version
change in mathema, listed in the changelog, not a patch.

## Companion projects

mathema is the engine. These sit alongside it:

- **[claim-driven-development](https://github.com/aaronbyrnephd/claim-driven-development)**:
  the specification mathema implements. Independently maintained and
  separately licensed (CC BY-SA 4.0), so the claim vocabulary and the
  record format are not mathema's to change unilaterally. Anything
  that reads or writes that shape interoperates with mathema's records
  without importing mathema.
- **[mathema-symbology](https://github.com/tetrionlabs/mathema-symbology)**:
  conventional notation. A claim written in the reader's own symbols
  is a claim the reader will actually check, so this supplies
  domain-conventional symbols for parameter and function names when
  rendering claims. Install with `pip install "mathema[symbology]"`.
  See [Symbology and rendering](symbology.md).
- **[mathema-agents](https://github.com/tetrionlabs/mathema-agents)**:
  agent-facing setup. Skills and per-tool adapters that teach a coding
  agent how to drive the CDD loop properly. `mathema init --agents`
  vendors the right adapter for whichever tool it detects. The fetch
  is explicit and opt-in; mathema itself makes no network calls.
