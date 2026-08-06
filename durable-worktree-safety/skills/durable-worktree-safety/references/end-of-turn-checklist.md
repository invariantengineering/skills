# Durability gate

Apply every item before handing an active worktree to another agent, allowing
cleanup, or ending a turn that created or changed repository content.

## Repository state

- [ ] Run `git status --short --branch`.
- [ ] Account for every modified, staged, deleted, and untracked path.
- [ ] Separate intended work from unrelated user changes.
- [ ] Leave unrelated user changes untouched and report them.

## Worktree capability

- [ ] Confirm the worktree is persistent and covered by a configured writable
      root.
- [ ] Separate file-edit authorization, sandbox capability, local Git mutation
      authorization, and remote mutation authorization.
- [ ] Leave no routine edit dependent on repeated per-file escalation.
- [ ] If the worktree moved, record exact authorization and verify branch,
      `HEAD`, index, status, and upstream before and after the move.

## Checkpoint

- [ ] Review the intended diff and staged diff.
- [ ] Inspect staged paths and content for secrets, private keys, credentials,
      dumps, generated output, and large unexplained binaries.
- [ ] Run the relevant checks.
- [ ] Commit each verified coherent slice.
- [ ] Commit complete reusable artifacts even when the surrounding
      implementation remains unfinished.
- [ ] If valuable work is incomplete, create a clearly named checkpoint only
      when remote work-in-progress is authorized and the content is safe.
- [ ] Leave no intended change uncommitted before claiming completion.

## Handoff and cleanup

- [ ] Before handoff, record the branch, worktree, latest durable commit,
      remaining local paths, permitted mutations, and prohibited cleanup scope.
- [ ] Before deleting a temporary or generated path, run `git ls-files --
      <path>`, `git check-ignore -v <path>`, and `git status --short
      --untracked-files=all -- <path>`.
- [ ] Treat every directory containing tracked files as protected from
      recursive deletion or recreation.
- [ ] Give cleanup agents exact removable paths; never delegate broad cleanup
      categories or directories.
- [ ] Permit only the primary agent to remove mixed tracked/untracked
      directories, after every path is classified and every valuable file is
      confirmed on the remote.
- [ ] If valuable local work cannot be checkpointed safely, prohibit cleanup
      until the primary agent resumes.

## Remote durability

- [ ] Push each verified slice when remote mutation is authorized.
- [ ] Compare `HEAD`, the upstream tracking ref, and the advertised remote
      branch hash.
- [ ] Record the latest commit hash and push destination.
- [ ] If pushing is forbidden or fails, mark durability `blocked` or
      `unconfirmed`; identify exactly what remains local.

## Pull request scope

- [ ] Fetch the intended remote base when network access permits.
- [ ] Recheck divergence, ahead commits, diff statistics, and changed paths.
- [ ] Confirm every pull request commit and file belongs to the task.
- [ ] Use a clean branch from the current remote base if history is polluted.

## Exit decision

Report `confirmed` only when intended changes are committed, required checks
have an acceptable result, the remote advertises the latest commit, pull
request scope is clean, and any handoff or cleanup scope is explicit. Report
unresolved sandbox limitations separately as `worktree capability:
approval-bound`; do not claim the worktree is ready for continued edits.
Otherwise report the blocking evidence and safest next action.
