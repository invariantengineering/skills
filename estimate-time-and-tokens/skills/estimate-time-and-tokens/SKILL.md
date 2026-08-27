---
name: estimate-time-and-tokens
description: Use when the user explicitly requests a time or token estimate, or when substantial future work needs a scoped approval decision supported by a forecast. Do not use for direct answers, reviews, status reports, completed work, small already-authorized edits, or casual next-step suggestions.
---

# Estimate Time and Tokens

Treat an estimate as an active control, not a one-time prediction. State the original promise, measure progress, revise elapsed-plus-remaining projections when evidence changes, and stop before silently exceeding the approved envelope.

## Scope gate

Continue only when an estimate is itself requested or a material approval
decision depends on forecasting substantial future work. A plan, comparison,
offer to help, or next-step suggestion does not activate this skill on its own.
Do not load the calibration workflow for work that is complete, read-only,
minor, or already authorized.

## Forecast the complete scope

Before proposing work:

1. Include discovery, implementation, validation, review, and handoff required for completion.
2. Describe the execution model: repeated work units, implementation agents, reviewers, automatic correction-pass cap, and material environment assumptions.
3. Use one implementer, one combined specification-and-quality reviewer, and one automatic correction pass unless the task requires otherwise. More agents, split reviewer roles, or another correction pass are workflow changes, not free capacity.
4. For repeated work, make the first unit a canary and checkpoint before extrapolating to the rest.
5. Estimate active wall-clock time in the current environment, including required tool and test latency. Exclude waits on the user, approvals, and external state.
6. Submit incremental tokens still required for the work. The script adds the latest root session `last_token_usage.total_tokens` when available to produce the projected final-context total. Never substitute cumulative session usage.
7. When multiple agent sessions will contribute, separately estimate aggregate tokens across those sessions. Mark aggregate usage unavailable when telemetry cannot support it; never imply that the root total includes subagents.
8. Inspect enough of the repository to name `expected_files` and less-certain `possible_files` without beginning implementation. Use repository-relative paths.
9. Estimate additions and deletions as separate rounded ranges. These are final Git diff counts, not gross churn or rework.
10. State the largest material uncertainty. Widen ranges when the repository, failure mode, environment, approval path, or validation cost is unclear.

If environment setup is optional, report its current-task net cost separately from its durable benefit on later tasks. Do not expand the current task solely because setup may pay off later.

## Record the initial forecast

Use `scripts/calibrate.py`. It writes append-only JSONL under `~/.codex/state/estimate-time-and-tokens/` by default. Record only bounded metadata, timestamps, repository-relative paths, Git counts, and token counters. Never record prompts, source contents, tool output, secrets, or absolute repository paths.

Keep `SKILL.md` static between releases. Per-task feedback belongs in the ledger.

```text
python3 <skill-directory>/scripts/calibrate.py forecast --task-class feature --time-low 45 --time-high 75 --tokens-low 30000 --tokens-high 55000 --aggregate-tokens-low 45000 --aggregate-tokens-high 80000 --work-units 6 --implementation-agents 1 --reviewers 1 --max-correction-passes 1 --environment-assumption "focused tests run in the existing container" --expected-file src/widget.py --possible-file tests/test_widget.py --add-low 80 --add-high 160 --delete-low 10 --delete-high 40
```

Use the calibrated output in the decision point and retain `run_id`. `tokens.incremental` is the submitted remaining-work range; `tokens.final_context` includes the root context already consumed; `aggregate_tokens` is a separate multi-agent measure.

If the ledger or session telemetry is unavailable, still give the estimate and identify which calibration or token metric is unavailable.

## Start from the implementation worktree

After approval, create or select the clean feature worktree where implementation will occur, then start before editing:

```text
python3 <skill-directory>/scripts/calibrate.py start <run_id> --repo .
```

Never start from a primary checkout when implementation will occur in a linked worktree. `start` refuses protected branches and dirty repositories. Use `--allow-protected-branch` or `--allow-dirty` only for intentional time/token-only tracking where Git scope will not be calibrated.

Pause only before waiting on the user, an approval, or external state. Do not pause for required builds, tests, or tool latency.

```text
python3 <skill-directory>/scripts/calibrate.py pause <run_id>
python3 <skill-directory>/scripts/calibrate.py resume <run_id>
```

While actively working, keep the user informed at least every 60 seconds. Long tool latency is not a reason to leave the user without an update.

## Check progress and control scope

Run a checkpoint after the first repeated unit and whenever any of these occurs:

- scope or workflow changes;
- an environment assumption fails;
- the canary does not extrapolate;
- elapsed time or token burn no longer matches completion;
- a correction pass exceeds the forecast cap;
- the projected total may exceed the approved upper bound.

```text
python3 <skill-directory>/scripts/calibrate.py checkpoint <run_id> --completed-units 1 --correction-passes 0 --implementation-agents 1 --reviewers 1 --aggregate-tokens 18000 --reason "first page complete"
```

The command records active elapsed time, root token usage when available, aggregate usage when supplied, current burn projection, triggers, and a `control_action`. A first-unit canary returns `reforecast-required`. Exceeding the correction-pass cap returns `approval-required`.

Reviewer findings do not authorize implementation. Classify each material finding before acting:

```text
python3 <skill-directory>/scripts/calibrate.py classify <run_id> --classification required-now --summary "breaks the accepted migration contract"
python3 <skill-directory>/scripts/calibrate.py classify <run_id> --classification backlog --summary "concurrency hardening outside migration scope"
python3 <skill-directory>/scripts/calibrate.py classify <run_id> --classification out-of-scope --summary "unrelated cleanup"
```

- `required-now`: reforecast before implementation.
- `backlog`: retain the finding without changing this task.
- `out-of-scope`: reject it for this task.

Allow one automatic correction pass by default. A second pass requires a user update and revised estimate.

## Reforecast elapsed plus remaining

At every required checkpoint, estimate remaining work from current evidence. Record actual consumed plus revised remaining, not a replacement estimate detached from elapsed work.

```text
python3 <skill-directory>/scripts/calibrate.py reforecast <run_id> --remaining-time-low 25 --remaining-time-high 45 --root-tokens 92000 --remaining-tokens-low 18000 --remaining-tokens-high 32000 --aggregate-tokens 118000 --remaining-aggregate-tokens-low 26000 --remaining-aggregate-tokens-high 48000 --deviation workflow-expansion --reason "review split into two roles"
```

Use one deviation class:

- `estimator-error` or `canary-variance`: the work stayed in scope but the prediction was wrong;
- `agent-scope-creep`: implementation expanded without authorization;
- `workflow-expansion`: agents, reviewers, passes, or process expanded;
- `environment-surprise`: a material runtime assumption failed;
- `user-scope-change`: the user changed the requested outcome;
- `review-rework`: review loops created unforecast rework.

The command preserves the initial forecast, current approved envelope, actual consumption, remaining estimate, projected total, and reason. It returns `stop-for-approval` when the projection exceeds the approved envelope or scope/workflow changed. Stop and ask the user. After approval, repeat the reforecast with `--approved`; include updated `--work-units`, `--implementation-agents`, `--reviewers`, or `--max-correction-passes` when the execution model changed.

Do not continue merely because a reviewer found something. Do not hide an overrun by starting a new run. `finish --outcome completed` refuses unresolved reforecasts and approvals.

## Finish and reconcile

Finish from the same worktree and branch immediately before handoff. Supply aggregate tokens if they are available.

```text
python3 <skill-directory>/scripts/calibrate.py finish <run_id> --repo . --outcome completed --aggregate-tokens 166000
```

Use `blocked` or `abandoned` when appropriate. Close every forecast, including declined work:

```text
python3 <skill-directory>/scripts/calibrate.py finish <run_id> --outcome abandoned
```

The final token event is normally written after the response. The next `forecast`, `stats`, or explicit `reconcile` records the first task-complete turn after the forecast boundary using `last_token_usage`.

Runs with `agent-scope-creep`, `workflow-expansion`, `environment-surprise`, `user-scope-change`, or `review-rework` remain inspectable but are excluded from baseline calibration. This prevents execution failures and changed tasks from teaching the estimator that the original forecast was intrinsically wrong. `estimator-error` and `canary-variance` remain calibration evidence.

## Correct bad observations

```text
python3 <skill-directory>/scripts/calibrate.py runs --limit 20
python3 <skill-directory>/scripts/calibrate.py invalidate <run_id> --reason wrong-worktree
```

Invalidation appends an event. Never edit `history.jsonl` manually. Invalidate wrong timing, token, worktree, or Git scope; do not invalidate a truthful overrun.

## Present the decision point

Use a compact form:

> Expected files: `src/widget.py`, `tests/test_widget.py`; possible: `src/cache.py`. Estimated final diff: +80–160 / −10–40 lines.
>
> Execution: 6 units, 1 implementer, 1 combined reviewer, 1 correction pass. Estimated effort: 45–75 active minutes. Tokens: 30k–55k incremental, 92k–117k projected root final context; 45k–80k aggregate across agents. Calibration: 8 comparable runs, medium confidence. Biggest uncertainty: container build latency.

Omit aggregate tokens when no multi-agent work is planned. Mark telemetry unavailable rather than fabricating it.

## Interpret calibration conservatively

- Keep the 20 most recent eligible completions.
- Use task-class observations after five comparable completions; otherwise use global history.
- Apply the observed 20th-to-80th-percentile ratio after five samples. Before that, report history without changing the submitted range.
- Treat time, root final-context tokens, aggregate agent tokens, file count, and final diff lines as separate signals.
- Treat zero-file or zero-diff observations as valid only when no repository files intentionally changed. Invalidate accidental zeroes from the wrong checkout.
- Preserve the original forecast and append checkpoints/reforecasts; never overwrite history.

Do not repeat unchanged estimates in routine updates. Do not add an estimate to a direct answer, completed result, or status report unless it proposes additional future work.
