---
name: impeccable-to-issues
description: Break a plan, spec, or PRD into independently grabbable vertical-slice issues, persist every issue as repository-local Markdown, and publish the approved set to the configured project issue tracker. Use when the user wants implementation issues or tickets drafted from existing material, especially when drafts must stay inside a writable repository root instead of an external or temporary directory.
---

# To Issues

Break source material into thin, complete tracer-bullet issues that can be
implemented and verified independently.

The issue tracker and triage vocabulary should be provided by the repository's
skill configuration. Run the repository's skill setup workflow if they are
missing.

## Establish the artifact workspace

Before drafting issues:

1. Resolve the current Git worktree and inspect registered worktrees, repository
   conventions, configured writable roots, and ignore rules.
2. Prefer `<repository-root>/.worktrees/planning/issues/<source-slug>/` when
   `.worktrees/` is persistent, inside a configured writable root, and ignored
   by Git. When the current checkout is itself a linked worktree, use the
   repository-managed `.worktrees/` directory that contains it rather than
   creating a nested one.
3. Otherwise use an existing documented, repository-local, ignored planning
   directory that is writable without per-edit escalation.
4. If no safe location exists, ask once before adding an ignore rule or choosing
   another repository-local path. Do not use `/tmp`, `/private/tmp`, a home
   directory, or a path outside configured writable roots.
5. Confirm the selected directory is ignored before creating artifacts. Never
   stage or commit planning artifacts unless the user explicitly requests it.

Write the approved breakdown to `00-index.md`. Write each issue body to
`<sequence>-<slice-slug>.md`, using two-digit dependency order. Never overwrite
an ambiguous existing draft.

Use these files as the source of truth for publication. Prefer a tracker's
body-file option over copying bodies into inline shell arguments or external
scratch files.

## Process

### 1. Gather context

Use the conversation context and supplied plan, spec, or PRD. If the user gives
an issue reference, read its full body and comments from the configured issue
tracker.

### 2. Explore the codebase when needed

Understand the current implementation before choosing slices. Use the
repository's domain vocabulary and respect relevant architectural decisions.

### 3. Draft vertical slices

Each issue must deliver a narrow but complete path through every relevant layer
and be demoable or verifiable on its own. Prefer many thin slices over a few
horizontal or oversized ones.

Classify each slice as HITL when it requires human interaction or judgment, and
AFK when it can be implemented and merged without human interaction. Prefer AFK
when the work is genuinely independent.

### 4. Confirm the breakdown

Present a numbered list containing each slice's title, HITL or AFK type,
dependencies, and covered user stories. Ask whether granularity, dependencies,
splits, merges, and classifications are correct. Iterate until approved.

### 5. Save the approved Markdown

Write `00-index.md` and every issue file before remote mutation. Review all
saved files for completeness, sensitive data, stale implementation detail, and
dependency consistency.

### 6. Publish in dependency order

Publish blockers first so later files can reference real issue identifiers.
Before publishing a dependent issue, update its saved `Blocked by` section with
the published identifiers. Apply the repository's AFK-ready triage label unless
directed otherwise. Keep each saved Markdown file identical to its published
issue body.

Do not close or modify a parent issue.

If publication is forbidden or fails, preserve every repository-local draft,
identify which issues were and were not published, and do not claim the issue
set is complete remotely.

<issue-template>

## Parent

Reference the parent issue when the source was an existing issue. Otherwise
omit this section.

## What to build

Describe the end-to-end behavior of this vertical slice, not a layer-by-layer
implementation plan.

Avoid file paths and code snippets that will quickly become stale. A prototype
snippet may be included only when it captures a decision more precisely than
prose; trim it to the decision-rich portion and identify it as a prototype
result.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Blocked by

- Reference each blocking issue.

Use `None - can start immediately` when there are no blockers.

</issue-template>
