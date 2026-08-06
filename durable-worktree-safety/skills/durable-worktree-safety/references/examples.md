# Scenario examples

## Fresh feature work

**Situation:** The main worktree is clean and the user authorizes branch and
remote mutations.

**Behavior:** Fetch the remote base, verify zero unintended ahead commits,
detect the existing persistent worktree convention, add a new worktree and
neutral feature branch from the remote base, push the branch early, implement
and verify coherent slices, push each slice, and open a draft pull request if
the work will span turns.

**Report:** Persistent path, base hash, branch, upstream, latest local and
remote hash, pull request URL, checks, and `durability: confirmed`.

## Existing dirty main worktree

**Situation:** The main worktree contains unrelated modified and untracked
files before new feature work begins.

**Behavior:** Record the paths, do not stage or stash them, leave that worktree
on its current branch, and create a separate persistent worktree from the
fetched remote base. Perform the feature work only in the clean worktree.

**Report:** Identify the preserved paths without exposing sensitive content.
State that they were neither staged nor moved.

## Polluted or diverged feature branch

**Situation:** The requested feature branch includes older commits from another
task and is also behind the current remote base.

**Behavior:** Refuse to use it as the pull request branch. Leave it intact.
Create a clean branch from the fetched current remote base in a persistent
worktree, cherry-pick only verified task commits, run checks, and compare the
new branch against the base before pushing.

**Report:** List selected commit hashes, clean divergence, intended file scope,
and the polluted branch left untouched.

## Deleted ephemeral worktree

**Situation:** A stale worktree record points to a missing path under an
ephemeral directory.

**Behavior:** Do not prune. Inspect the branch, remotes, reflogs, stashes,
worktree administrative metadata, preserved index, and unreachable objects.
Recover committed trees first. If the stale index names staged blobs, extract
copies into a separate persistent recovery directory.

**Report:** Separate recovered commits, staged blobs, and external backup
possibilities. State that unstaged or untracked files are unrecoverable by Git
when no other source recorded them.

## Push or network failure

**Situation:** A verified local slice is committed but the push or remote hash
check fails.

**Behavior:** Keep the local branch and persistent worktree intact. Retry only
when safe and within authorization. Do not claim a remote checkpoint or task
completion.

**Report:** Branch, local commit, failed operation, local-only content,
`durability: unconfirmed`, and the next safe retry.

## Secret detected before staging or commit

**Situation:** A changed `.env` file and a token appear in the intended paths.

**Behavior:** Stop before staging. Do not print the secret, commit it, push it,
or alter unrelated staged content. Identify the risky paths and ask whether to
exclude, sanitize, or replace them with documented placeholders.

**Report:** Name paths only, state that no remote mutation occurred, and mark
the checkpoint blocked pending a safe decision.

## User forbids remote mutation

**Situation:** The user permits local edits and commits but explicitly forbids
pushes and pull request changes.

**Behavior:** Use a persistent worktree, clean branch, verified slices, and
coherent local commits. Perform no remote mutation. Keep the last status and
local commit evidence.

**Report:** State `durability: blocked by remote-mutation restriction`, give the
local branch and commit, identify anything uncommitted, and do not claim
durable completion.

## Handoff with a complete documentation slice

**Situation:** Implementation is still in progress, but a reusable design
document is complete. Another agent will inspect or modify the same worktree.

**Behavior:** Treat the document as its own coherent slice. Review it for
sensitive content, commit it, push it when authorized, and confirm the remote
hash before the handoff. Give the next agent the durable commit and identify
all remaining local paths. Do not delay the documentation checkpoint until the
implementation or independent reviews finish.

**Report:** Document path, checkpoint commit, confirmed remote hash, remaining
local work, and any prohibited cleanup scope.

## Cleanup of a mixed tracked and untracked directory

**Situation:** A cleanup agent is asked to remove artifacts from a directory
that contains committed generated files and a valuable untracked document.

**Behavior:** Stop broad cleanup. Run `git ls-files -- <path>`, `git
check-ignore -v <path>`, and path-scoped status. Treat the directory as
protected because it contains tracked files. Return control to the primary
agent unless the assignment identifies exact removable files. The primary
agent checkpoints the valuable document before authorizing any exact cleanup.

**Report:** Tracked, ignored, and untracked classifications; durable commit for
valuable content; exact removable paths, if any; and the directory preserved.

## Persistent convention outside writable roots

**Situation:** The usual sibling worktree path is persistent but outside the task's configured writable roots.

**Behavior:** Treat the user's edit permission as clear but separate from sandbox capability. Use an existing ignored `.worktrees/` location inside the authorized repository root, or ask once to add the sibling path as a workspace root. Do not accept repeated per-file approvals or relocate a dirty worktree without exact authorization.

**Report:** Name the selected path, its covering writable root, and any authorized relocation.
