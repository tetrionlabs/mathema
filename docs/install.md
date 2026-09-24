# Install

mathema needs Python 3.10 or newer and has two required dependencies, sympy
for the symbolic route and pyyaml for the record store. Install it into a
virtual environment rather than a system Python:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install mathema
```

or, in a project managed with uv:

```bash
uv add mathema
```

That is the whole of what most people need: `mathema check`, `verify`,
`audit`, `lock`, the derive route and the record store all come with the core
install.

## Optional extras

Each extra adds one capability without making it everyone's dependency.

| Extra | Adds |
|---|---|
| `numpy` | array-shaped claims, matrix structure checks and array parameter synthesis |
| `smt` | z3 as an additional decision procedure for the derive route (a native library of roughly 100 MB) |
| `mcp` | `mathema mcp serve`, which exposes mathema's checking tools to a coding agent |
| `coverage` | reading a native `.coverage` report, so the tests you already run count toward the implementation score (a `coverage.json` export works without it) |
| `symbology` | conventional notation for parameter and function names when claims are rendered |
| `all` | `numpy`, `smt`, `mcp` and `coverage` together |

```bash
pip install "mathema[all]"
```

## Offline by design

mathema makes no network calls. There is no account, no API key and no
telemetry, so it runs against a private codebase without source or claims
leaving the machine. The one command that fetches anything,
`mathema init --agents`, does so only when you run it explicitly.

## Next

The [quick start](quickstart.md) takes five minutes and one function from a
falsified claim to a proven one.
