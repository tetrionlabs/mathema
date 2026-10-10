#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Render the README's hero image from a real run.

Writes `rates.py` into a temporary directory, runs a short
interactive session against it in a fresh interpreter, and draws the
captured transcript as a terminal window in
`docs/assets/readme-hero.svg`. Every line of output in the image is
what that run printed; only the line breaks of rows wider than the
window are changed.

Usage:
  uv run python scripts/readme_hero.py [--out docs/assets/readme-hero.svg]
"""

from __future__ import annotations

import argparse
import html
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import textwrap

ROOT = pathlib.Path(__file__).resolve().parents[1]

SOURCE = '''\
def discount_factor(rate: float) -> float:
    """A discount factor that divides by one minus the rate."""
    return 1 / (1 - rate)
'''

SESSION = [
    "import mathema",
    "from rates import discount_factor",
    'full_range = mathema.claim("for rate in [0, 1], f(rate) >= 1", name="full_range")',
    'safe_range = mathema.claim("for rate in [0, 0.99], f(rate) >= 1", name="safe_range")',
    "mathema.check(discount_factor, claims=[full_range, safe_range])",
]

# Runs inside the child interpreter: each statement is compiled in
# "single" mode, as the interactive prompt does, so an expression
# statement prints its repr. Installed capability providers are switched
# off so the record shows mathema's own defaults.
_DRIVER = '''\
import contextlib, io, json, sys
from mathema import _providers
_providers.entry_points = lambda **_: []
_providers._discovered.cache_clear()
_providers._load.cache_clear()
ns = {"__name__": "__main__"}
out = []
for stmt in json.loads(sys.argv[1]):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(compile(stmt + "\\n", "<stdin>", "single"), ns)
    out.append(buf.getvalue())
print(json.dumps(out))
'''

WIDTH = 100          # columns before a row is re-flowed
FONT_SIZE = 14
CHAR_W = 8.8         # advance of one monospace cell at FONT_SIZE
LINE_H = 20
PAD_X = 26
PAD_TOP = 52
PAD_BOTTOM = 22

COLOURS = {
    "bg": "#0f1419",
    "bar": "#1b2129",
    "text": "#d6dde6",
    "prompt": "#7fb4ff",
    "proven": "#7ad48a",
    "holds": "#e6c06b",
    "falsified": "#ff7b72",
}


def capture(workdir: str) -> list[str]:
    """Intent:
        Run SESSION in a child interpreter whose working directory holds
        rates.py, and return what each statement printed.

    Raises:
        RuntimeError: the child interpreter failed.
    """
    import json
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env["XDG_CONFIG_HOME"] = os.path.join(workdir, ".config")
    env["MATHEMA_FAST_TIMEOUT"] = "60"
    env["MATHEMA_EXTENSIVE_TIMEOUT"] = "120"
    env["PYTHONPATH"] = workdir
    r = subprocess.run([sys.executable, "-c", _DRIVER, json.dumps(SESSION)],
                       cwd=workdir, env=env, capture_output=True, text=True,
                       timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"the session failed:\n{r.stderr}")
    return json.loads(r.stdout)


def transcript(outputs: list[str]) -> list[str]:
    """Intent:
        The terminal lines: the file listed, then each prompt followed by
        what it printed.
    """
    lines = ["$ cat rates.py", *SOURCE.splitlines(), "", "$ python -q"]
    for stmt, printed in zip(SESSION, outputs):
        lines.append(f">>> {stmt}")
        lines += printed.rstrip("\n").splitlines() if printed.strip() else []
    return lines


def reflow(lines: list[str], width: int = WIDTH) -> list[str]:
    """Intent:
        Break each line wider than `width` at spaces. A record row's
        continuation is aligned under its third column (where the row's
        detail text starts), and a row's counterexample starts a line of
        its own there; any other line continues four spaces in.
    """
    out = []
    for ln in lines:
        m = re.match(r"^(\s+\S+\s+\S+\s+)", ln)
        head, _, tail = ln.partition("   counterexample")
        if m and ln.startswith("    ") and tail and head.strip():
            col = " " * len(m.group(1))
            out.append(head.rstrip())
            rest = col + "counterexample" + tail
            while len(rest) > width and rest.rfind(": ", 0, width) > len(col):
                cut = rest.rfind(": ", 0, width) + 1
                out.append(rest[:cut])
                rest = col + rest[cut:].lstrip()
            out.append(rest)
            continue
        if len(ln) <= width:
            out.append(ln)
            continue
        indent = " " * len(m.group(1)) if m and ln.startswith("    ") else \
            " " * (len(ln) - len(ln.lstrip()) + 4)
        out += textwrap.wrap(ln, width=width, subsequent_indent=indent,
                             break_long_words=False, break_on_hyphens=False,
                             drop_whitespace=True)
    return out


_TOKEN = re.compile(r"\b(proven|holds|falsified)\b|(counterexample)")


def spans(line: str) -> str:
    """Intent:
        One transcript line as escaped SVG text with tspans colouring
        prompts, verdict words and the word counterexample.
    """
    for prefix in ("$ ", ">>> "):
        if line.startswith(prefix):
            return (f'<tspan fill="{COLOURS["prompt"]}">{html.escape(prefix)}</tspan>'
                    + html.escape(line[len(prefix):]))
    parts, pos = [], 0
    for m in _TOKEN.finditer(line):
        parts.append(html.escape(line[pos:m.start()]))
        word = m.group(0)
        colour = COLOURS.get(word, COLOURS["falsified"])
        weight = ' font-weight="bold"' if word == "counterexample" else ""
        parts.append(f'<tspan fill="{colour}"{weight}>{html.escape(word)}</tspan>')
        pos = m.end()
    parts.append(html.escape(line[pos:]))
    return "".join(parts)


def render(lines: list[str]) -> str:
    """Intent:
        The transcript drawn as a dark terminal window, as SVG text.
    """
    cols = max(len(ln) for ln in lines)
    w = round(2 * PAD_X + cols * CHAR_W)
    h = PAD_TOP + LINE_H * len(lines) + PAD_BOTTOM
    rows = []
    for i, ln in enumerate(lines):
        if not ln:
            continue
        y = PAD_TOP + LINE_H * i + FONT_SIZE
        # a fixed advance per character, so the window fits whichever
        # monospace font the viewer has
        rows.append(f'    <text x="{PAD_X}" y="{y}" xml:space="preserve" '
                    f'textLength="{len(ln) * CHAR_W:.1f}" lengthAdjust="spacingAndGlyphs">'
                    f"{spans(ln)}</text>")
    dots = "".join(
        f'<circle cx="{22 + 20 * k}" cy="18" r="6" fill="{c}"/>'
        for k, c in enumerate(("#ff5f57", "#febc2e", "#28c840")))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="mathema checking a discount factor: falsified at the pole '
        f'rate = 1 over the full range, proven over rates up to 0.99">\n'
        f'  <rect width="{w}" height="{h}" rx="10" fill="{COLOURS["bg"]}"/>\n'
        f'  <path d="M0 10 a10 10 0 0 1 10 -10 h{w - 20} a10 10 0 0 1 10 10 v26 '
        f'h-{w} z" fill="{COLOURS["bar"]}"/>\n'
        f"  {dots}\n"
        f'  <g font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, '
        f"'Liberation Mono', monospace\" font-size=\"{FONT_SIZE}\" "
        f'fill="{COLOURS["text"]}">\n'
        + "\n".join(rows)
        + "\n  </g>\n</svg>\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "assets" / "readme-hero.svg"))
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as workdir:
        pathlib.Path(workdir, "rates.py").write_text(SOURCE)
        lines = reflow(transcript(capture(workdir)))
    pathlib.Path(args.out).write_text(render(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {os.path.relpath(args.out, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
