---
name: mvp-scope-guard
description: Use when the user authorizes implementing a code, configuration, workflow, infrastructure, or documentation change, or requests an execution-ready implementation plan. Enforce the smallest coherent diff that achieves the explicit request. Do not use for brainstorming, exploration, critique, research, review, explanation, estimation, or discussion before implementation is authorized.
---

# MVP Scope Guard

Choose the smallest safe step that answers the immediate question or achieves
the requested outcome.

## Scope gate

Continue only after the user authorizes implementation or asks for an
execution-ready implementation plan. Do not apply this skill during
brainstorming, exploration, research, critique, review, explanation,
estimation, or other discussion before that boundary is crossed.

## Respect the Execution Boundary

- If the request is exploratory or implementation is not authorized, do not
  apply this skill and continue without announcing it.
- Apply the guard silently unless it removes proposed scope or requires user
  opt-in.
- Treat the user's rationale as context, not an additional requirement.
- Match the existing style and conventions instead of improving adjacent code,
  comments, formatting, or structure.
- Remove only code that the current change makes obsolete. Report pre-existing
  dead code rather than deleting it unless the user asks.
- Before editing, state the requested change and explicit non-goals.
- Do not implement optional improvements without explicit opt-in.
- Require confirmation before adding new abstractions, persistent state,
  subsystems, rollout behavior, rollback behavior, or operational guarantees
  unless they are indispensable to the requested outcome.
- Add only the narrowest regression test for the changed behavior.
- Update documentation only where the requested user-facing behavior changed.

## Match Validation to the Immediate Question

- Distinguish a usefulness test from production acceptance. Do not turn an
  authorized trial into production qualification, or substitute a trial for
  acceptance the user explicitly requested.
- Reuse proven simple methods. An existing script or prompt, representative
  real inputs, and human comparison may be enough for an initial usefulness
  test; do not automatically require a suite, metrics, new application modes,
  or redesigned evidence references.
- Separate experiment blockers from integration blockers. A limitation in the
  production command does not necessarily prevent a safe standalone trial.
  Preserve authorization, data-handling, and no-writeback boundaries.
- State what the result does and does not establish. Useful output from a
  small trial is not proof of production readiness.

## Scope the MVP

1. State the user's outcome in one sentence.
2. Inspect what already exists before estimating or proposing work.
3. For every proposed task, ask:
   - Is it required for the outcome?
   - What breaks if it is omitted?
   - Does it already exist?
4. Remove any task that has no concrete blocker.
5. Prefer one direct vertical slice over new infrastructure.
6. Backlog reusable frameworks, automation, dashboards, and speculative
   safeguards.
7. Do not import unrelated tickets merely because they share a dependency
   graph.
8. Separate the remaining work into:
   - Required now
   - Optional
   - Backlog
9. Provide the smallest safe step that answers the immediate question or
   achieves the requested outcome first.
10. Show time and token estimates for the MVP only.

## Stop and Simplify

Reduce the proposal again when:

- It introduces more than one new abstraction.
- Proving the idea safely would take less work than the proposed preparation;
  offer the smallest safe experiment first and state its limits.
- Existing work is being regenerated.
- The proposed scope exceeds the user's stated objective.
- A foundation cannot be tied to an immediate failure mode.
