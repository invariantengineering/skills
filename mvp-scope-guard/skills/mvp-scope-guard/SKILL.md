---
name: mvp-scope-guard
description: Use before proposing plans, dependencies, frameworks, or multi-ticket implementations to prevent architecture slop, redundant work, and scope beyond the user's stated outcome.
---

# MVP Scope Guard

Keep proposed work limited to the smallest verifiable deliverable that achieves
the user's stated outcome.

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
9. Provide the smallest verifiable deliverable first.
10. Show time and token estimates for the MVP only.

## Stop and Simplify

Reduce the proposal again when:

- It introduces more than one new abstraction.
- Preparation costs more than execution.
- Existing work is being regenerated.
- The proposed scope exceeds the user's stated objective.
- A foundation cannot be tied to an immediate failure mode.
