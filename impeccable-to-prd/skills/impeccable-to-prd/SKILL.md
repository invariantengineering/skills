---
name: impeccable-to-prd
description: Turn the current conversation context into a PRD, persist the PRD as repository-local Markdown, and publish it to the configured project issue tracker. Use when the user wants to create or publish a PRD from the current context, especially when drafts must stay inside a writable repository root instead of an external or temporary directory.
---

# To PRD

Synthesize the current conversation and codebase understanding into a PRD. Do
not restart discovery by interviewing the user about facts already established.

The issue tracker and triage vocabulary should be provided by the repository's
skill configuration. Run the repository's skill setup workflow if they are
missing.

## Establish the artifact workspace

Before writing the PRD:

1. Resolve the current Git worktree and inspect registered worktrees, repository
   conventions, configured writable roots, and ignore rules.
2. Prefer `<repository-root>/.worktrees/planning/prds/` when `.worktrees/` is
   persistent, inside a configured writable root, and ignored by Git. When the
   current checkout is itself a linked worktree, use the repository-managed
   `.worktrees/` directory that contains it rather than creating a nested one.
3. Otherwise use an existing documented, repository-local, ignored planning
   directory that is writable without per-edit escalation.
4. If no safe location exists, ask once before adding an ignore rule or choosing
   another repository-local path. Do not use `/tmp`, `/private/tmp`, a home
   directory, or a path outside configured writable roots.
5. Confirm the selected directory is ignored before creating artifacts. Never
   stage or commit planning artifacts unless the user explicitly requests it.

Name the PRD `<topic-slug>.md`. Reuse it only when it clearly belongs to the
same PRD; never overwrite an ambiguous existing draft.

Write the complete PRD to this file before any remote publication. Use that
file as the source of truth for the issue body. Prefer a tracker's body-file
option over copying the body into an inline shell argument or external scratch
file.

## Process

1. Explore the repository when needed. Use its domain glossary vocabulary and
   respect relevant architectural decisions.
2. Sketch the major modules to build or modify. Look for deep modules with
   small, stable, independently testable interfaces.
3. Confirm the proposed modules and testing scope with the user.
4. Write the approved PRD to the artifact workspace using the template below.
5. Review the saved file for completeness, sensitive data, and unintended
   implementation detail.
6. Publish the saved PRD to the configured issue tracker and apply the
   AFK-ready triage label defined by the repository.
7. Retain the local Markdown as a handoff artifact. Report its absolute path,
   the published issue URL, and the applied label.

If publication is forbidden or fails, preserve the repository-local Markdown,
state that it is local-only, and do not claim that the PRD was published.

<prd-template>

## Problem Statement

Describe the problem from the user's perspective.

## Solution

Describe the solution from the user's perspective.

## User Stories

Provide an extensive numbered list covering every aspect of the feature:

1. As an <actor>, I want <feature>, so that <benefit>.

## Implementation Decisions

Record the modules and interfaces affected, technical clarifications,
architectural decisions, schema changes, API contracts, and interactions.

Do not include file paths or code snippets that will quickly become stale. A
prototype snippet may be included only when it captures a decision more
precisely than prose; trim it to the decision-rich portion and identify it as a
prototype result.

## Testing Decisions

Describe externally observable behavior to test, the modules covered, and
relevant testing precedent in the repository. Avoid tests coupled to
implementation details.

## Out of Scope

List what this PRD intentionally excludes.

## Further Notes

Record any remaining context that materially affects delivery.

</prd-template>
