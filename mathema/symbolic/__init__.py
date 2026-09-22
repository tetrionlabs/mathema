# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Symbolic proof: the `derive` evidence route. Public re-export surface
for the package, import from here (`from mathema.symbolic import lift,
try_prove`), never from a private `mathema.symbolic._xxx` submodule
directly; those are implementation detail and may be reorganized without
notice.

The underscore-prefixed names here are deliberately exported: they are
the package-internal analysis surface `inventory`/`analysis`/`tiers`/
`_tier_text` consume (lift context walking, expression conversion,
loop-header classification, branch explanation), internal to mathema,
stable enough for its own sibling modules, not for third parties. The
per-shape lift record classes (`FoldLift` and friends) are not exported:
nothing outside this package constructs or annotates one.
"""
from __future__ import annotations

import sympy

from ._base import (
    NotSymbolic, _LiftCtx, _bind_params, _cond_to_sympy, _expr_to_sympy,
    strip_docstring, _unmodified_params, _walk_lift_body, lift, Lifted,
    DerivedClaim,
)
from ._loop_shapes import bare_seq_name, classify_loop_header, seq_one_colon
from ._proof_support import _humanize, ProofResult
from ._conditioned import (
    ConditionedLift, _affine_locals, _explain_branch, lift_conditioned,
)
from ._fold import diagnose_fold, lift_fold
from ._dot import lift_dot
from ._sum import lift_sum
from ._prove import try_prove, try_prove_raises
from ._matrix import (matrix_param_dims, mentions_matrix_ops,
                      try_prove_matrix)

__all__ = [
    "NotSymbolic", "_LiftCtx", "_affine_locals", "bare_seq_name",
    "_bind_params", "classify_loop_header", "_cond_to_sympy",
    "_explain_branch", "_expr_to_sympy", "_humanize", "seq_one_colon",
    "strip_docstring", "_unmodified_params", "_walk_lift_body",
    "diagnose_fold", "lift", "lift_conditioned", "lift_dot", "lift_fold",
    "lift_sum", "sympy", "try_prove", "try_prove_raises",
    "matrix_param_dims", "mentions_matrix_ops", "try_prove_matrix",
    "Lifted", "DerivedClaim", "ProofResult", "ConditionedLift",
]
