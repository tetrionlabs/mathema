# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Interface surfaces over the mathema library boundary.

Two kinds live here. A protocol subpackage (`mcp`) is self-contained
and imported only on demand, because its own dependency is an optional
extra and never a core requirement; the core library carries no
interface weight. `extension` is the other kind: the contracted
surface a registered capability provider imports, with no dependency
of its own, versioned by `EXTENSION_API_VERSION` rather than by the
package.

Nothing here is imported by this package on your behalf. Import the
one you want.
"""
