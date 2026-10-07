# Install

mathema needs Python 3.10 or newer and has two required dependencies, sympy
for the symbolic route and pyyaml for the record store. Install it into a
virtual environment rather than a system Python:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "mathema[all]"
```

or, in a project managed with uv:

```bash
uv add "mathema[all]"
```

`[all]` adds numpy for array-shaped claims, z3 for the nonlinear proof
rung, the MCP server, the native coverage reader and mathema-language for
string and structured-value domains; `pip install mathema`
is the minimal core, which already has `mathema check`, `verify`, `audit`,
`lock`, the derive route and the record store. pandas and polars are
separate extras, installed when your code uses them.

## Optional extras

Each extra adds one capability without making it everyone's dependency.

| Extra | Adds |
|---|---|
| `numpy` | array-shaped claims, matrix structure checks and array parameter synthesis |
| `pandas` | a parameter annotated `pd.Series` or `pd.DataFrame` is sampled as one, so a claim about a pandas function runs against the object the code expects |
| `polars` | the same for a parameter annotated `pl.Series` or `pl.DataFrame` |
| `smt` | z3's nonlinear real arithmetic as one rung of the `extensive` proof ladder (a native library of roughly 100 MB) |
| `mcp` | `mathema mcp serve`, which exposes mathema's checking tools to a coding agent |
| `coverage` | reading a native `.coverage` report, so the tests you already run count toward the implementation score (a `coverage.json` export works without it) |
| `symbology` | conventional notation for parameter and function names when claims are rendered |
| `language` | the `L[...]` domains over strings and structured values, from the [mathema-language](language.md) package |
| `all` | `numpy`, `smt`, `mcp`, `coverage` and `language` together, the recommended install |

```bash
pip install mathema            # the minimal core
pip install "mathema[pandas]"  # one extra at a time
```

## Offline by design

mathema makes no network calls. There is no account, no API key and no
telemetry, so it runs against a private codebase without source or claims
leaving the machine. The one command that fetches anything,
`mathema init --agents`, does so only when you run it explicitly.

## Next

The [quick start](quickstart.md) takes five minutes and one function from a
falsified claim to a proven one.
