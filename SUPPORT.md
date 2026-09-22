# Support

## Documentation first

Most questions are answered at
[mathema.tetrionlabs.com](https://mathema.tetrionlabs.com):

- [Quick start](https://mathema.tetrionlabs.com/quickstart/): five
  minutes, one function, one claim.
- [The claim grammar](https://mathema.tetrionlabs.com/grammar/):
  everything you can say in a claim.
- [The derive route](https://mathema.tetrionlabs.com/derive-route/):
  which function shapes can reach `proven`, and what happens to the
  ones that cannot. Read this first if a claim you expected to prove
  came back `holds`.
- [Versioning and stability](https://mathema.tetrionlabs.com/stability/):
  what may change, and which versions are supported.

## Asking a question

Open a [GitHub issue](https://github.com/tetrionlabs/mathema/issues)
using the question or bug template. There is no separate forum or chat
channel, deliberately: issues are searchable, and the next person with
your question finds the answer.

## Reporting a problem with a verdict

If mathema reports a verdict you believe is wrong, that is the most
useful kind of report and it has its own flow:

```bash
mathema describe <target> --issue
```

This generates a structured failure report, including the claim, the
evidence, and the engine's own diagnostic codes, which you can attach
to a new issue. A verdict disagreement with a reproducible report is
treated as a correctness bug, not a support question.

## Security

Do not open a public issue for a security vulnerability. See
[SECURITY.md](SECURITY.md) for private disclosure.

## Commercial licensing and support

mathema is source-available under the Business Source License 1.1.
Production use is free for organisations under the thresholds set out
in [LICENSING.md](LICENSING.md); beyond them it requires a commercial
licence.

For commercial licensing, or for support arrangements beyond
best-effort issue response, contact **licensing@tetrion.co**.

## What to expect

This is a small project. Issues are read, and bugs affecting
correctness of a verdict take priority over everything else. There is
no response-time commitment on the free tier; a commercial agreement
is where response times get contractual.
