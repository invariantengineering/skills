---
name: estimate-time-and-tokens
description: Use whenever proposing future work, presenting an implementation or remediation plan, offering to make changes, comparing approaches, or asking whether to proceed. Forecast elapsed time, turn-final tokens, files touched, and added/deleted lines, then record outcomes so later estimates calibrate against observed work.
---

# Estimate Time and Tokens

Give the user a concrete cost and code-surface forecast before they approve proposed work. Learn from completed runs instead of repeatedly relying on intuition alone.

## Forecast the complete scope

1. Include discovery, implementation, validation, review, and handoff when they are required for completion.
2. Estimate agent wall-clock time in the current environment, including likely tool and test latency.
3. Estimate final-turn `last_token_usage.total_tokens`. Treat it as an operational context-usage measure, not billing data or cumulative session usage. When current session telemetry is available, use its latest value as a lower bound rather than estimating below tokens already observed.
4. Inspect enough of the repository to name likely files without beginning the implementation.
5. Separate `expected_files` from less-certain `possible_files`. Use repository-relative paths only.
6. Estimate additions and deletions as separate rounded ranges. Do not invent a “modified lines” count.
7. State the largest material uncertainty. Widen ranges when the repository, failure mode, approval path, or validation cost is unclear.

Do not pause solely to make the estimate precise. If inspection cannot resolve a path, name the likely directory or mark the file as possible.

## Record and calibrate the forecast

Use the bundled `scripts/calibrate.py` ledger. It stores append-only JSONL under `~/.codex/state/estimate-time-and-tokens/` by default. It records forecast metadata, timestamps, repository-relative paths, Git counts, and token counters. Never add prompts, source contents, tool output, secrets, or absolute repository paths.

Keep `SKILL.md` static between runs. Record forecasts and outcomes in the ledger; do not rewrite the skill with per-task results.

Before presenting a forecast, run `forecast`. Use a stable task class such as `bugfix`, `feature`, `refactor`, `docs`, `ops`, or `research`.

```text
python3 <skill-directory>/scripts/calibrate.py forecast --task-class bugfix --time-low 20 --time-high 35 --tokens-low 40000 --tokens-high 70000 --expected-file src/widget.py --possible-file tests/test_widget.py --add-low 25 --add-high 60 --delete-low 5 --delete-high 20
```

Use the returned calibrated ranges in the user-facing estimate and retain the `run_id` for the current task. The token baseline is never lower than the latest observed turn usage and adds 20% headroom when that observation exceeds the submitted range. The command also reconciles any completed prior run whose final token event has become available.

After approval, create or select the clean feature worktree where implementation will occur. Start the clock from that exact worktree before editing any files:

```text
python3 <skill-directory>/scripts/calibrate.py start <run_id> --repo .
```

Never start from the primary checkout when implementation will happen in a linked worktree. `start` refuses protected branches and dirty repositories by default. Use `--allow-protected-branch` or `--allow-dirty` only for intentional time/token-only tracking where Git scope will not be calibrated.

Pause before waiting on the user, an approval, or an external dependency; resume when active work restarts:

```text
python3 <skill-directory>/scripts/calibrate.py pause <run_id>
python3 <skill-directory>/scripts/calibrate.py resume <run_id>
```

Immediately before the completed handoff, finish the run from the same worktree and branch:

```text
python3 <skill-directory>/scripts/calibrate.py finish <run_id> --repo . --outcome completed
```

Use `blocked` or `abandoned` when appropriate. Those outcomes remain in history but are excluded from calibration. A run started with `--allow-dirty` fails closed for Git scope rather than attributing unrelated changes.

Close every forecast. If the user declines the work or implementation never starts, finish it as `abandoned` or `blocked`; an unstarted run cannot be marked `completed`.

```text
python3 <skill-directory>/scripts/calibrate.py finish <run_id> --outcome abandoned
```

Use this lifecycle for every estimated implementation: forecast, select the feature worktree, start before edits, pause/resume for material interruptions, finish in the same worktree, then reconcile on the following turn.

The current turn's final token event is normally written after the response. `finish` therefore marks token usage pending. The next `forecast`, `stats`, or explicit `reconcile` command finds the first `task_complete` after the saved forecast boundary and records the last preceding `last_token_usage` event. Never substitute `total_token_usage`.

If the ledger or session telemetry is unavailable, still give the forecast and say that calibration is unavailable. Do not block useful work on measurement.

## Correct bad observations

List recent runs before correcting one:

```text
python3 <skill-directory>/scripts/calibrate.py runs --limit 20
```

Invalidate a run whose timing, token, worktree, or Git scope is wrong. Give a short non-sensitive reason:

```text
python3 <skill-directory>/scripts/calibrate.py invalidate <run_id> --reason wrong-worktree
```

Invalidation appends an event; it never deletes or rewrites history. Invalidated runs remain inspectable but are excluded from reconciliation and every calibration metric. Never edit `history.jsonl` manually.

## Present the decision point

Use this compact structure:

> Expected files: `src/widget.py`, `tests/test_widget.py`; possible: `src/cache.py`. Estimated diff: +25–60 / −5–20 lines.
>
> Estimated effort: 20–35 minutes, roughly 40k–70k tokens. Calibration: 8 comparable runs, medium confidence. Biggest uncertainty: integration-test fallout.

Omit an empty possible-files clause. For multiple options, forecast and record each option separately only if the user is genuinely choosing between them.

## Interpret calibration conservatively

- The ledger keeps the 20 most recent completed observations.
- It uses task-class observations after five comparable completions; otherwise it falls back to global history.
- It applies the observed 20th-to-80th-percentile ratio range after five samples. Before that, it reports history but leaves the raw range unchanged.
- Confidence is low below five samples, medium from five through fourteen, and high at fifteen or more.
- Time, tokens, file count, and changed lines remain separate signals. A slow build can consume time without many tokens.
- File and diff factors are supporting evidence, not permission to name files that repository inspection does not support.
- Treat zero-file or zero-diff observations as valid only when the task intentionally changed no repository files. Invalidate accidental zeroes caused by tracking from the wrong checkout.
- Re-estimate and create a new forecast when the user changes scope or inspection reveals materially different work. Close the superseded run as `abandoned`.

Do not repeat unchanged estimates in routine updates. Do not add an estimate to a direct answer, completed result, or status report unless it proposes additional future work.
