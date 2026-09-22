# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The MCP interface: mathema's library surface served as MCP tools.

Requires the optional extra:

    pip install mathema[mcp]

`tools.py` holds the plain functions (no MCP dependency; they are
testable and usable directly); `server.py` wires them onto a FastMCP
server and needs the `mcp` package installed. Serve with:

    mathema mcp serve

The surface is deliberately bounded: no tool makes an LLM call, no
tool accepts a caller-supplied verdict, and acceptance (`mathema
accept`) is never exposed here; accepting evidence or owning risk is
a human act."""
