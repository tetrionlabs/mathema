# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every output the documentation shows is the output a real run gives.

A page that shows code next to its output makes two promises: the code
runs, and it prints what the page says. This module holds the pages to
the second one. It reads the markdown, runs each marked example in a
fresh temporary directory, and compares what came out with what the
page shows, allowing only timing figures and absolute paths to differ.

Marking an example
------------------

An example is one or more fenced blocks, each preceded on the line
immediately above its opening fence by an HTML comment (invisible once
rendered):

    <!-- example: ID ROLE [OPTION ...] -->

Blocks sharing an ID form one example and run in page order, in one
Python namespace and one working directory. The roles:

- `file=NAME`: write the block to NAME in the working directory.
- `run`: run the block. A `python` fence executes in the example's
  namespace; a `bash`/`sh`/`shell` fence runs through bash, with
  `mathema` and `python` on PATH. What it prints is captured.
- `output`: what everything run since the previous `output` printed.
- `repl`: an interactive session, `>>> `/`... ` lines are input and
  every other line is the output shown for the input above it.
- `session`: a shell session, `$ ` lines are commands and every other
  line is output.
- `verdicts fn=TARGET`: one claim per line, each followed by
  `# verdict` (or all taking `expect=VERDICT`), checked against TARGET,
  a function defined earlier in the example or a `module:name`.

Options:

- `inline` (on a `run` block): a top-level expression line ending in
  `# text` is an assertion that evaluating it gives `text`, either the
  repr of its value or `ExcType: message` for an exception.
- `match=subset`: the shown output is an excerpt. Every shown line
  appears in the real output in the same order, and a detail line
  indented under an entry follows that entry directly.
- `after=ID`: first replay example ID's files and Python silently, for
  a page that builds one example on another.
- `route=ROUTE` (on `verdicts`): the route each claim is adjudicated on.
- `slow`: the example takes more than a few seconds; it carries the
  `slow_docs_example` marker so a quick run can deselect it.
- `requires=MODULE`: skip when MODULE is not importable.

A fence that looks like output but shows no run (a diagram, a
figure drawn for the page) is marked `<!-- illustration -->` instead.

`tests/data/docs_examples.txt` is the checklist: every marked example
by page, and every page's fenced blocks that look like output but are
not marked. Regenerate it after marking with

    python tests/test_docs_outputs.py --write-inventory
"""
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOCS = os.path.join(_ROOT, "docs")
_INVENTORY = os.path.join(_ROOT, "tests", "data", "docs_examples.txt")

_MARK = re.compile(r"^<!-- example: (.+?) -->\n```(\w*)\n(.*?)^```",
                   re.M | re.S)
_FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.M | re.S)
_ROLES = {"file", "run", "output", "repl", "session", "verdicts"}
_ILLUSTRATION = "<!-- illustration -->"


def _pages():
    """Every markdown page a reader sees: the docs tree and the README."""
    out = []
    for base, _, files in os.walk(_DOCS):
        out += [os.path.join(base, f) for f in files if f.endswith(".md")]
    return sorted(out) + [os.path.join(_ROOT, "README.md")]


def _rel(path):
    return os.path.relpath(path, _ROOT)


def _parse_mark(text):
    """Intent:
        Split one marker's text into (id, role, value, options).

    Raises:
        ValueError: the marker names no role, or an unknown one.
    """
    tokens = shlex.split(text)
    if len(tokens) < 2:
        raise ValueError(f"marker {text!r} needs an id and a role")
    ident, role_tok, *rest = tokens
    role, _, value = role_tok.partition("=")
    if role not in _ROLES:
        raise ValueError(f"marker {text!r}: unknown role {role!r}")
    opts = {}
    for tok in rest:
        key, eq, val = tok.partition("=")
        opts[key] = val if eq else True
    return ident, role, value, opts


def collect(path):
    """Intent:
        The marked examples on one page, as an ordered dict of
        id -> {"page", "parts", "options"}, each part a dict with the
        role, fence language, body and options of one block.
    """
    text = open(path, encoding="utf-8").read()
    examples = {}
    for m in _MARK.finditer(text):
        ident, role, value, opts = _parse_mark(m.group(1))
        ex = examples.setdefault(ident, {"page": _rel(path), "parts": [],
                                         "options": {}})
        ex["parts"].append({"role": role, "value": value, "lang": m.group(2),
                            "body": m.group(3), "options": opts,
                            "line": text.count("\n", 0, m.start()) + 1})
        ex["options"].update(opts)
    return examples


def _all_examples():
    out = []
    for page in _pages():
        for ident, ex in collect(page).items():
            out.append((f"{_rel(page)}:{ident}", ex))
    return out


def _looks_like_output(lang, body):
    """An unmarked fence that shows output: a text/console fence, a REPL
    transcript, a shell prompt followed by what it printed, or a line
    annotated with the verdict or exception it gives."""
    if lang in ("text", "console"):
        return True
    return bool(re.search(r"^>>> ", body, re.M)
                or re.search(r"^\$ \S", body, re.M)
                or re.search(r"#\s*(proven|holds|falsified|unknown|skipped)\b",
                             body)
                or re.search(r"#\s*[A-Z]\w*(Error|Exception):", body))


def inventory():
    """Intent:
        The checklist text: per page, the marked examples and the line of
        every unmarked fence that looks like output.
    """
    lines = ["# Documentation examples checked by tests/test_docs_outputs.py",
             "# Regenerate: python tests/test_docs_outputs.py --write-inventory",
             "#",
             "# [x] page:id  roles         a marked example, run and compared",
             "# [ ] page:line               an unmarked fence that shows output",
             "# [-] page:line               marked as an illustration, not a run",
             ""]
    covered = unchecked = 0
    for page in _pages():
        text = open(page, encoding="utf-8").read()
        marked_at = {m.start(0) + len(m.group(0).split("\n", 1)[0]) + 1
                     for m in _MARK.finditer(text)}
        rows = []
        for ident, ex in collect(page).items():
            roles = " ".join(p["role"] for p in ex["parts"])
            flags = " ".join(sorted(k for k in ex["options"]
                                    if k in ("slow", "requires", "after")))
            rows.append(f"[x] {_rel(page) + ':' + ident:<44} {roles}"
                        + (f"  ({flags})" if flags else ""))
            covered += 1
        for m in _FENCE.finditer(text):
            if m.start() in marked_at:
                continue
            if _looks_like_output(m.group(1), m.group(2)):
                line = text.count("\n", 0, m.start()) + 1
                if text[:m.start()].endswith(_ILLUSTRATION + "\n"):
                    rows.append(f"[-] {_rel(page)}:{line}")
                    continue
                rows.append(f"[ ] {_rel(page)}:{line}")
                unchecked += 1
        lines += rows
    lines += ["", f"# {covered} examples checked, {unchecked} output fences "
                  "not yet marked", ""]
    return "\n".join(lines)


# --- comparison ----------------------------------------------------------

_DURATION = re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s|sec|seconds)\b")


def normalise(text, workdir):
    """Intent:
        The text with what legitimately differs between runs replaced:
        the working directory's absolute path and timing figures.
        Trailing whitespace and surrounding blank lines are dropped.
    """
    for d in {workdir, os.path.realpath(workdir)}:
        text = text.replace(d, "<tmp>")
    text = _DURATION.sub("<time>", text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(lines).strip("\n")


def _indent(line):
    return len(line) - len(line.lstrip())


def matches(shown, actual, subset=False):
    """Intent:
        Whether `actual` is what `shown` shows: equal, or with `subset`,
        every shown line found in `actual` in the same order. Lines at
        the excerpt's outermost indentation are headings whose entries
        may be trimmed; below that, a continuation line (indented deeper
        than the line above it, or level with a continuation above it)
        must follow that line directly, so a detail is never matched
        under the wrong entry.
    """
    if not subset:
        return shown == actual
    have = actual.splitlines()
    top = min((_indent(ln) for ln in shown.splitlines() if ln.strip()),
              default=0)
    i, prev, prev_cont = 0, None, False
    for ln in shown.splitlines():
        cont = prev is not None and _indent(prev) > top and (
            _indent(ln) > _indent(prev)
            or (prev_cont and _indent(ln) == _indent(prev)))
        if cont:
            if i >= len(have) or have[i] != ln:
                return False
        else:
            while i < len(have) and have[i] != ln:
                i += 1
            if i == len(have):
                return False
        i += 1
        prev, prev_cont = ln, cont
    return True


# --- the driver: runs one example inside a subprocess ------------------

def _no_providers():
    """Capability providers installed in the environment change rendered
    output, so examples render with mathema's own defaults, the same
    isolation tests/conftest.py applies in-process."""
    from mathema import _providers
    _providers.entry_points = lambda **_: []
    _providers._discovered.cache_clear()
    _providers._load.cache_clear()


def _wrappers(workdir):
    """A bin directory with `mathema` and `python` on it, both this
    interpreter, the CLI isolated from installed providers."""
    bindir = os.path.join(workdir, ".bin")
    os.makedirs(bindir, exist_ok=True)
    cli = os.path.join(bindir, "mathema")
    with open(cli, "w") as fh:
        fh.write(f"#!{sys.executable}\nimport sys\n"
                 f"sys.path.insert(0, {os.path.dirname(__file__)!r})\n"
                 "from test_docs_outputs import _no_providers\n"
                 "_no_providers()\n"
                 "from mathema.cli import main\nsys.exit(main())\n")
    py = os.path.join(bindir, "python")
    with open(py, "w") as fh:
        fh.write(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
    for p in (cli, py):
        os.chmod(p, 0o755)
    return bindir


class _Driver:
    """Intent:
        Execute one example's parts in order, collecting for each part
        that shows output what the real run produced.
    """

    def __init__(self, workdir):
        self.workdir = workdir
        self.ns = {"__name__": "__main__"}
        self.buffer = []
        self.blocks = 0
        env = dict(os.environ)
        env.pop("VIRTUAL_ENV", None)
        env["PATH"] = _wrappers(workdir) + os.pathsep + env.get("PATH", "")
        self.env = env

    def _capture(self, fn):
        import contextlib
        import io
        import traceback
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                fn()
            except SystemExit:
                pass
            except Exception:
                traceback.print_exc()
        return out.getvalue()

    def _exec(self, code):
        """Execute `code` from a real file, so the functions it defines
        have source that `inspect` can read, as they would in a script."""
        self.blocks += 1
        path = os.path.join(self.workdir, f"_doc_block_{self.blocks}.py")
        with open(path, "w") as fh:
            fh.write(code + "\n")
        exec(compile(code + "\n", path, "exec"), self.ns)

    def _shell(self, body):
        body = re.sub(r"\\\n\s*", " ", body)
        r = subprocess.run(["bash", "-c", body], cwd=self.workdir, env=self.env,
                           capture_output=True, text=True)
        return r.stdout + r.stderr

    def run_part(self, part, silent=False):
        role, lang, body = part["role"], part["lang"], part["body"]
        if role == "file":
            with open(os.path.join(self.workdir, part["value"]), "w") as fh:
                fh.write(body)
            return None
        if role == "run" and lang == "python":
            if part["options"].get("inline") and not silent:
                return self._inline(body)
            text = self._capture(lambda: self._exec(body))
        elif role == "run":
            text = self._shell(body)
        elif role == "output":
            text, self.buffer = "".join(self.buffer), []
            return text
        elif role == "repl":
            return self._repl(body)
        elif role == "session":
            return self._session(body)
        elif role == "verdicts":
            return self._verdicts(body, part["options"])
        if not silent:
            self.buffer.append(text)
        return None

    def _inline(self, body):
        """Run the block, turning each asserted line into `code  # got`."""
        shown, pending = [], []
        assert_line = re.compile(r"^(\S.*?)\s+#\s(.*)$")

        def flush():
            if pending:
                self.buffer.append(self._capture(
                    lambda: self._exec("\n".join(pending))))
                pending.clear()
        for ln in body.splitlines():
            m = assert_line.match(ln)
            if m:
                try:
                    code = compile(m.group(1), "<doc>", "eval")
                except SyntaxError:
                    code = None
            if m and code is not None:
                flush()
                try:
                    got = repr(eval(code, self.ns))
                except Exception as e:
                    got = f"{type(e).__name__}: {e}"
                shown.append(f"{m.group(1)}  # {got}")
            else:
                pending.append(ln)
        flush()
        return "\n".join(shown)

    def _repl(self, body):
        out, stmt = [], []

        def run_stmt():
            if stmt:
                src = "\n".join(stmt) + "\n"
                out.append(self._capture(lambda: exec(
                    compile(src, "<doc>", "single"), self.ns)).rstrip("\n"))
                stmt.clear()
        for ln in body.splitlines():
            if ln.startswith(">>> "):
                run_stmt()
                out.append(ln)
                stmt.append(ln[4:])
            elif ln.startswith("... "):
                out.append(ln)
                stmt.append(ln[4:])
        run_stmt()
        return "\n".join(x for x in out if x)

    def _session(self, body):
        out = []
        for ln in body.splitlines():
            if ln.startswith("$ "):
                out.append(ln)
                out.append(self._shell(ln[2:]).rstrip("\n"))
        return "\n".join(x for x in out if x)

    def _target(self, spec):
        if ":" in spec:
            mod, _, name = spec.partition(":")
            if self.workdir not in sys.path:
                sys.path.insert(0, self.workdir)
            return getattr(importlib.import_module(mod), name)
        return self.ns[spec]

    def _verdicts(self, body, opts):
        from mathema.claims import check_conjectures, claim
        fn = self._target(opts["fn"])
        kw = {"route": opts["route"]} if "route" in opts else {}
        shown = []
        for ln in body.splitlines():
            if not ln.strip():
                continue
            text, _, comment = ln.partition("  #")
            text = text.strip()
            (p,) = check_conjectures(fn, [claim(text, **kw)])
            if comment:
                rest = comment.strip()
                word = re.match(r"[a-z]+", rest).group(0)
                shown.append(f"{text}  # {p.verdict}{rest[len(word):]}")
            else:
                shown.append(f"{text}  # {p.verdict}")
        return "\n".join(shown)


def expected_for(part):
    """Intent:
        What the page shows for one part, in the shape the driver
        reports it, or None for a part that shows no output.
    """
    role, body = part["role"], part["body"]
    if role == "output":
        return body
    if role in ("repl", "session"):
        return "\n".join(ln for ln in body.splitlines() if ln.strip())
    if role == "run" and part["options"].get("inline"):
        rx = re.compile(r"^(\S.*?)\s+#\s(.*)$")
        rows = []
        for ln in body.splitlines():
            m = rx.match(ln)
            if m:
                try:
                    compile(m.group(1), "<doc>", "eval")
                except SyntaxError:
                    continue
                rows.append(f"{m.group(1)}  # {m.group(2)}")
        return "\n".join(rows)
    if role == "verdicts":
        default = part["options"].get("expect")
        rows = []
        for ln in body.splitlines():
            if not ln.strip():
                continue
            text, _, comment = ln.partition("  #")
            rest = comment.strip() if comment else default
            rows.append(f"{text.strip()}  # {rest}")
        return "\n".join(rows)
    return None


def drive(spec_path):
    """The subprocess entry point: run the example in `spec_path`'s JSON
    and write each part's actual output next to it."""
    with open(spec_path) as fh:
        spec = json.load(fh)
    workdir = spec["workdir"]
    os.chdir(workdir)
    sys.path.insert(0, workdir)
    _no_providers()
    d = _Driver(workdir)
    for part in spec.get("before", []):
        if part["role"] in ("file", "run"):
            d.run_part(part, silent=True)
    results = [d.run_part(p) for p in spec["parts"]]
    with open(spec_path + ".out", "w") as fh:
        json.dump(results, fh)


# --- the tests -----------------------------------------------------------

_EXAMPLES = _all_examples()
_BY_ID = {}
for _key, _ex in _EXAMPLES:
    _BY_ID.setdefault(_ex["page"], {})[_key.split(":", 1)[1]] = _ex


def _params():
    out = []
    for key, ex in _EXAMPLES:
        marks = []
        if ex["options"].get("slow"):
            marks.append(pytest.mark.slow_docs_example)
        out.append(pytest.param(ex, id=key, marks=marks))
    return out


@pytest.mark.parametrize("example", _params())
def test_the_output_shown_is_the_output_a_run_gives(example, tmp_path):
    req = example["options"].get("requires")
    if req and importlib.util.find_spec(req) is None:
        pytest.skip(f"needs {req}")
    before = []
    if example["options"].get("after"):
        before = _BY_ID[example["page"]][example["options"]["after"]]["parts"]
    workdir = str(tmp_path)
    spec_path = os.path.join(workdir, ".example.json")
    with open(spec_path, "w") as fh:
        json.dump({"workdir": workdir, "parts": example["parts"],
                   "before": before}, fh)
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--drive",
                        spec_path], cwd=workdir, env=env, capture_output=True,
                       text=True, timeout=600)
    assert r.returncode == 0, f"the example driver failed:\n{r.stderr}"
    with open(spec_path + ".out") as fh:
        results = json.load(fh)
    compared = 0
    for part, actual in zip(example["parts"], results):
        shown = expected_for(part)
        if shown is None:
            continue
        compared += 1
        shown_n, actual_n = normalise(shown, workdir), normalise(actual, workdir)
        subset = part["options"].get("match") == "subset"
        assert matches(shown_n, actual_n, subset), (
            f"{example['page']}:{part['line']}: the page shows\n{shown_n}\n\n"
            f"but a real run gives\n{actual_n}")
    assert compared, "a marked example with nothing to compare checks nothing"


def test_only_timing_and_paths_are_allowed_to_differ():
    shown = "wrote <tmp>/x.yaml in <time>"
    assert normalise("wrote /t/w/x.yaml in 0.42s", "/t/w") == shown
    assert normalise("wrote /t/w/x.yaml in 3 ms", "/t/w") == shown
    assert normalise("proven, n=12", "/t/w") != normalise("proven, n=13", "/t/w")


def test_an_excerpt_keeps_each_detail_under_its_own_entry():
    real = "rec\n  A\n     detail a\n  B\n     detail b\n  C"
    assert matches("rec\n  A\n     detail a\n  C", real, subset=True)
    assert matches("rec\n  B\n     detail b", real, subset=True)
    # a detail shown under the wrong entry is not in the real output
    assert not matches("rec\n  A\n     detail b", real, subset=True)
    # order matters, and an excerpt is not a whole
    assert not matches("rec\n  C\n  A", real, subset=True)
    assert not matches("rec\n  A", real)


def test_every_marker_is_well_formed():
    """A marker with a typo would silently mark nothing; parse them all."""
    bad = []
    loose = re.compile(r"<!-- example: (.+?) -->")
    for page in _pages():
        text = open(page, encoding="utf-8").read()
        n_loose = len(loose.findall(text))
        try:
            n_parsed = sum(len(ex["parts"]) for ex in collect(page).values())
        except ValueError as e:
            bad.append(f"{_rel(page)}: {e}")
            continue
        if n_loose != n_parsed:
            bad.append(f"{_rel(page)}: {n_loose - n_parsed} marker(s) not "
                       "directly above a fence")
    assert not bad, "\n".join(bad)


def test_the_checklist_is_current():
    with open(_INVENTORY, encoding="utf-8") as fh:
        on_disk = fh.read()
    assert on_disk == inventory(), (
        "tests/data/docs_examples.txt is stale; regenerate it with "
        "`python tests/test_docs_outputs.py --write-inventory`")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--drive"]:
        drive(sys.argv[2])
    elif sys.argv[1:2] == ["--write-inventory"]:
        with open(_INVENTORY, "w", encoding="utf-8") as fh:
            fh.write(inventory())
        print(f"wrote {_rel(_INVENTORY)}")
    else:
        sys.exit("usage: test_docs_outputs.py --write-inventory")
