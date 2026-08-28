# Repository Agent Guidelines

Use these rules as routing guidance. Load more detailed instructions only when
the current request needs them.

## Execution boundaries

- Answering questions, reviewing, diagnosing, reporting status, and discussing
  options are read-only unless the user also asks for a change.
- Requests to change, build, fix, or update authorize the smallest in-scope
  local edits and validation needed to complete the request.
- Confirm before destructive actions, external writes, material cost, or a
  meaningful expansion of scope unless the user has already authorized that
  exact action.
- Treat an execution-ready implementation plan as planning, not permission to
  implement it.

## Skill loading

- Do not preload skills at the start of a task. Select a skill only when the
  current request matches its frontmatter description.
- After selecting a skill, read its root `SKILL.md` first. Open supporting
  references only when that file routes the current task to them.
- Read-only analysis or status work does not by itself activate implementation,
  Git durability, estimation, publishing, or pull-request handoff workflows.
- Explicit user instructions and explicitly named skills take precedence over
  automatic routing.
- If a selected skill's scope gate excludes the current task, stop loading that
  skill and continue with the instructions that actually apply.

## Shell operations

- Apply shell guidance only when commands will actually run.
- Run one command per shell call. Do not combine commands with pipes, chaining,
  command substitution, subshells, or multi-line shell scripts.
- Separate inspection from mutation, use the tool's working-directory control,
  and keep each command small enough to approve independently.

## Repository workflow

- Do not mutate Git state during read-only work.
- Before the first repository-content edit, inspect the current branch and
  worktree status. This lightweight gate is mandatory even when no Git skill is
  otherwise selected.
- Never edit repository content on a default or protected branch. If the
  current task has not explicitly verified a clean, intended feature worktree,
  load `durable-worktree-safety` and establish one from the fetched default
  branch before editing.
- After the current task verifies a clean, intended feature worktree, ordinary
  edits can proceed without loading the remaining durability workflow.
- Preserve unrelated user changes. Inspect and stage only files that belong to
  the requested change.
- Validate the smallest relevant surface before handoff.
- Open pull requests only when requested or already authorized, target the
  default branch, and do not merge or deploy unless the user explicitly asks.

## Safety and artifacts

- Resolve exact targets before deleting, overwriting, moving, or cleaning
  files, branches, or worktrees. Stop when ownership or scope is ambiguous.
- Keep temporary work in an established, ignored repository-local scratch or
  planning directory. Confirm it does not appear in Git status.
- Keep committed and published writing neutral and public-safe. Exclude
  credentials, personal data, private project details, machine-specific paths,
  and authorship or generation footers unless the user requires them.

## Completion gate

After changing repository content or Git state:

1. Review the changed paths and diff for scope, sensitive data, and unrelated
   work.
2. Run the relevant checks and report any that were skipped or failed.
3. Confirm the final repository status.
4. If commit, push, or pull-request work was requested, verify the resulting
   branch and remote state before declaring completion.
