#!/usr/bin/env python3
"""Record forecasts and calibrate them against completed turns."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
ESTIMATOR_VERSION = "2.0.0"
MEASUREMENT_VERSION = 2
DEFAULT_STATE_DIR = Path.home() / ".codex" / "state" / "estimate-time-and-tokens"
DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
PROTECTED_BRANCHES = {"main", "master", "prod", "production", "stage", "staging"}
CHECKPOINT_TRIGGERS = {
    "canary-checkpoint",
    "workflow-change",
    "scope-change",
    "environment-change",
    "failed-canary",
    "budget-mismatch",
}
DEVIATION_CLASSES = {
    "estimator-error",
    "canary-variance",
    "agent-scope-creep",
    "workflow-expansion",
    "environment-surprise",
    "user-scope-change",
    "review-rework",
}
CALIBRATION_EXCLUDED_DEVIATIONS = {
    "agent-scope-creep",
    "workflow-expansion",
    "environment-surprise",
    "user-scope-change",
    "review-rework",
}
FINDING_CLASSES = {"required-now", "backlog", "out-of-scope"}


class CalibrationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def state_dir(args: argparse.Namespace) -> Path:
    configured = args.state_dir or os.environ.get("ESTIMATE_CALIBRATION_STATE_DIR")
    return Path(configured).expanduser() if configured else DEFAULT_STATE_DIR


def history_path(args: argparse.Namespace) -> Path:
    return state_dir(args) / "history.jsonl"


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CalibrationError(
                f"invalid history JSON on line {line_number}: {exc}"
            ) from exc
        if event.get("schema_version") != SCHEMA_VERSION:
            raise CalibrationError(f"unsupported history schema on line {line_number}")
        events.append(event)
    return events


def append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {"schema_version": SCHEMA_VERSION, **event}
    encoded = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n").encode()
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, encoded)
    finally:
        os.close(descriptor)


def reconstruct(events: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for event in events:
        run_id = event.get("run_id")
        if not run_id:
            continue
        run = runs.setdefault(run_id, {"run_id": run_id, "events": []})
        run["events"].append(event)
        kind = event.get("event")
        if kind == "forecast":
            run.update(event)
        elif kind == "start":
            run["start"] = event
        elif kind == "finish":
            run["finish"] = event
        elif kind == "reconcile":
            run["reconcile"] = event
        elif kind == "invalidate":
            run["invalidate"] = event
        elif kind == "checkpoint":
            run.setdefault("checkpoints", []).append(event)
            run["checkpoint"] = event
        elif kind == "reforecast":
            run.setdefault("reforecasts", []).append(event)
            run["reforecast"] = event
        elif kind == "classify":
            run.setdefault("classifications", []).append(event)
    return runs


def short_note(value: str, label: str) -> str:
    note = value.strip()
    if not note or len(note) > 200 or "\n" in note:
        raise CalibrationError(
            f"{label} must be a single non-empty line of at most 200 characters"
        )
    return note


def calibration_exclusion(run: dict[str, Any]) -> str | None:
    deviations = {event.get("deviation") for event in run.get("reforecasts", [])}
    excluded = sorted(deviations & CALIBRATION_EXCLUDED_DEVIATIONS)
    return ",".join(excluded) if excluded else None


def require_active_run(run: dict[str, Any]) -> None:
    require_valid_run(run)
    if not run.get("start") or run.get("finish"):
        raise CalibrationError("command requires an active run")


def current_token_usage(run: dict[str, Any], explicit: int | None) -> int | None:
    if explicit is not None:
        return explicit
    stored_session = run.get("session_file")
    usage = latest_usage(Path(stored_session)) if stored_session else None
    return usage["total_tokens"] if usage else None


def current_envelope(run: dict[str, Any]) -> dict[str, list[int] | None]:
    approved = [
        event
        for event in run.get("reforecasts", [])
        if event.get("approval_state") in {"approved", "not-required"}
    ]
    if approved:
        latest = approved[-1]
        return {
            "time_minutes": latest["projected_total_time_minutes"],
            "root_tokens": latest.get("projected_root_tokens")
            or run["forecast_tokens"],
            "aggregate_tokens": latest.get("projected_aggregate_tokens")
            or run.get("forecast_aggregate_tokens"),
        }
    return {
        "time_minutes": run["forecast_time_minutes"],
        "root_tokens": run["forecast_tokens"],
        "aggregate_tokens": run.get("forecast_aggregate_tokens"),
    }


def current_execution_model(run: dict[str, Any]) -> dict[str, int]:
    model = {
        "work_units": run.get("work_units", 1),
        "implementation_agents": run.get("implementation_agents", 1),
        "reviewers": run.get("reviewers", 0),
        "max_correction_passes": run.get("max_correction_passes", 1),
    }
    for event in run.get("reforecasts", []):
        if event.get("approval_state") == "approved":
            model.update(event.get("execution_model") or {})
    return model


def unresolved_control(run: dict[str, Any]) -> str | None:
    unresolved: str | None = None
    for event in run["events"]:
        if event.get("event") == "checkpoint" and event.get("control_action") in {
            "reforecast-required",
            "approval-required",
        }:
            unresolved = event["control_action"]
        elif (
            event.get("event") == "classify"
            and event.get("classification") == "required-now"
        ):
            unresolved = "reforecast-required"
        elif event.get("event") == "reforecast":
            unresolved = (
                "approval-required"
                if event.get("approval_state") == "pending"
                else None
            )
    return unresolved


def unresolved_checkpoint_triggers(run: dict[str, Any]) -> set[str]:
    triggers: set[str] = set()
    for event in run["events"]:
        if event.get("event") == "checkpoint":
            triggers.update(event.get("triggers", []))
        elif event.get("event") == "reforecast":
            triggers.clear()
    return triggers


def session_file(sessions_dir: Path) -> Path | None:
    thread_id = os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID")
    if not thread_id or not sessions_dir.exists():
        return None
    matches = list(sessions_dir.rglob(f"*{thread_id}*.jsonl"))
    return matches[0].resolve() if len(matches) == 1 else None


def token_usage(payload: dict[str, Any]) -> dict[str, int | None] | None:
    usage = (payload.get("info") or {}).get("last_token_usage")
    if not isinstance(usage, dict) or not isinstance(usage.get("total_tokens"), int):
        return None
    values: dict[str, int | None] = {}
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ):
        value = usage.get(key)
        values[key] = int(value) if isinstance(value, int) else None
    if values["total_tokens"] is None:
        return None
    return values


def token_counter_delta(
    before: dict[str, int | None] | None, after: dict[str, int | None] | None
) -> dict[str, int | None] | None:
    """Return trustworthy cumulative-counter deltas, or unavailable."""
    if not before or not after:
        return None
    deltas: dict[str, int | None] = {}
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
    ):
        old, new = before.get(key), after.get(key)
        if old is None or new is None or new < old:
            return None
        deltas[key] = new - old
    cached = deltas.get("cached_input_tokens")
    input_tokens = deltas.get("input_tokens")
    deltas["uncached_input_tokens"] = (
        input_tokens - cached
        if input_tokens is not None and cached is not None and input_tokens >= cached
        else None
    )
    return deltas


def latest_usage(path: Path) -> dict[str, int | None] | None:
    if not path.exists():
        return None
    usage: dict[str, int | None] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = envelope.get("payload") or {}
        if envelope.get("type") == "event_msg" and payload.get("type") == "token_count":
            usage = token_usage(payload) or usage
    return usage


def session_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(envelope, dict) and envelope.get("timestamp"):
            events.append(envelope)
    return events


def execution_measurement(
    path: Path,
    started_at: str,
    finished_at: str,
    execution_session_id: str | None = None,
    execution_turn_id: str | None = None,
) -> dict[str, Any]:
    """Measure only one attributable interval in one session.

    Old records intentionally continue to use ``last_token_usage``. New
    records require an explicit start boundary and cumulative counters. Any
    reset, overlap, or missing identifier makes the token measurement unknown.
    """
    start, finish = parse_time(started_at), parse_time(finished_at)
    selected = []
    for envelope in session_events(path):
        timestamp = parse_time(envelope["timestamp"])
        if not start <= timestamp <= finish:
            continue
        payload = envelope.get("payload") or {}
        identifiers = {envelope.get("session_id"), payload.get("session_id")}
        turns = {envelope.get("turn_id"), payload.get("turn_id")}
        if execution_session_id and execution_session_id not in identifiers:
            continue
        if execution_turn_id and execution_turn_id not in turns:
            continue
        selected.append(envelope)
    observed_sessions = {
        identifier
        for envelope in selected
        for identifier in {
            envelope.get("session_id"),
            (envelope.get("payload") or {}).get("session_id"),
        }
        if identifier
    }
    observed_turns = {
        identifier
        for envelope in selected
        for identifier in {
            envelope.get("turn_id"),
            (envelope.get("payload") or {}).get("turn_id"),
        }
        if identifier
    }
    if (not execution_session_id and len(observed_sessions) > 1) or (
        not execution_turn_id and len(observed_turns) > 1
    ):
        return {
            "status": "unavailable",
            "reason": "ambiguous overlapping session or turn identifiers",
            "token_usage": None,
            "context_size": None,
        }
    counters = []
    for envelope in selected:
        payload = envelope.get("payload") or {}
        if envelope.get("type") == "event_msg" and payload.get("type") == "token_count":
            usage = token_usage(payload)
            if usage:
                counters.append((envelope["timestamp"], usage))
    if len(counters) < 2:
        return {
            "status": "unavailable",
            "reason": "fewer than two attributable cumulative counter samples",
            "token_usage": None,
            "context_size": None,
        }
    for (_, previous), (_, current) in zip(counters, counters[1:]):
        if token_counter_delta(previous, current) is None:
            return {
                "status": "unavailable",
                "reason": "counter reset, missing counter, or cached-input overlap",
                "token_usage": None,
                "context_size": None,
            }
    first, last = counters[0][1], counters[-1][1]
    delta = token_counter_delta(first, last)
    if delta is None:
        return {
            "status": "unavailable",
            "reason": "counter reset, missing counter, or cached-input overlap",
            "token_usage": None,
            "context_size": None,
        }
    context_sizes = []
    for envelope in selected:
        info = ((envelope.get("payload") or {}).get("info") or {})
        value = info.get("context_size")
        if isinstance(value, int):
            context_sizes.append(value)
    return {
        "status": "available",
        "reason": None,
        "token_usage": delta,
        "context_size": context_sizes[-1] if context_sizes else None,
    }


def last_usage_for_turn(path: Path, after: str) -> dict[str, int | None] | None:
    """Legacy reconciliation helper retained for pre-v2 ledger records."""
    events = session_events(path)
    after_time = parse_time(after)
    last_usage: dict[str, int | None] | None = None
    for envelope in events:
        if parse_time(envelope["timestamp"]) < after_time:
            continue
        payload = envelope.get("payload") or {}
        if envelope.get("type") == "event_msg" and payload.get("type") == "token_count":
            last_usage = token_usage(payload) or last_usage
        if envelope.get("type") == "event_msg" and payload.get("type") == "task_complete":
            return last_usage
    return last_usage


def reconcile_pending(args: argparse.Namespace) -> int:
    path = history_path(args)
    runs = reconstruct(load_events(path))
    reconciled = 0
    for run in runs.values():
        finish = run.get("finish")
        if not finish or finish.get("outcome") != "completed" or run.get("invalidate"):
            continue
        if any(event.get("event") == "reconcile" for event in run["events"]):
            continue
        stored_session = run.get("session_file")
        if not stored_session:
            continue
        if not run.get("start"):
            usage = last_usage_for_turn(Path(stored_session), run["forecast_at"])
            if usage is None:
                continue
            append_event(
                path,
                {
                    "event": "reconcile",
                    "run_id": run["run_id"],
                    "reconciled_at": utc_now(),
                    "measurement_version": 1,
                    "token_metric": "last_token_usage",
                    "measurement_status": "legacy",
                    "token_usage": usage,
                },
            )
            reconciled += 1
            continue
        start = run["start"]
        measurement = execution_measurement(
            Path(stored_session),
            start["started_at"],
            finish["finished_at"],
            start.get("execution_session_id"),
            start.get("execution_turn_id"),
        )
        append_event(
            path,
            {
                "event": "reconcile",
                "run_id": run["run_id"],
                "reconciled_at": utc_now(),
                "measurement_version": MEASUREMENT_VERSION,
                "token_metric": "cumulative_counter_delta",
                "metric_definitions": {
                    "input_tokens": "uncached plus cached input counter delta",
                    "cached_input_tokens": "cached input counter delta",
                    "uncached_input_tokens": "input delta minus cached input delta",
                    "output_tokens": "output counter delta",
                    "reasoning_output_tokens": "reasoning output counter delta when provided",
                    "total_tokens": "total counter delta",
                    "context_size": "latest context size; descriptive, not consumed tokens",
                },
                "measurement_status": measurement["status"],
                "measurement_reason": measurement["reason"],
                "token_usage": measurement["token_usage"],
                "context_size": measurement["context_size"],
            },
        )
        reconciled += 1
    return reconciled


def midpoint(bounds: list[float]) -> float:
    return (bounds[0] + bounds[1]) / 2


def quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def confidence(sample_size: int) -> str:
    if sample_size == 0:
        return "none"
    if sample_size < 5:
        return "low"
    if sample_size < 15:
        return "medium"
    return "high"


def normalize_task_class(value: str | None) -> str:
    normalized = (value or "general").strip().lower().replace("_", "-")
    aliases = {
        "bug-fix": "bugfix",
        "bug-fixing": "bugfix",
        "feature-work": "feature",
        "enhancement": "feature",
        "maintenance": "chore",
    }
    return aliases.get(normalized, normalized)


def completed_runs(args: argparse.Namespace) -> list[dict[str, Any]]:
    runs = reconstruct(load_events(history_path(args)))
    completed = [
        run
        for run in runs.values()
        if run.get("finish", {}).get("outcome") == "completed"
        and not run.get("invalidate")
        and not calibration_exclusion(run)
    ]
    return sorted(completed, key=lambda run: run["finish"]["finished_at"])


def observations(runs: list[dict[str, Any]], metric: str) -> list[float]:
    ratios: list[float] = []
    for run in runs:
        if metric == "time":
            predicted = midpoint(run["forecast_time_minutes"])
            elapsed = run["finish"].get("active_elapsed_seconds")
            if elapsed is None:
                continue
            actual = elapsed / 60
        elif metric == "tokens":
            if not run.get("reconcile"):
                continue
            if run["reconcile"].get("measurement_status") == "unavailable":
                continue
            observed_floor = run.get("observed_token_floor")
            if observed_floor is not None and run.get("submitted_forecast_tokens"):
                predicted = midpoint(run["submitted_forecast_tokens"])
                total = (run["reconcile"].get("token_usage") or {}).get("total_tokens")
                if total is None:
                    continue
                actual = (
                    total
                    if run["reconcile"].get("measurement_version", 1) >= MEASUREMENT_VERSION
                    else max(0, total - observed_floor)
                )
            else:
                predicted = midpoint(run["forecast_tokens"])
                total = (run["reconcile"].get("token_usage") or {}).get("total_tokens")
                if total is None:
                    continue
                actual = total
        elif metric == "aggregate_tokens":
            predicted_bounds = run.get("forecast_aggregate_tokens")
            actual = run["finish"].get("actual_aggregate_tokens")
            if not predicted_bounds or actual is None:
                continue
            predicted = midpoint(predicted_bounds)
        elif metric == "files":
            predicted = len(
                set(run.get("expected_files", []) + run.get("possible_files", []))
            )
            actual_files = run["finish"].get("actual_files")
            if actual_files is None:
                continue
            actual = len(actual_files)
        elif metric == "diff":
            additions = run.get("forecast_additions", [0, 0])
            deletions = run.get("forecast_deletions", [0, 0])
            predicted = midpoint(additions) + midpoint(deletions)
            additions = run["finish"].get("actual_additions")
            deletions = run["finish"].get("actual_deletions")
            if additions is None or deletions is None:
                continue
            actual = additions + deletions
        else:
            raise CalibrationError(f"unknown metric: {metric}")
        if predicted > 0 and actual >= 0:
            ratios.append(actual / predicted)
    return ratios


def select_runs(
    runs: list[dict[str, Any]], task_class: str
) -> tuple[list[dict[str, Any]], str]:
    normalized = normalize_task_class(task_class)
    matching = [
        run for run in runs if normalize_task_class(run.get("task_class")) == normalized
    ]
    # Filter by comparable class before applying the history limit.
    source_runs = matching if len(matching) >= 5 else runs
    return (source_runs[-20:], "task_class") if len(matching) >= 5 else (runs[-20:], "global")


def metric_summary(runs: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    ratios = observations(runs, metric)
    summary: dict[str, Any] = {
        "sample_size": len(ratios),
        "confidence": confidence(len(ratios)),
        "applied": len(ratios) >= 5,
    }
    if ratios:
        summary.update(
            {
                "median_factor": round(statistics.median(ratios), 3),
                "p20_factor": round(quantile(ratios, 0.2), 3),
                "p80_factor": round(quantile(ratios, 0.8), 3),
            }
        )
    return summary


def round_bounds(bounds: list[float], metric: str) -> list[int]:
    if metric == "time":
        unit = 5
    else:
        unit = 1000 if max(bounds) >= 10000 else 500
    low = max(unit, math.floor(bounds[0] / unit) * unit)
    high = max(low, math.ceil(bounds[1] / unit) * unit)
    return [int(low), int(high)]


def calibrated_bounds(
    raw: list[int], summary: dict[str, Any], metric: str
) -> list[int]:
    if not summary["applied"]:
        return raw
    center = midpoint(raw)
    return round_bounds(
        [center * summary["p20_factor"], center * summary["p80_factor"]], metric
    )


def token_total_bounds(incremental: list[int], observed_total: int | None) -> list[int]:
    if not observed_total:
        return incremental
    return [observed_total + incremental[0], observed_total + incremental[1]]


def normalize_relative_paths(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise CalibrationError(
                f"planned paths must be repository-relative: {value}"
            )
        normalized.append(path.as_posix())
    return sorted(set(normalized))


def git(args: list[str], repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CalibrationError(result.stderr.strip() or "Git command failed")
    return result.stdout


def repo_identity(repo: Path) -> dict[str, Any]:
    root = Path(git(["rev-parse", "--show-toplevel"], repo).strip()).resolve()
    clean = not git(["status", "--porcelain"], root).strip()
    return {
        "root": root,
        "repo_name": root.name,
        "repo_fingerprint": hashlib.sha256(str(root).encode()).hexdigest()[:16],
        "clean": clean,
        "head": git(["rev-parse", "HEAD"], root).strip(),
        "branch": git(["branch", "--show-current"], root).strip(),
    }


def diff_stats(repo: Path, base: str) -> dict[str, Any]:
    files: dict[str, tuple[int, int]] = {}
    for line in git(["diff", "--numstat", base], repo).splitlines():
        added, deleted, path = line.split("\t", 2)
        files[path] = (int(added), int(deleted)) if added != "-" else (0, 0)
    for path in git(["ls-files", "--others", "--exclude-standard"], repo).splitlines():
        if path in files:
            continue
        data = (repo / path).read_bytes()
        files[path] = (0, 0) if b"\0" in data else (len(data.splitlines()), 0)
    return {
        "actual_files": sorted(files),
        "actual_additions": sum(value[0] for value in files.values()),
        "actual_deletions": sum(value[1] for value in files.values()),
    }


def active_elapsed(events: list[dict[str, Any]], finished_at: str) -> int:
    running_since: datetime | None = None
    elapsed = 0.0
    for event in events:
        kind = event.get("event")
        if kind == "start" and running_since is None:
            running_since = parse_time(event["started_at"])
        elif kind == "pause" and running_since is not None:
            elapsed += (parse_time(event["paused_at"]) - running_since).total_seconds()
            running_since = None
        elif kind == "resume" and running_since is None:
            running_since = parse_time(event["resumed_at"])
    if running_since is not None:
        elapsed += (parse_time(finished_at) - running_since).total_seconds()
    return max(0, round(elapsed))


def find_run(args: argparse.Namespace) -> dict[str, Any]:
    run = reconstruct(load_events(history_path(args))).get(args.run_id)
    if not run:
        raise CalibrationError(f"unknown run id: {args.run_id}")
    return run


def require_valid_run(run: dict[str, Any]) -> None:
    if run.get("invalidate"):
        raise CalibrationError("run is invalidated")


def command_forecast(args: argparse.Namespace) -> dict[str, Any]:
    reconciled = reconcile_pending(args)
    runs = completed_runs(args)
    selected, source = select_runs(runs, args.task_class)
    time_summary = metric_summary(selected, "time")
    token_summary = metric_summary(selected, "tokens")
    aggregate_token_summary = metric_summary(selected, "aggregate_tokens")
    scope = {
        "files": metric_summary(selected, "files"),
        "diff_lines": metric_summary(selected, "diff"),
    }
    raw_time = [args.time_low, args.time_high]
    submitted_tokens = [args.tokens_low, args.tokens_high]
    run_id = uuid.uuid4().hex[:12]
    sessions_dir = (
        Path(args.sessions_dir).expanduser()
        if args.sessions_dir
        else DEFAULT_SESSIONS_DIR
    )
    current_session = session_file(sessions_dir)
    current_usage = latest_usage(current_session) if current_session else None
    token_floor = current_usage["total_tokens"] if current_usage else None
    raw_tokens = token_total_bounds(submitted_tokens, token_floor)
    aggregate_tokens_low = getattr(args, "aggregate_tokens_low", None)
    aggregate_tokens_high = getattr(args, "aggregate_tokens_high", None)
    aggregate_tokens = (
        [aggregate_tokens_low, aggregate_tokens_high]
        if aggregate_tokens_low is not None
        else None
    )
    calibrated_time = calibrated_bounds(raw_time, time_summary, "time")
    calibrated_incremental_tokens = calibrated_bounds(
        submitted_tokens, token_summary, "tokens"
    )
    calibrated_tokens = token_total_bounds(calibrated_incremental_tokens, token_floor)
    metric_definitions = {
        "time": "active elapsed time between explicit start and finish boundaries",
        "tokens": "cumulative counter deltas within the attributable execution interval",
        "cached_input_tokens": "cached input counter delta, reported separately",
        "uncached_input_tokens": "input counter delta minus cached input delta",
        "output_tokens": "output counter delta",
        "context_size": "descriptive context size, never a consumed-token measurement",
    }
    event = {
        "event": "forecast",
        "run_id": run_id,
        "estimator_version": ESTIMATOR_VERSION,
        "forecast_at": utc_now(),
        "task_class": normalize_task_class(args.task_class),
        "forecast_time_minutes": raw_time,
        "forecast_tokens": raw_tokens,
        "submitted_forecast_tokens": submitted_tokens,
        "forecast_aggregate_tokens": aggregate_tokens,
        "observed_token_floor": token_floor,
        "work_units": getattr(args, "work_units", 1),
        "implementation_agents": getattr(args, "implementation_agents", 1),
        "reviewers": getattr(args, "reviewers", 0),
        "max_correction_passes": getattr(args, "max_correction_passes", 1),
        "environment_assumptions": [
            short_note(value, "environment assumption")
            for value in getattr(args, "environment_assumption", [])
        ],
        "expected_files": normalize_relative_paths(args.expected_file),
        "possible_files": normalize_relative_paths(args.possible_file),
        "forecast_additions": [args.add_low, args.add_high],
        "forecast_deletions": [args.delete_low, args.delete_high],
        "session_file": str(current_session) if current_session else None,
        "measurement_version": MEASUREMENT_VERSION,
        "metric_definitions": metric_definitions,
        "model_metadata": {
            key: os.environ[key]
            for key in ("CODEX_MODEL", "CODEX_MODEL_VERSION")
            if os.environ.get(key)
        },
        "raw_forecast": {
            "time_minutes": raw_time,
            "incremental_tokens": submitted_tokens,
            "final_context": raw_tokens,
        },
        "displayed_forecast": {
            "time_minutes": calibrated_time,
            "incremental_tokens": calibrated_incremental_tokens,
            "final_context": calibrated_tokens,
        },
    }
    append_event(history_path(args), event)
    return {
        "run_id": run_id,
        "reconciled_prior_runs": reconciled,
        "calibration_source": source,
        "time_minutes": {
            "raw": raw_time,
            "calibrated": calibrated_time,
            **time_summary,
        },
        "tokens": {
            "submitted": submitted_tokens,
            "baseline": raw_tokens,
            "incremental": submitted_tokens,
            "incremental_calibrated": calibrated_incremental_tokens,
            "final_context": raw_tokens,
            "calibrated": calibrated_tokens,
            "observed_floor": token_floor,
            "metric": "last_token_usage.total_tokens",
            **token_summary,
        },
        "aggregate_tokens": {
            "forecast": aggregate_tokens,
            "metric": "sum of agent-session totals when available",
            **aggregate_token_summary,
        },
        "execution_model": {
            "work_units": event["work_units"],
            "implementation_agents": event["implementation_agents"],
            "reviewers": event["reviewers"],
            "max_correction_passes": event["max_correction_passes"],
            "environment_assumptions": event["environment_assumptions"],
        },
        "code_scope": {
            "expected_files": event["expected_files"],
            "possible_files": event["possible_files"],
            "additions": event["forecast_additions"],
            "deletions": event["forecast_deletions"],
            "historical_factors": scope,
        },
        "token_reconciliation": "pending" if current_session else "unavailable",
    }


def command_start(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    require_valid_run(run)
    if run.get("start"):
        raise CalibrationError("run already started")
    identity = repo_identity(Path(args.repo).resolve())
    if identity["branch"] in PROTECTED_BRANCHES and not args.allow_protected_branch:
        raise CalibrationError(
            f"refusing to start on protected branch {identity['branch']!r}; "
            "create or select the implementation worktree first"
        )
    if not identity["clean"] and not args.allow_dirty:
        raise CalibrationError(
            "refusing to start in a dirty repository; start before edits or use --allow-dirty "
            "for time/token-only tracking"
        )
    event = {
        "event": "start",
        "run_id": args.run_id,
        "started_at": utc_now(),
        "repo_name": identity["repo_name"],
        "repo_fingerprint": identity["repo_fingerprint"],
        "branch": identity["branch"],
        "git_base": identity["head"] if identity["clean"] else None,
        "git_scope_available": identity["clean"],
        "git_scope_reason": None
        if identity["clean"]
        else "repository was dirty at start",
        "execution_session_id": getattr(args, "execution_session_id", None)
        or os.environ.get("CODEX_SESSION_ID"),
        "execution_turn_id": getattr(args, "execution_turn_id", None)
        or os.environ.get("CODEX_TURN_ID"),
        "execution_boundary": "start",
    }
    append_event(history_path(args), event)
    return {
        key: value for key, value in event.items() if key not in {"event", "run_id"}
    }


def command_pause(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    require_valid_run(run)
    if not run.get("start") or run.get("finish"):
        raise CalibrationError("only an active run can be paused")
    event = {"event": "pause", "run_id": args.run_id, "paused_at": utc_now()}
    append_event(history_path(args), event)
    return {"paused_at": event["paused_at"]}


def command_resume(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    require_valid_run(run)
    if not run.get("start") or run.get("finish"):
        raise CalibrationError("only an active run can be resumed")
    event = {"event": "resume", "run_id": args.run_id, "resumed_at": utc_now()}
    append_event(history_path(args), event)
    return {"resumed_at": event["resumed_at"]}


def command_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    require_active_run(run)
    execution_model = current_execution_model(run)
    work_units = execution_model["work_units"]
    if not 0 <= args.completed_units <= work_units:
        raise CalibrationError(f"completed units must be between 0 and {work_units}")
    if args.correction_passes < 0:
        raise CalibrationError("correction passes cannot be negative")
    checked_at = utc_now()
    elapsed = active_elapsed(run["events"], checked_at)
    root_tokens = current_token_usage(run, args.root_tokens)
    envelope = current_envelope(run)
    triggers = set(args.trigger)
    completion_ratio = args.completed_units / work_units
    projected_time = None
    if work_units > 1 and args.completed_units == 1:
        triggers.add("canary-checkpoint")
    if (
        args.implementation_agents is not None
        and args.implementation_agents != execution_model["implementation_agents"]
    ):
        triggers.add("workflow-change")
    if args.reviewers is not None and args.reviewers != execution_model["reviewers"]:
        triggers.add("workflow-change")
    if completion_ratio > 0:
        projected_time = round((elapsed / 60) / completion_ratio, 1)
        if projected_time > envelope["time_minutes"][1]:
            triggers.add("budget-mismatch")
    if root_tokens is not None and root_tokens > envelope["root_tokens"][1]:
        triggers.add("budget-mismatch")
    if (
        args.aggregate_tokens is not None
        and envelope["aggregate_tokens"]
        and args.aggregate_tokens > envelope["aggregate_tokens"][1]
    ):
        triggers.add("budget-mismatch")
    over_correction_cap = (
        args.correction_passes > execution_model["max_correction_passes"]
    )
    if over_correction_cap:
        control_action = "approval-required"
    elif triggers:
        control_action = "reforecast-required"
    else:
        control_action = "continue"
    event = {
        "event": "checkpoint",
        "run_id": args.run_id,
        "checked_at": checked_at,
        "active_elapsed_seconds": elapsed,
        "completed_units": args.completed_units,
        "total_work_units": work_units,
        "execution_model": execution_model,
        "completion_ratio": round(completion_ratio, 3),
        "correction_passes": args.correction_passes,
        "root_token_usage": root_tokens,
        "aggregate_token_usage": args.aggregate_tokens,
        "projected_time_minutes_at_current_burn": projected_time,
        "triggers": sorted(triggers),
        "control_action": control_action,
        "reason": short_note(args.reason, "reason") if args.reason else None,
    }
    append_event(history_path(args), event)
    return {
        key: value for key, value in event.items() if key not in {"event", "run_id"}
    }


def command_classify(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    require_active_run(run)
    event = {
        "event": "classify",
        "run_id": args.run_id,
        "classified_at": utc_now(),
        "classification": args.classification,
        "summary": short_note(args.summary, "summary"),
        "control_action": "reforecast-required"
        if args.classification == "required-now"
        else "continue",
    }
    append_event(history_path(args), event)
    return {
        key: value for key, value in event.items() if key not in {"event", "run_id"}
    }


def command_reforecast(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    require_active_run(run)
    prior_control = unresolved_control(run)
    checkpoint_triggers = unresolved_checkpoint_triggers(run)
    reforecast_at = utc_now()
    elapsed_minutes = active_elapsed(run["events"], reforecast_at) / 60
    root_tokens = current_token_usage(run, args.root_tokens)
    projected_time = [
        math.floor(elapsed_minutes + args.remaining_time_low),
        math.ceil(elapsed_minutes + args.remaining_time_high),
    ]
    projected_root = (
        [
            root_tokens + args.remaining_tokens_low,
            root_tokens + args.remaining_tokens_high,
        ]
        if root_tokens is not None
        else None
    )
    projected_aggregate = (
        [
            args.aggregate_tokens + args.remaining_aggregate_tokens_low,
            args.aggregate_tokens + args.remaining_aggregate_tokens_high,
        ]
        if args.aggregate_tokens is not None
        and args.remaining_aggregate_tokens_low is not None
        else None
    )
    envelope = current_envelope(run)
    previous_execution_model = current_execution_model(run)
    execution_model = {
        key: value
        for key, value in {
            "work_units": args.work_units,
            "implementation_agents": args.implementation_agents,
            "reviewers": args.reviewers,
            "max_correction_passes": args.max_correction_passes,
        }.items()
        if value is not None
    }
    exceeds_envelope = projected_time[1] > envelope["time_minutes"][1]
    if projected_root is not None:
        exceeds_envelope = (
            exceeds_envelope or projected_root[1] > envelope["root_tokens"][1]
        )
    if projected_aggregate is not None and envelope["aggregate_tokens"]:
        exceeds_envelope = (
            exceeds_envelope or projected_aggregate[1] > envelope["aggregate_tokens"][1]
        )
    scope_changed = args.deviation in {
        "agent-scope-creep",
        "workflow-expansion",
        "environment-surprise",
        "user-scope-change",
        "review-rework",
    } or any(
        previous_execution_model[key] != value for key, value in execution_model.items()
    )
    approval_required = (
        exceeds_envelope
        or scope_changed
        or prior_control == "approval-required"
        or bool(checkpoint_triggers & {"scope-change", "workflow-change"})
    )
    approval_state = (
        "approved"
        if args.approved
        else "pending"
        if approval_required
        else "not-required"
    )
    event = {
        "event": "reforecast",
        "run_id": args.run_id,
        "reforecast_at": reforecast_at,
        "reason": short_note(args.reason, "reason"),
        "deviation": args.deviation,
        "active_elapsed_minutes": round(elapsed_minutes, 1),
        "root_token_usage": root_tokens,
        "aggregate_token_usage": args.aggregate_tokens,
        "remaining_time_minutes": [args.remaining_time_low, args.remaining_time_high],
        "remaining_incremental_root_tokens": [
            args.remaining_tokens_low,
            args.remaining_tokens_high,
        ],
        "remaining_aggregate_tokens": (
            [args.remaining_aggregate_tokens_low, args.remaining_aggregate_tokens_high]
            if args.remaining_aggregate_tokens_low is not None
            else None
        ),
        "projected_total_time_minutes": projected_time,
        "projected_root_tokens": projected_root,
        "projected_aggregate_tokens": projected_aggregate,
        "previous_approved_envelope": envelope,
        "previous_execution_model": previous_execution_model,
        "execution_model": execution_model,
        "checkpoint_triggers": sorted(checkpoint_triggers),
        "exceeds_approved_envelope": exceeds_envelope,
        "approval_required": approval_required,
        "approval_state": approval_state,
        "control_action": "stop-for-approval"
        if approval_state == "pending"
        else "continue",
    }
    append_event(history_path(args), event)
    return {
        key: value for key, value in event.items() if key not in {"event", "run_id"}
    }


def command_finish(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    require_valid_run(run)
    if run.get("finish"):
        raise CalibrationError("run is already finished")
    if args.outcome == "completed" and unresolved_control(run):
        raise CalibrationError(
            f"cannot complete run while control action is unresolved: {unresolved_control(run)}"
        )
    finished_at = utc_now()
    finish: dict[str, Any] = {
        "event": "finish",
        "run_id": args.run_id,
        "finished_at": finished_at,
        "outcome": args.outcome,
        "active_elapsed_seconds": active_elapsed(run["events"], finished_at),
        "actual_files": None,
        "actual_additions": None,
        "actual_deletions": None,
        "actual_aggregate_tokens": getattr(args, "aggregate_tokens", None),
        "calibration_exclusion": calibration_exclusion(run),
    }
    if not run.get("start"):
        if args.outcome == "completed":
            raise CalibrationError(
                "a completed run must be started before it is finished"
            )
        append_event(history_path(args), finish)
        return {
            "finished_at": finished_at,
            "outcome": args.outcome,
            "active_elapsed_seconds": 0,
            "actual_files": None,
            "actual_additions": None,
            "actual_deletions": None,
            "token_reconciliation": "excluded",
            "calibration_exclusion": finish["calibration_exclusion"],
        }
    start = run["start"]
    if start.get("git_scope_available"):
        identity = repo_identity(Path(args.repo).resolve())
        if identity["repo_fingerprint"] != start["repo_fingerprint"]:
            raise CalibrationError("finish must run from the repository used at start")
        if start.get("branch") and identity["branch"] != start["branch"]:
            raise CalibrationError("finish must run on the branch used at start")
        finish.update(diff_stats(identity["root"], start["git_base"]))
    append_event(history_path(args), finish)
    return {
        "finished_at": finished_at,
        "outcome": args.outcome,
        "active_elapsed_seconds": finish["active_elapsed_seconds"],
        "actual_files": finish["actual_files"],
        "actual_additions": finish["actual_additions"],
        "actual_deletions": finish["actual_deletions"],
        "actual_aggregate_tokens": finish["actual_aggregate_tokens"],
        "calibration_exclusion": finish["calibration_exclusion"],
        "token_reconciliation": "pending"
        if args.outcome == "completed"
        else "excluded",
    }


def command_reconcile(args: argparse.Namespace) -> dict[str, Any]:
    return {"reconciled_runs": reconcile_pending(args)}


def command_invalidate(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    if run.get("invalidate"):
        raise CalibrationError("run is already invalidated")
    reason = short_note(args.reason, "reason")
    event = {
        "event": "invalidate",
        "run_id": args.run_id,
        "invalidated_at": utc_now(),
        "reason": reason,
    }
    append_event(history_path(args), event)
    return {"run_id": args.run_id, "status": "invalidated", "reason": reason}


def command_runs(args: argparse.Namespace) -> dict[str, Any]:
    if not 1 <= args.limit <= 100:
        raise CalibrationError("limit must be between 1 and 100")
    runs = reconstruct(load_events(history_path(args)))
    ordered = sorted(
        runs.values(), key=lambda run: run.get("forecast_at", ""), reverse=True
    )
    items = []
    for run in ordered[: args.limit]:
        if run.get("invalidate"):
            status = "invalidated"
        elif run.get("finish"):
            status = run["finish"].get("outcome", "finished")
        elif run.get("start"):
            status = "active"
        else:
            status = "forecast"
        items.append(
            {
                "run_id": run["run_id"],
                "task_class": run.get("task_class"),
                "forecast_at": run.get("forecast_at"),
                "status": status,
                "branch": run.get("start", {}).get("branch"),
                "token_usage_reconciled": bool(run.get("reconcile")),
                "actual_file_count": (
                    len(run.get("finish", {}).get("actual_files"))
                    if run.get("finish", {}).get("actual_files") is not None
                    else None
                ),
                "invalidation_reason": run.get("invalidate", {}).get("reason"),
                "control_action": unresolved_control(run),
                "reforecast_count": len(run.get("reforecasts", [])),
                "calibration_exclusion": calibration_exclusion(run),
            }
        )
    return {"runs": items}


def audit_summary(args: argparse.Namespace) -> dict[str, Any]:
    """Read-only recovery report; it never appends adjudications."""
    runs = reconstruct(load_events(history_path(args)))
    counts: dict[str, int] = {}
    candidates: list[dict[str, Any]] = []
    for run in runs.values():
        finish = run.get("finish")
        if run.get("invalidate"):
            status = "invalidated"
        elif finish:
            status = finish.get("outcome", "finished")
        elif run.get("start"):
            status = "active"
        else:
            status = "forecast"
        counts[status] = counts.get(status, 0) + 1
        reasons: list[str] = []
        if finish and finish.get("outcome") == "completed" and not run.get("reconcile"):
            reasons.append("completed_without_reconciliation")
        if run.get("reconcile", {}).get("measurement_status") == "unavailable":
            reasons.append("unavailable_measurement")
        if run.get("reconcile", {}).get("measurement_version", 1) < MEASUREMENT_VERSION:
            reasons.append("legacy_reconciliation")
        if run.get("start") and not finish:
            reasons.append("unresolved_started_run")
        if reasons:
            candidates.append({"run_id": run["run_id"], "reasons": reasons})
    return {
        "dry_run": True,
        "counts": counts,
        "recovery_candidate_total": len(candidates),
        "recovery_counts": {
            reason: sum(reason in item["reasons"] for item in candidates)
            for reason in sorted({reason for item in candidates for reason in item["reasons"]})
        },
        "recovery_candidates": candidates[:20],
        "note": "No historical outcome or measurement was changed.",
    }


def backtest(runs: list[dict[str, Any]], metric: str, task_class: str) -> dict[str, Any]:
    """Chronological comparison of the current global method and class correction."""
    ordered = sorted(runs, key=lambda run: run["finish"]["finished_at"])
    results: dict[str, list[float]] = {"existing": [], "class_correction": []}
    covered: dict[str, int] = {"existing": 0, "class_correction": 0}
    for index, target in enumerate(ordered):
        prior = ordered[:index]
        global_ratios = observations(prior, metric)
        class_prior = [
            run for run in prior
            if normalize_task_class(run.get("task_class")) == normalize_task_class(task_class)
        ]
        class_ratios = observations(class_prior, metric)
        if not global_ratios:
            continue
        raw_key = {
            "time": "forecast_time_minutes",
            "tokens": "forecast_tokens",
        }.get(metric)
        if not raw_key or not target.get("finish"):
            continue
        actual_values = observations([target], metric)
        if not actual_values:
            continue
        actual = actual_values[0] * midpoint(target[raw_key])
        methods = {
            "existing": global_ratios,
            "class_correction": class_ratios if len(class_ratios) >= 3 else global_ratios,
        }
        for name, ratios in methods.items():
            if len(ratios) < 5:
                low = high = midpoint(target[raw_key])
            else:
                low = midpoint(target[raw_key]) * quantile(ratios, 0.2)
                high = midpoint(target[raw_key]) * quantile(ratios, 0.8)
            midpoint_error = abs(midpoint(target[raw_key]) * statistics.median(ratios) - actual)
            results[name].append(midpoint_error)
            covered[name] += int(low <= actual <= high)
    return {
        name: {
            "sample_count": len(values),
            "midpoint_error": round(statistics.mean(values), 3) if values else None,
            "interval_coverage": round(covered[name] / len(values), 3) if values else None,
        }
        for name, values in results.items()
    }


def command_stats(args: argparse.Namespace) -> dict[str, Any]:
    reconciled = reconcile_pending(args)
    all_runs = reconstruct(load_events(history_path(args)))
    runs = completed_runs(args)
    selected, source = select_runs(runs, args.task_class)
    planned_precision: list[float] = []
    planned_recall: list[float] = []
    for run in selected:
        planned = set(run.get("expected_files", []) + run.get("possible_files", []))
        actual = set(run["finish"].get("actual_files", []))
        overlap = len(planned & actual)
        if planned:
            planned_precision.append(overlap / len(planned))
        if actual:
            planned_recall.append(overlap / len(actual))
    return {
        "reconciled_runs": reconciled,
        "invalidated_runs": sum(
            bool(run.get("invalidate")) for run in all_runs.values()
        ),
        "deviation_excluded_runs": sum(
            bool(calibration_exclusion(run))
            and run.get("finish", {}).get("outcome") == "completed"
            for run in all_runs.values()
        ),
        "calibration_source": source,
        "completed_runs": len(selected),
        "time": metric_summary(selected, "time"),
        "tokens": metric_summary(selected, "tokens"),
        "aggregate_tokens": metric_summary(selected, "aggregate_tokens"),
        "files": metric_summary(selected, "files"),
        "diff_lines": metric_summary(selected, "diff"),
        "planned_path_precision_median": round(statistics.median(planned_precision), 3)
        if planned_precision
        else None,
        "planned_path_recall_median": round(statistics.median(planned_recall), 3)
        if planned_recall
        else None,
        "backtest": {
            "target_coverage": 0.8,
            "time": backtest(runs, "time", args.task_class),
            "tokens": backtest(runs, "tokens", args.task_class),
        },
    }


def bounded_pair(parser: argparse.ArgumentParser, low: str, high: str) -> None:
    parser.add_argument(low, type=int, required=True)
    parser.add_argument(high, type=int, required=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument(
        "--state-dir", help="override the private calibration state directory"
    )
    commands = root.add_subparsers(dest="command", required=True)

    forecast = commands.add_parser("forecast")
    forecast.add_argument("--task-class", default="general")
    bounded_pair(forecast, "--time-low", "--time-high")
    bounded_pair(forecast, "--tokens-low", "--tokens-high")
    forecast.add_argument("--aggregate-tokens-low", type=int)
    forecast.add_argument("--aggregate-tokens-high", type=int)
    forecast.add_argument("--work-units", type=int, default=1)
    forecast.add_argument("--implementation-agents", type=int, default=1)
    forecast.add_argument("--reviewers", type=int, default=0)
    forecast.add_argument("--max-correction-passes", type=int, default=1)
    forecast.add_argument("--environment-assumption", action="append", default=[])
    forecast.add_argument("--expected-file", action="append", default=[])
    forecast.add_argument("--possible-file", action="append", default=[])
    forecast.add_argument("--add-low", type=int, default=0)
    forecast.add_argument("--add-high", type=int, default=0)
    forecast.add_argument("--delete-low", type=int, default=0)
    forecast.add_argument("--delete-high", type=int, default=0)
    forecast.add_argument("--sessions-dir")
    forecast.set_defaults(handler=command_forecast)

    for name, handler in (
        ("start", command_start),
        ("pause", command_pause),
        ("resume", command_resume),
    ):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        if name == "start":
            command.add_argument("--repo", default=".")
            command.add_argument("--allow-dirty", action="store_true")
            command.add_argument("--allow-protected-branch", action="store_true")
            command.add_argument("--execution-session-id")
            command.add_argument("--execution-turn-id")
        command.set_defaults(handler=handler)

    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("run_id")
    checkpoint.add_argument("--completed-units", type=int, required=True)
    checkpoint.add_argument("--correction-passes", type=int, default=0)
    checkpoint.add_argument("--root-tokens", type=int)
    checkpoint.add_argument("--aggregate-tokens", type=int)
    checkpoint.add_argument("--implementation-agents", type=int)
    checkpoint.add_argument("--reviewers", type=int)
    checkpoint.add_argument(
        "--trigger", action="append", choices=sorted(CHECKPOINT_TRIGGERS), default=[]
    )
    checkpoint.add_argument("--reason")
    checkpoint.set_defaults(handler=command_checkpoint)

    classify = commands.add_parser("classify")
    classify.add_argument("run_id")
    classify.add_argument(
        "--classification", choices=sorted(FINDING_CLASSES), required=True
    )
    classify.add_argument("--summary", required=True)
    classify.set_defaults(handler=command_classify)

    reforecast = commands.add_parser("reforecast")
    reforecast.add_argument("run_id")
    bounded_pair(reforecast, "--remaining-time-low", "--remaining-time-high")
    bounded_pair(reforecast, "--remaining-tokens-low", "--remaining-tokens-high")
    reforecast.add_argument("--root-tokens", type=int)
    reforecast.add_argument("--aggregate-tokens", type=int)
    reforecast.add_argument("--remaining-aggregate-tokens-low", type=int)
    reforecast.add_argument("--remaining-aggregate-tokens-high", type=int)
    reforecast.add_argument("--work-units", type=int)
    reforecast.add_argument("--implementation-agents", type=int)
    reforecast.add_argument("--reviewers", type=int)
    reforecast.add_argument("--max-correction-passes", type=int)
    reforecast.add_argument(
        "--deviation", choices=sorted(DEVIATION_CLASSES), required=True
    )
    reforecast.add_argument("--reason", required=True)
    reforecast.add_argument("--approved", action="store_true")
    reforecast.set_defaults(handler=command_reforecast)

    finish = commands.add_parser("finish")
    finish.add_argument("run_id")
    finish.add_argument("--repo", default=".")
    finish.add_argument(
        "--outcome",
        choices=("completed", "declined", "superseded", "blocked", "unknown", "abandoned"),
        default="completed",
    )
    finish.add_argument("--aggregate-tokens", type=int)
    finish.set_defaults(handler=command_finish)

    reconcile = commands.add_parser("reconcile")
    reconcile.set_defaults(handler=command_reconcile)

    runs = commands.add_parser("runs")
    runs.add_argument("--limit", type=int, default=20)
    runs.set_defaults(handler=command_runs)

    audit = commands.add_parser("audit")
    audit.set_defaults(handler=lambda args: audit_summary(args))

    invalidate = commands.add_parser("invalidate")
    invalidate.add_argument("run_id")
    invalidate.add_argument("--reason", required=True)
    invalidate.set_defaults(handler=command_invalidate)

    stats = commands.add_parser("stats")
    stats.add_argument("--task-class", default="general")
    stats.set_defaults(handler=command_stats)
    return root


def validate_ranges(args: argparse.Namespace) -> None:
    pairs: list[tuple[str, str]] = []
    optional_pairs: list[tuple[str, str]] = []
    if args.command == "forecast":
        pairs = [
            ("time_low", "time_high"),
            ("tokens_low", "tokens_high"),
            ("add_low", "add_high"),
            ("delete_low", "delete_high"),
        ]
        optional_pairs = [("aggregate_tokens_low", "aggregate_tokens_high")]
        if args.work_units < 1 or args.implementation_agents < 1:
            raise CalibrationError(
                "work units and implementation agents must be positive"
            )
        if args.reviewers < 0 or args.max_correction_passes < 0:
            raise CalibrationError(
                "reviewers and correction-pass cap cannot be negative"
            )
        if args.time_low == 0 or args.tokens_low == 0:
            raise CalibrationError(
                "time and token lower bounds must be greater than zero"
            )
    elif args.command == "reforecast":
        pairs = [
            ("remaining_time_low", "remaining_time_high"),
            ("remaining_tokens_low", "remaining_tokens_high"),
        ]
        optional_pairs = [
            ("remaining_aggregate_tokens_low", "remaining_aggregate_tokens_high")
        ]
        if args.work_units is not None and args.work_units < 1:
            raise CalibrationError("work units must be positive")
        if args.implementation_agents is not None and args.implementation_agents < 1:
            raise CalibrationError("implementation agents must be positive")
        if args.reviewers is not None and args.reviewers < 0:
            raise CalibrationError("reviewers cannot be negative")
        if args.max_correction_passes is not None and args.max_correction_passes < 0:
            raise CalibrationError("correction-pass cap cannot be negative")
    for low_name, high_name in pairs:
        low, high = getattr(args, low_name), getattr(args, high_name)
        if low < 0 or high < low:
            raise CalibrationError(
                f"invalid range: --{low_name.replace('_', '-')} / "
                f"--{high_name.replace('_', '-')}"
            )
    for low_name, high_name in optional_pairs:
        low, high = getattr(args, low_name), getattr(args, high_name)
        if (low is None) != (high is None):
            raise CalibrationError(
                f"both --{low_name.replace('_', '-')} and "
                f"--{high_name.replace('_', '-')} are required together"
            )
        if low is not None and (low < 0 or high < low):
            raise CalibrationError(
                f"invalid range: --{low_name.replace('_', '-')} / "
                f"--{high_name.replace('_', '-')}"
            )
    for name in ("root_tokens", "aggregate_tokens"):
        value = getattr(args, name, None)
        if value is not None and value < 0:
            raise CalibrationError(f"--{name.replace('_', '-')} cannot be negative")


def main() -> int:
    args = parser().parse_args()
    try:
        validate_ranges(args)
        result = args.handler(args)
    except CalibrationError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
