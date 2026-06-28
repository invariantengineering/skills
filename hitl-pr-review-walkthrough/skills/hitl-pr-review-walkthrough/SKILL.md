---
name: hitl-pr-review-walkthrough
description: >
  When a task has a human-in-the-loop (HITL) requirement to review a pull
  request, create a hands-on reviewer walkthrough that explains exactly how to
  test, evaluate, and merge it. Also use when the user asks for a PR review
  tutorial, review runbook, testing checklist, merge checklist, reviewer
  handoff, or instructions for future reviewers with no context.
---

# hitl-pr-review-walkthrough

Create a practical walkthrough that lets a human reviewer validate a pull
request without relying on memory, chat history, or unstated context.

## Principles

- Optimize for the reviewer who has no context or is returning weeks later.
- Write exact steps, expected outcomes, and merge criteria.
- Prefer repo-specific commands, routes, files, accounts, flags, fixtures, and
  environments over generic advice.
- Separate required checks from optional deeper checks.
- Call out unknowns, assumptions, and blockers instead of smoothing over them.
- Do not add self-attribution or automation-watermark text to the artifact.

## Workflow

1. Gather the review surface:
   - PR URL or branch name, base branch, linked issue or spec, and current CI
     status when available.
   - Changed files, diff summary, user-facing behavior, migrations, config,
     feature flags, dependencies, and external services touched.
   - Existing test commands or documented QA instructions from the repo.

2. Identify what the reviewer must prove:
   - The intended behavior works.
   - Important regressions still do not occur.
   - Data, security, privacy, permissions, accessibility, performance, and
     operational risks are covered when relevant.
   - Merge requirements are satisfied.

3. Produce a walkthrough with these sections:
   - `What changed`: Brief context, linked work, branch or PR, and the user
     outcome being reviewed.
   - `Before you start`: Required accounts, secrets, environment variables,
     feature flags, seed data, local services, migrations, and setup notes.
   - `Checkout and setup`: Exact commands and working directory assumptions.
   - `Automated checks`: Commands to run, expected pass criteria, and what a
     failure usually means.
   - `Manual review path`: Step-by-step actions with exact routes, inputs,
     fixtures, UI states, API calls, or CLI commands.
   - `Expected results`: Observable evidence the reviewer should see after
     each important step.
   - `Regression checks`: Focused checks for nearby behavior that could have
     been affected.
   - `Code review focus`: Specific files or concepts worth inspecting closely.
   - `Merge criteria`: Required approvals, CI status, stale branch handling,
     deployment or migration timing, and post-merge verification.
   - `Open questions or blockers`: Anything the reviewer must resolve before
     merging.

4. Make the walkthrough self-contained:
   - Include links, file paths, route names, command names, and exact test data
     whenever they are known.
   - Explain why each non-obvious check matters.
   - Mark inferred steps as assumptions.
   - Avoid vague instructions such as "test the flow" unless followed by the
     precise flow to test.

5. Choose the artifact location from the user request:
   - If the user asks for a PR description, write a PR-ready section.
   - If the user asks for a file, add or update the requested file.
   - If no destination is specified, return the walkthrough in the final
     response and mention any local files inspected.

## Skill or plugin PRs

When the pull request adds or changes a skill, include install checks for every
target agent surface the repository supports.

- **Codex CLI or GUI**: Install the raw skill folder by copying
  `<repo>/<plugin>/skills/<skill-name>/` to
  `${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>/`, then start a fresh
  Codex session and confirm the skill appears and triggers from its
  frontmatter description.
- **Claude Code CLI**: Add the marketplace with
  `/plugin marketplace add <repo-or-absolute-path>`, then install with
  `/plugin install <skill-name>@skills`. Start a fresh session before testing
  trigger behavior.
- **Claude GUI**: Use the plugin or marketplace UI to add the same marketplace
  source, install the named plugin, then start a fresh chat or coding session
  and confirm the skill is available.
- If a surface cannot be tested locally, state that clearly and give the exact
  command or UI path the reviewer should run.

## Output template

````markdown
## Review Walkthrough

### What changed

- PR/branch:
- Base:
- Related work:
- Reviewer goal:

### Before you start

- Required access:
- Required environment:
- Feature flags or config:
- Data or fixtures:

### Checkout and setup

```sh
<one command per line>
```

### Automated checks

```sh
<one command per line>
```

Expected: <what passing looks like>

### Manual review path

1. <specific action>
   Expected: <observable result>

2. <specific action>
   Expected: <observable result>

### Regression checks

- <nearby behavior to verify>

### Code review focus

- `<path>`: <why this file matters>

### Merge criteria

- <required CI/approval/test evidence>
- <branch freshness or deployment requirement>
- <post-merge check>

### Open questions or blockers

- <question or blocker, or "None known">
````
