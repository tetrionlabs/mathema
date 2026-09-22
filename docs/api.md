# API reference

Generated directly from docstrings, so it never drifts from what the
code actually does.

## `mathema`

::: mathema
    options:
      members:
        - check
        - note
        - analyze
        - track_claims
        - Record
        - resolve
        - resolve_function
        - gate
        - verify_project

## `mathema.reason_codes`

::: mathema.reason_codes
    options:
      members:
        - ReasonCode
        - Category
        - ClaimReasonCode
        - LoopReason
        - BranchReason
        - blocked_code
        - describe_code
        - claim_reason_code

## `mathema.conjecture`

::: mathema.conjecture
    options:
      members:
        - claim
        - check_conjectures
        - Conjecture

## `mathema.symbolic`

::: mathema.symbolic
    options:
      members:
        - lift
        - lift_conditioned
        - try_prove
        - try_prove_raises
        - Lifted
        - ProofResult

## `mathema.inventory`

::: mathema.inventory
    options:
      members:
        - is_pure_enough
        - purity_reason
        - claim_floor
        - derivability_report
        - structural_complexity
        - scope_dependencies
        - mutated_globals
        - typing_info
        - wrapped_target
        - docstring_quality
        - docs_checklist
        - is_test_covered
        - read_test_coverage
        - suggest_coverage_command

## `mathema.types`

::: mathema.types
    options:
      members:
        - Probability
        - Positive
        - Nonnegative
        - Shape

## `mathema.identity`

::: mathema.identity
    options:
      members:
        - form_hash

## `mathema.compiled`

::: mathema.compiled
    options:
      members:
        - CompiledForm
        - compile_form
        - numeric_check

## `mathema.forms`

::: mathema.forms
    options:
      members:
        - closed_forms
        - substituted_forms
        - executable_forms
        - Form
        - SubstitutedForm
        - Substitution
        - register_substitution

## `mathema.targets`

::: mathema.targets
    options:
      members:
        - resolve
        - resolve_function
        - Target
        - TargetError
