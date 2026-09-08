---
name: hitl-pr-review-walkthrough
description: >
  Use when creating or updating a pull-request description or reviewer handoff,
  or when the user explicitly requests a pull-request runbook or merge
  checklist. Do not use for generic pull-request status checks, code-review
  findings, or implementation work before reviewer handoff.
---

# hitl-pr-review-walkthrough

Teach a human reviewer how to use the feature being changed and recognize
whether it works, without relying on memory, chat history, or unstated context.

## Scope gate

Continue only when the current deliverable is the reviewer-facing walkthrough
itself. If the task is checking pull-request status, reviewing code, reporting
findings, or still implementing the change, wait until the reviewer handoff is
being prepared.

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
   - `Try the feature`: A runnable tutorial following the requirements below,
     with explanations and observable results alongside each step.
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

## Feature tutorial requirements

Write `Try the feature` as a short lesson using the real feature entry point.
The reviewer must be able to follow it from setup to a useful result.

- For CLI and API features, provide copyable shell commands in fenced blocks.
  State the working directory, prerequisites, and how to create or obtain the
  sample inputs. Explain any values the reviewer must supply; never include
  real secrets or private data.
- Before each command, explain what it does and why this step matters. Explain
  the relevant flags and inputs, especially those introduced or changed by
  the PR. Keep commands in execution order and carry forward any generated
  identifiers or paths explicitly.
- After each step, show the expected output or state and how to observe it.
  Include an inspection command when the result is stored in a file, database,
  or other service. Label illustrative output so it is not mistaken for an
  actual execution result.
- Exercise the happy path and any failure or recovery behavior central to the
  change. For example, a resume feature needs a supported way to reach an
  interrupted state, resume it, and verify that the original run is reused.
- Verify command syntax, flags, and entry points against the implementation,
  CLI help, or maintained documentation. Do not invent commands to fill gaps.
  State what was actually run and what remains untested, with the reason.
  Call out side effects or external prerequisites that affect running a step.
- For UI-only features, give exact navigation, inputs, actions, and visible
  results. For changes without a new user entry point, demonstrate the
  affected existing workflow; explain when no runnable behavior applies.
- Keep file-reading tasks in `Code review focus` and test-suite commands in
  `Automated checks`. Neither substitutes for using the feature. Instructions
  such as "review these files" or "confirm the flag is passed through" do not
  satisfy the tutorial requirement.

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

### Try the feature

#### 1. <use the feature to accomplish a concrete task>

<Explain what this step does, why it matters, and the relevant flags or inputs.>

```sh
<verified command using the actual feature entry point>
```

Expected: <observable output or state, and how to inspect it>

#### 2. <continue the workflow or exercise a central failure/recovery case>

<Explain the next action and how to reuse any output, identifier, or path
from the previous step. Omit this step if no second action is needed.>

```sh
<verified command with concrete sample inputs>
```

Expected: <observable result that demonstrates the changed behavior>

Execution evidence: <steps actually run and results; unrun steps and reasons>

<For UI-only features, replace shell blocks with exact navigation and actions.
If no runnable behavior applies, explain why and give the relevant review steps.>

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
