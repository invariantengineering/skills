---
name: timebox-routine-ops
description: Use only for a known, tiny local administrative operation expected to need at most one quick inspection and one direct mutation, such as removing one confirmed artifact or checking one routine status. Do not use for audits, investigations, debugging, implementation, multi-file work, or complex Git and worktree recovery.
---

# Timebox Routine Operations

Finish the smallest safely scoped operation quickly. Prefer a precise manual handoff over prolonged autonomous struggle.

## Scope gate

Continue only when the exact target and operation are already known and the
task should fit within one inspection and one mutation. If the work requires
discovery, diagnosis, implementation, several files, repeated attempts, or
complex Git or worktree recovery, stop using this skill and follow the
task-specific workflow instead.

## Execution limits

- Start a hard 30-second budget with the first tool call.
- Perform at most one quick read-only inspection and one direct mutation attempt.
- Keep commentary to one short update unless the operation completes.
- Do not retry, loop on approvals, diagnose extensively, or add ceremonial validation.
- Do not spend longer fixing the environment than the underlying operation should take.
- Do not load multiple heavyweight workflow skills unless safety genuinely requires them.

## Operate safely

1. Resolve the exact target with the single inspection.
2. Stop and ask one concise question if the target is ambiguous or potentially destructive.
3. Attempt one mutation against only the resolved target.
4. Preserve unrelated branches, worktrees, metadata, files, directories, and user changes.
5. Never broaden a deletion or cleanup operation.
6. If part of the operation already succeeded, continue only from the remaining state; never restart the workflow.

## Stop conditions

If the mutation fails because of sandboxing, permissions, an approval requirement, or an environmental limitation, stop immediately. Do not retry or issue another approval request. If an approval is not resolved promptly, stop waiting.

State what succeeded, identify the exact remainder, and provide only the minimum commands needed to finish manually. Use this exact structure:

Completed: <what succeeded>.
Remaining: <what is blocked>.

Run:
```sh
<minimal exact commands>
```

For partial worktree cleanup, provide only the remaining metadata and local-branch cleanup commands. If `git branch -d` is blocked by a stale worktree record, hand off the exact scoped cleanup sequence without trying several more Git commands.
