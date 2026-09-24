# `mathema mcp`

mathema's library surface served as MCP tools, so an agent connects to
the same machinery every other mode uses, the one resolver, the one
gate, the reason-code registry, instead of shelling out and parsing
tables.

```bash
pip install "mathema[mcp]"
mathema mcp serve [--root .]
```

`serve` runs the server on stdio. Without the optional extra installed
the command prints the install hint and exits 2.

## Tools

| Tool | What it does |
|---|---|
| `resolve_target` | any target spelling (dotted name, `module:function`, file path) to its function keys and signatures |
| `adjudicate_target` | adjudicate one function, gated, with agent-shaped claim rows. `include` selects the row set: `declared` (default; what the surfaces actually state, which is what a re-check asks about), `suggested`, or `all`. Statements in `claims` are LINTED first, so a statement that does not parse comes back at parse cost with nothing adjudicated |
| `adjudicate_targets` | the same adjudication over SEVERAL targets in one call, column-oriented (`{prefix, cols, rows}`): the declared and verified stores are read once for the batch instead of once per target, and one envelope is returned instead of N |
| `verify_project` | the CI sweep: freshness, re-adjudication, record refresh, the gate; `keys` carries the sweep as structured per-key data (why, gate counts, claim rows) so nothing needs `lines` parsed |
| `describe_target` | one function's full detail view: identity, domains, claims with verdicts, tier ladder |
| `audit_targets` | the population report in the column-oriented compact shape; `cols` selects the columns, `filter` (explicit, never a default) keeps rows by derive_unlock class, claim status, or columnar substring (`blocker~loop`, `~mutual`), same-dimension terms OR together, dimensions AND across, and a filter's column references are always computed so an empty result means "nothing matched", never "never looked" |
| `reason_code` | selective code lookup: names, numeric ids (`2.18`), or whole groups (`loop`, `2`), singly or comma-separated; no argument returns the compact id/code/fixable index, never the full table, the machine twin of [Reason codes](../reason-codes.md) |
| `claim_grammar` | the claim-language lexicon, exactly as the library states it |
| `parse_claim` | parse and validate one claim statement without adjudicating, the authoring-loop linter: resolved name/statement/relation/route/domain rendered back explicitly, or the grammar's own error. Pass `target` and it also checks the statement against that function's real signature (arity, parameter names, quantified names) by inspection |
| `suggest_claims` | candidate claims for one function, `[name, statement, route, declared, aspect]` rows, declares, never verifies, and a suggestion never gates until adopted; identical columns to `mathema claims --suggest --format json` |
| `pending_decisions` | the human-decision queue, read-only: `[key, claim, kind, detail]` rows for pending supersessions, stale acceptances, stale intent acceptances, standing accepted risks, unaccepted unknowns and falsifications, and locked functions whose body moved; acceptance and unlock themselves stay CLI-only |
| `lock_target` | pin a function's form hash so `verify` fails if the body changes; the safe direction, so agents may do it. There is deliberately no unlock tool: a person runs `mathema unlock` |
| `project_index` | the generated `.mathema/index.yaml` map: system/module/function intents with acceptance rungs, keys, a sed-ready `span` per function, verified-record paths, concepts; run `mathema audit --index` (or `mathema docsync`) first if it reports the index missing |
| `implementation_coverage` | per-function implementation coverage without running the test suite: mathema's own probes and proofs supply the `probe` and `derive` sources, as `[key, percent, potential, sources, test_stale, traced, remedy]` rows plus the repo score; `run_tests=true` re-runs the suite under coverage first (slow, and it runs your tests) |
| `badges` | the three [badges](badges.md) (`implementation`, `intent`, `clarity`) and their `overall` over a target set, or rootwide when empty, with `[key, implementation, intent, clarity]` rows and the ASCII triangle |

## Which row set you get

`adjudicate_target` defaults to `include="declared"`. That is the set a
re-check after editing a claim is actually asking about, and it is
much cheaper: on a real fixture, 3483 bytes of every-row output
becomes 959 (and 3481 becomes 480), because the suggestion battery is
not just serialized but fully *adjudicated*; skipping it is 5x-26x
faster as well as ~75-85% smaller.

A function with no declared claims returns no rows plus a `hint`
naming `include="suggested"`, rather than silently handing back a
different kind of row than the one you asked for.

## The two agent payload shapes

Adjudication rows (`adjudicate_target`, and `mathema check --format
compact`) carry, per claim: `stance` (a closed four-value fold of the
open verdict, `supported`/`refuted`/`undecided`/`blocked`, to
branch on, with the verbatim `verdict` beside it for fidelity),
`source` (which authoring surface the claim came from: `declared`,
`docstring`, `decorator`, `types`, `suggested`, `builtin`, `ad_hoc`),
and `gates` (whether the row counts toward `passed`, a falsified
*suggestion* never does, and the flag makes that self-evident in the
payload). Envelope rule: `counterexample` is present iff the row is
refuted, `blocked_by` iff it is blocked; presence is the signal, so
a missing key can't be misread the way null or "" can.

The adjudication rows are also what `mathema verify --format json`
emits per key, so a CI artifact and an agent call carry the same
vocabulary.

Population output (`audit_targets`, and `mathema audit --compact`) is
column-oriented: `{"prefix": ..., "cols": [...], "rows": [[...],
...]}`, column names once, the shared dotted key prefix factored out
of every row, and `span` in the sed-ready `start:endp` form so the
follow-up read is targeted; it is a ready-made `sed -n` range, not a
line count. (`verify_project` separately returns `report`, the human
prose; the two used to share the name `lines` and are not the same
thing.) The caller names the columns it wants
(`cols`); the resolved selection is echoed back either way, and
analyses no chosen column needs are never computed at all.

One null policy across every cell: **null means the analysis was not
computed**; a computed-but-empty result is its typed empty value;
`[]` for lists, `0` for counts, `""` for the blocker of a derivable
function. `blocker` holds exactly a bare reason-code key (a real
enum over the code table), with its decorations split into
`blocker_params` (the domain parameters a resolvable branch names)
and `blocker_more` (the +N further-blocked-kinds count). `typed` and
`doc_quality` are `[n, m]` pairs, never "n/m" strings to parse;
`docsync` is the weighted 0-100 CDD-compliance percent (one int);
`mutates` lists the module-level names the function writes through
(the strongest scope relationship); `tested` is the closed enum
`"yes"`/`"no"`/`"no-report"`/`"outdated"` (a missing coverage report
is a different fact from an uncovered function, and a report older
than the function's own source file supports neither answer).

## Resources and prompts

The server also registers reference material and procedures, not just
tools. A tool answers a question the agent already knew to ask; a
resource is what it reads when it does not, and a prompt is a
procedure delivered at the moment it chooses what to do.

| Resource | Content |
|---|---|
| `mathema://reference/grammar` | the claim language by example, generated from `lexicon.LEXICON` |
| `mathema://reference/codes` | the reason-code table with each code's `derive_unlock` and hint |
| `mathema://reference/verdicts` | how to read a verdict: the stance fold, why `skipped` is not `falsified`, and why `passed` can be true beside a refuted row |

| Prompt | Bound to |
|---|---|
| `claim_this_function(target)` | the authoring procedure with that function's real signature and current candidates resolved into it |
| `triage_repository(targets)` | orient, then narrow to what is both risky and unevidenced |
| `diagnose_falsification(target, claim)` | the code-wrong / claim-wrong fork, and why the judgement is handed back |

Everything served is generated from what core already owns, so it
cannot drift from the code it describes. The wall covers it: no
resource or prompt takes a `verdict`/`accepted`/`stance`/`gates`/
`pin`/`verified_by` parameter, none is named to suggest accepting,
unlocking or PIN entry, and the material says plainly that acceptance,
unlocking and the [PIN](pin.md) are human acts done in the CLI. A test
asserts that over everything registered, not only over `TOOLS`.
`lock_target` is the deliberate one-way door: an agent may lock, and
only a person may unlock.

## Wire format

Tool payloads go over the wire as compact JSON. The SDK pretty-prints
a returned dict with a hardcoded `indent=2`, which roughly doubles the
column-oriented payloads that exist precisely to stop repeating key
names, so the server serializes compactly at the boundary instead:
`audit_targets` 1468 -> 738 bytes, `reason_code` 4242 -> 2627. Prose-
heavy payloads gain little (`claim_grammar`, 9%), which is expected;
the saving is concentrated where the shape was already compact.

The tools themselves still return dicts, so they stay directly
callable and testable, and nothing is duplicated into a structured
content block.

## What is deliberately absent

No tool makes an LLM call. No tool accepts a caller-supplied verdict:
claims are statements mathema adjudicates, and every verdict in every
payload is mathema's own. And there is no `accept` tool at all,
accepting evidence, owning risk, or marking a discovery is a human act,
done in the CLI ([`mathema accept`](accept.md)), never exposed to
agent tooling.

## Plugins

A mathema plugin can contribute tools by exposing an entry point in
the `mathema.mcp_tools` group whose callable returns plain functions.
The hook is fail-soft: a plugin that errors contributes nothing and
never breaks the server.
