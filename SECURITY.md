# Security

## Supported versions

| Version | Supported |
|---|---|
| 0.6.x | Yes |
| < 0.6 | Not applicable; 0.6.0 is the first public release |

Security fixes land on the current minor version. See
[versioning and stability](https://mathema.tetrionlabs.com/stability/)
for the wider support policy.

## Reporting a vulnerability

Please report a suspected security vulnerability privately rather than
through a public GitHub issue.

Email: security@tetrion.co

Include, if you can:

- A description of the vulnerability and its potential impact.
- Steps to reproduce it, or a minimal example.
- The mathema version (`mathema.__version__`) and Python version you
  found it on.

## Response

You'll receive an acknowledgment within 5 business days. We aim to
provide an initial assessment (confirmed, not a vulnerability, or need
more information) within 14 days of acknowledgment, and to keep you
updated on progress toward a fix after that.

## Scope

mathema is fully offline: no core function makes a network call (see
the README's "Network policy" section). A vulnerability report is
most useful when it identifies a concrete way that guarantee, or
another of mathema's stated behaviors, doesn't hold, or a way that
running `mathema check` against untrusted input (a claim string, a
function someone else wrote, a YAML spec file) could do something
other than what's documented.
