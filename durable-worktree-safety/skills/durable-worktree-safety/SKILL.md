---
name: durable-worktree-safety
description: >
  Use for Git or worktree mutations where branch integrity or durable recovery
  matters: creating or moving worktrees, dirty or polluted branches, commits,
  pushes, pull-request preparation, handoffs, destructive cleanup, or recovery.
  Do not use for read-only repository inspection, code review, explanation,
  status reporting, or ordinary edits in an already-safe worktree.
---

# Durable Worktree Safety

Make active work survive worktree loss and keep pull requests limited to the
intended change.

## Scope gate

Continue only when the task will mutate Git or worktree state, may strand
valuable local work, or requires a durable handoff or recovery decision. For a
read-only check or ordinary editing inside an established clean feature
worktree, use the repository's normal workflow without loading the remaining
recovery and durability procedures.

## Non-negotiable invariants

- Treat every worktree as disposable.
- Treat the remote feature branch as the durable backup.
- Never keep the only copy of active work in `/tmp`, `/private/tmp`, a system
  cache, a transient sandbox, or another cleanup-prone directory.
- Require the selected worktree path to be covered by the task's configured
  writable roots so ordinary edits do not require repeated escalation.
- Treat user authorization, filesystem sandbox capability, and Git or remote
  mutation authorization as separate facts.
- Prefer the repository's existing persistent worktree convention. Do not
  invent a competing layout when one is documented or already in use.
- Start feature work from the fetched remote base, not from a possibly stale
  local base branch.
- Preserve unrelated user changes. Never stage, stash, move, overwrite, clean,
  reset, or discard them merely to make the task easier.
- Refuse to build a pull request from unrelated branch history.
- After repository content or Git state changes, apply the durability gate
  before agent handoff, cleanup, or exit.
- Never claim completion while intended work remains only local and
  uncommitted.
- Never force-push, reset, clean, prune, delete branches or worktrees, rewrite
  history, or discard work without explicit authorization.
- Never relocate an active or dirty worktree without explicit authorization for
  the exact source and destination.

## 1. Establish scope and authority

Determine before mutation:

- intended repository and task;
- intended base branch and remote;
- configured workspace and writable roots, when the environment exposes them;
- whether the intended worktree path is persistent and writable without
  per-edit escalation;
- whether the user authorized file edits in that path;
- whether local branch, commit, and worktree creation are authorized;
- whether remote branch pushes and pull request mutations are authorized;
- whether the user permits a remote work-in-progress checkpoint;
- expected checks and protected-branch rules.

Treat an explicit request to push or open a pull request as remote
authorization for that scope. Otherwise ask before the first remote mutation.
Permission to edit files does not change the application's filesystem sandbox
and does not by itself authorize commits, pushes, or pull request changes.
Explain any mismatch once and offer a path-level remedy; do not repeatedly ask
the user to restate permission they already granted.

Fetching reads the remote but updates local remote-tracking refs; perform it
when network access is allowed. If it cannot be performed, mark the base
unverified and do not present branch cleanliness as proven.

## 2. Run the pre-edit inspection

Run small, separate inspection commands. Adapt placeholders to the repository.

```text
git rev-parse --show-toplevel
git branch --show-current
git remote -v
git worktree list --porcelain
git status --short --branch
git rev-parse --abbrev-ref --symbolic-full-name @{upstream}
```

Discover the intended base from the user's request, repository documentation,
remote default, or existing pull request metadata. Do not guess when different
bases would materially change the result.

Fetch the exact remote base:

```text
git fetch <remote> <base>
```

Then inspect ancestry, divergence, commits, and file scope:

```text
git merge-base --is-ancestor <remote>/<base> HEAD
git rev-list --left-right --count <remote>/<base>...HEAD
git log --oneline --decorate <remote>/<base>..HEAD
git diff --stat <remote>/<base>...HEAD
git diff --name-status <remote>/<base>...HEAD
```

Interpret the evidence:

- Commits ahead of the base must all belong to the requested change.
- Files in the three-dot diff must all belong to the requested change.
- Being behind a newly advanced base is not itself pollution, but it must be
  reported and handled without unauthorized history rewriting.
- Historical, reverted, merged-from-elsewhere, or differently scoped commits
  are unrelated even if the final file diff looks plausible.
- Ambiguous ownership is a safety stop.

Do not add new work to a branch with unrelated ahead history.

## 3. Select a persistent worktree

Inspect repository documentation, existing worktree paths, sibling directories,
ignored worktree directories, team conventions, and the task's configured
writable roots. Resolve candidate paths before creation. A candidate is valid
only when it is both persistent and writable for routine task operations.

Prefer, in order:

1. the documented repository convention when a writable root covers it;
2. the convention visible in existing persistent worktrees when writable;
3. an existing ignored in-repository worktree directory such as `.worktrees/`
   inside an authorized repository root;
4. a stable sibling directory only when the task grants writable access to it;
5. another persistent location agreed with the user when placement is unclear.

Reject an ephemeral target for active work. A temporary directory may be used
only for disposable experiments whose valuable output is already committed and
pushed elsewhere.

Reject a target that would require repeated sandbox escalation for normal file
edits. If the preferred convention lies outside writable roots, either ask once
to add or open that path as a workspace root, or select an established
persistent location inside an existing writable root. State that the user's
permission is understood and that the remaining constraint is sandbox
capability.

If the current worktree is dirty:

- record the changed and untracked paths;
- leave unrelated changes in place;
- avoid switching branches when changes could follow the switch;
- create a separate clean worktree from the remote base for new work;
- stop before transferring existing changes if their ownership or overlap is
  unclear.

### Relocate an active worktree only as a controlled migration

Do not move a worktree merely to silence repeated approval prompts. First ask
for authorization naming the exact source and target. Before an authorized
move:

1. record `git worktree list --porcelain`, branch, `HEAD`, upstream, status,
   staged paths, and unstaged paths;
2. create and push a safe checkpoint when authorized;
3. confirm the destination is persistent, empty, and covered by a writable
   root;
4. use `git worktree move <source> <destination>` rather than a raw filesystem
   move;
5. re-run the recorded inspections and verify that branch, `HEAD`, index,
   staged state, unstaged state, and upstream are unchanged.

If no safe checkpoint can be created, preserve the current worktree and ask the
user to add its existing path as a writable root or explicitly accept the
remaining approval boundary.

## 4. Create a clean durable branch

Use the repository's branch naming convention. Otherwise choose a neutral,
task-specific name with no personal, provider, or automation markers.

Create the feature branch directly from the fetched remote base, preferably
while adding the persistent worktree:

```text
git worktree add -b <feature-branch> <persistent-path> <remote>/<base>
```

Re-run status and divergence checks inside the new worktree. Expect no local
changes and no unrelated ahead commits.

When remote mutation is authorized, establish the upstream early:

```text
git push -u <remote> <feature-branch>
```

For multi-turn, long-running, risky, or handoff-prone work, open a draft pull
request after the first meaningful pushed commit when pull request mutation is
authorized. Do not open one solely to satisfy ceremony for a trivial
single-turn change.

## 5. Work in verified slices

For every coherent slice:

1. inspect the working diff and changed paths;
2. run the smallest relevant checks;
3. stage only intended paths;
4. inspect the staged diff and security risks;
5. commit the coherent slice;
6. push it immediately when authorized;
7. confirm the upstream contains the commit.

Use specific path staging. Never use broad staging until every changed path has
been reviewed and belongs to the slice.

Before committing, inspect at least:

```text
git status --short
git diff --cached --stat
git diff --cached --name-status
git diff --cached
git diff --cached --check
git diff --cached --numstat
```

Stop on:

- `.env` files or local configuration not clearly intended for version control;
- credentials, tokens, passwords, private key material, signing material, or
  suspicious high-entropy values;
- database dumps, production exports, logs, caches, dependency trees, build
  output, or generated artifacts not required by project convention;
- large unexplained binaries;
- unrelated files or pre-existing staged changes;
- failed required checks.

Do not alter pre-existing staged content without authorization. Never push
secrets. Push failing or unrelated work only after the user explicitly
authorizes that exact risk and the work is isolated from reviewable changes.

If incomplete work is materially valuable and remote work-in-progress is
authorized, make a clearly named checkpoint commit such as
`chore(checkpoint): preserve <slice>` after inspecting it. State failed or
unrun checks in the draft pull request or handoff. Do not disguise a checkpoint
as completed work.

Do not delay a checkpoint merely because a broader implementation is not
finished. A complete, reusable document, design artifact, migration, test
fixture, or other coherent slice must be committed and pushed before another
agent receives access to the worktree when remote checkpoint authority exists.

## 6. Enforce the multi-agent handoff and cleanup gate

Before another agent works in or cleans an active worktree:

1. run `git status --short --branch` and classify every modified, staged,
   deleted, and untracked path;
2. checkpoint and push every coherent, valuable slice when remote checkpoint
   authority exists;
3. if valuable work is incomplete, create and push an explicit checkpoint
   commit when safe, or prohibit cleanup until the primary agent resumes;
4. give the receiving agent the branch, worktree, latest durable commit,
   remaining local paths, permitted mutations, and prohibited cleanup scope.

Before deleting any path described as temporary, generated, cached, or an
artifact, run:

```text
git ls-files -- <path>
git check-ignore -v <path>
git status --short --untracked-files=all -- <path>
```

Treat `git check-ignore` exit status 1 as “not ignored,” not as permission to
delete. A directory name, ignore rule, generated-file convention, or cleanup
assignment does not prove that all of its contents are disposable.

- Treat a directory containing any tracked file as protected. Never
  recursively delete or recreate it as cleanup.
- Do not let a subagent perform cleanup unless the assignment names the exact
  paths it may remove. General instructions such as “remove artifacts” or
  “clean temporary files” do not authorize directory deletion.
- Only the primary agent may remove a directory containing mixed tracked and
  untracked content, and only after classifying every path and confirming that
  the remote contains every valuable file.
- If remote checkpoint authority is absent or a safe checkpoint cannot be
  created, preserve the worktree and prohibit cleanup. Report which valuable
  paths remain local.

The primary agent remains responsible for the gate even when another agent
created the files or performs the cleanup. Delegation does not transfer
durability responsibility.

## 7. Keep pull request history clean

Immediately before opening or updating a pull request, repeat the fetched-base
comparison:

```text
git rev-list --left-right --count <remote>/<base>...HEAD
git log --oneline <remote>/<base>..HEAD
git diff --stat <remote>/<base>...HEAD
git diff --name-status <remote>/<base>...HEAD
```

Verify that every ahead commit and every changed file is intended. If the
working branch is polluted:

1. leave it intact;
2. create a new persistent worktree and clean branch from the current fetched
   remote base;
3. identify intended commits by hash;
4. cherry-pick only those commits in chronological order;
5. resolve conflicts without importing unrelated changes;
6. run checks and repeat the branch comparison;
7. push the clean branch when authorized;
8. open or retarget the pull request only when its scope is proven.

Do not repair pollution with force-push, reset, rebase, branch deletion, or
worktree deletion unless the user explicitly requests that exact mutation.

## 8. Enforce the pre-exit gate after changes

Read and apply
[references/end-of-turn-checklist.md](references/end-of-turn-checklist.md)
after repository content or Git state changes and before an agent handoff,
cleanup operation, or turn or session end. A read-only assessment does not
require the mutation-specific durability checklist.

When repository content or Git state changed, run:

```text
git status --short --branch
```

If intended changes remain uncommitted, do not report the task complete.
Either commit and push them after verification, or report why no safe durable
checkpoint could be created and identify what remains local.

After a push, confirm the remote branch advertises the latest local commit:

```text
git rev-parse HEAD
git rev-parse @{upstream}
git ls-remote --exit-code --heads <remote> <feature-branch>
```

Compare the hashes. A successful push message alone is not the final check.
If network confirmation fails, report durability as unconfirmed.

If the user forbids remote mutation, respect that boundary. Prefer a coherent
local commit if authorized, but report that the remote durability gate remains
unsatisfied. Do not claim durable completion.

## Recovery from a missing worktree

Freeze destructive cleanup. Do not prune the worktree record, delete metadata,
run aggressive garbage collection, reset the branch, or recreate paths over
possible evidence. Pruning may delete the stale worktree index and
administrative reflog; resetting may move the only ref that keeps a commit
reachable.

Inspect:

```text
git rev-parse --path-format=absolute --git-common-dir
git worktree list --porcelain
git worktree prune --dry-run --verbose
git reflog --all
git stash list
git fsck --no-reflogs --unreachable
```

Locate the stale worktree entry under the common Git directory's `worktrees`
administrative area. Preserve that entry, especially its `index`, `HEAD`, and
reflog, in a persistent recovery directory before authorized cleanup. Inspect a
preserved index without replacing a live index:

```text
GIT_INDEX_FILE=<preserved-index> git ls-files --stage
GIT_INDEX_FILE=<preserved-index> git diff --cached --stat <stale-head>
GIT_INDEX_FILE=<preserved-index> git diff --cached --name-status <stale-head>
```

Review recovered staged content for secrets and unrelated files before creating
any recovery commit or remote checkpoint. Extract candidates into a separate
recovery directory; never overwrite a live worktree.

Classify recovery sources honestly:

- **Remote branches and tags:** recover advertised commits and their recorded
  trees.
- **Local branches, commits, and reflogs:** recover committed snapshots while
  their objects remain.
- **Stashes:** recover content actually included in the stash; untracked files
  are present only if the stash was created with the relevant option.
- **Stale worktree index:** may retain blob object IDs for staged content in the
  worktree administrative metadata. Preserve the index and object database,
  inspect entries, and extract blobs into a separate recovery directory. Do not
  overwrite a live worktree.
- **Unreachable objects:** may expose committed or staged blobs, but names and
  relationships may be incomplete. Copy candidates before cleanup.
- **Filesystem snapshots, editor history, backups, and undelete tools:** may
  recover content Git never recorded; treat these as external recovery sources.

State the hard limit: unstaged modifications and untracked files are not stored
by Git merely because a worktree record exists. If no stash, staged blob,
commit, backup, editor history, or filesystem copy recorded them, Git cannot
restore them. Never promise otherwise.

## Safety stops

Stop and request direction when:

- the repository, base, remote, branch target, or worktree path is ambiguous;
- the worktree target may be ephemeral;
- the worktree target is outside configured writable roots;
- the proposed remedy would relocate an active or dirty worktree without exact
  source-and-destination authorization;
- dirty or staged changes cannot be attributed safely;
- a cleanup target has not been classified down to its tracked and untracked
  contents;
- a subagent cleanup request names a category or directory instead of exact
  removable paths;
- valuable local work lacks a safe durable checkpoint before handoff;
- branch history contains unrelated or uncertain commits;
- a mutation would overwrite, discard, rewrite, prune, or delete;
- a secret or sensitive artifact may be included;
- checks fail and remote work-in-progress authorization is absent;
- remote mutation or checkpoint authority is unclear;
- push, authentication, network, or remote confirmation fails.

Continue with read-only diagnosis while waiting when it cannot harm evidence.

## Output contract

Give concise progress updates during work. In the final handoff report:

- repository and persistent worktree path;
- writable root covering the worktree;
- worktree capability: `ready` or `approval-bound`, with any remaining sandbox
  limitation;
- intended base and fetched base commit;
- feature branch and upstream;
- latest local commit and confirmed remote commit;
- pull request URL and draft state, if any;
- checks run and results;
- divergence and intended commit/file summary;
- unrelated user changes preserved;
- anything intentionally left local;
- durability state: `confirmed`, `blocked`, or `unconfirmed`;
- recovery limits or required user decision, when relevant.

Never substitute optimistic language for missing evidence.

Read [references/examples.md](references/examples.md) when choosing behavior for
a dirty, polluted, missing, offline, sensitive, or local-only scenario.
