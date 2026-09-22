---
name: Function failed to lift
about: A function you expected mathema to handle didn't lift to a closed form
title: ''
labels: derive-route
assignees: ''
---

**Run `mathema describe --issue` against the function first**

```bash
mathema describe mypackage.mymodule:my_function --issue
```

This prints a structured JSON report and, if you confirm, writes it to
`.mathema/issues/`. Attach that file below rather than pasting the
function's code or a screenshot of the terminal output, the file
carries the exact reason code, the blocking constructs with their
lines, any structural motifs found in the body, and the
mathema/sympy versions that produced it, which is what actually
narrows down the cause.

The report never includes your source unless you ask for it
(`--include-source`), and never makes a network request; you choose
what to attach here.

**Attach the file**

<!-- Drag the .mathema/issues/*.json file the command wrote into this box. -->

**What you expected**

<!-- What should have lifted, and why you expected it to. -->

**Anything else**

<!-- Optional: the surrounding code, if the failure only makes sense with more context. -->
