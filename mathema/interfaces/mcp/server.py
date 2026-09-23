# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The MCP server wiring: `tools.py`'s plain functions registered on a
FastMCP app. This module is the only place the optional `mcp` package
is imported; everything callable lives SDK-free in `tools.py`."""
from __future__ import annotations

from . import resources as _resources
from . import tools as _tools


def _plugin_tools() -> list:
    """Intent:
        The plugin hook: a mathema plugin can contribute MCP tools by
        exposing an `mcp_tools()` callable returning plain functions.
        Fail-soft by design, a plugin that errors contributes
        nothing, it never breaks the server. Core registers no plugins
        itself; this is the seam.
    """
    contributed: list = []
    try:
        from importlib.metadata import entry_points
        for ep in entry_points(group="mathema.mcp_tools"):
            try:
                hook = ep.load()
                contributed.extend(hook() or [])
            except Exception:
                continue
    except Exception:
        pass
    return contributed



def _compact(fn):
    """Intent:
        The same tool, returning its payload as compact JSON text
        rather than a dict.

    Notes:
        The SDK serializes a returned dict with `indent=2` hardcoded,
        with no opt-out, which roughly doubles the row-oriented
        payloads that were hand-compacted (`prefix`/`cols`/`rows`)
        precisely to avoid repeating key names. A returned `str` is
        passed through verbatim, so this recovers it.

        This wraps at the SERVER boundary on purpose: the tool
        functions keep returning dicts, so they stay directly callable
        and testable, and the cross-surface test that compares a
        tool's return value against the CLI's own JSON keeps working.

        Registration must pass `structured_output=False`. A bare
        `-> str` annotation would make the SDK ADD a
        `{"result": "<json>"}` structured block duplicating the whole
        payload, worse than the pretty-printing it replaces. Nothing
        is lost by switching it off: every tool is annotated bare
        `-> dict`, which already yields no output schema at all.
    """
    import functools
    import json

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return json.dumps(fn(*args, **kwargs), separators=(",", ":"),
                          default=str)
    wrapper.__annotations__ = dict(getattr(fn, "__annotations__", {}))
    wrapper.__annotations__["return"] = str
    return wrapper

def build_server():
    """Construct the FastMCP server with every built-in tool (and any
    plugin-contributed ones) registered.

    Raises:
        ImportError: the `mcp` package is not installed, the caller
            (cmd_mcp) turns this into the install hint.
    """
    try:
        # mcp 2.x
        from mcp.server.mcpserver import MCPServer as _Server
    except ImportError:
        # mcp 1.x, where the same class is FastMCP; if this import
        # fails too, the package is genuinely absent and the
        # ImportError carries the install hint upward
        from mcp.server.fastmcp import FastMCP as _Server

    server = _Server(
        "mathema",
        instructions="Claim-Driven Development: turn software intent into "
                     "verifiable evidence. You state a claim, mathema "
                     "adjudicates it against the real function, the "
                     "record keeps the evidence. No tool accepts a "
                     "verdict from you; acceptance is a human act done "
                     "in the CLI, and so are unlocking a locked "
                     "function and entering a PIN. You may lock; only "
                     "a person unlocks.")
    def _register(fn):
        try:
            server.tool(structured_output=False)(_compact(fn))
        except TypeError:
            # an SDK without the flag: fall back to the plain dict
            # return rather than emitting a duplicated payload
            server.tool()(fn)

    for fn in _tools.TOOLS:
        _register(fn)
    for fn in _plugin_tools():
        try:
            _register(fn)
        except Exception:
            continue

    # reference material an agent can read when it does not already
    # know what to ask, and procedures put in front of it at the
    # moment it chooses what to do
    for uri, (builder, mime) in _resources.RESOURCES.items():
        try:
            server.resource(uri, mime_type=mime)(builder)
        except Exception:
            continue
    for name, builder in _resources.PROMPTS.items():
        try:
            server.prompt(name=name)(builder)
        except Exception:
            continue
    return server


def serve() -> None:
    """Run the server on stdio (the transport `mathema mcp serve`
    speaks)."""
    build_server().run()
