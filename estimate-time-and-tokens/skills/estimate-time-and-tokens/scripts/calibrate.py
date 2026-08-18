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
ESTIMATOR_VERSION = "1.2.0"
DEFAULT_STATE_DIR = Path.home() / ".codex" / "state" / "estimate-time-and-tokens"
DEFAULT_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
PROTECTED_BRANCHES = {"main", "master", "prod", "production", "stage", "staging"}


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
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CalibrationError(f"invalid history JSON on line {line_number}: {exc}") from exc
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
    return runs


def session_file(sessions_dir: Path) -> Path | None:
    thread_id = os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_SESSION_ID")
    if not thread_id or not sessions_dir.exists():
        return None
    matches = list(sessions_dir.rglob(f"*{thread_id}*.jsonl"))
    return matches[0].resolve() if len(matches) == 1 else None


def token_usage(payload: dict[str, Any]) -> dict[str, int] | None:
    usage = (payload.get("info") or {}).get("last_token_usage")
    if not isinstance(usage, dict) or not isinstance(usage.get("total_tokens"), int):
        return None
    return {
        key: int(usage.get(key, 0))
        for key in (
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
            "total_tokens",
        )
    }


def latest_usage(path: Path) -> dict[str, int] | None:
    if not path.exists():
        return None
    usage: dict[str, int] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = envelope.get("payload") or {}
        if envelope.get("type") == "event_msg" and payload.get("type") == "token_count":
            usage = token_usage(payload) or usage
    return usage


def last_usage_for_turn(path: Path, after: str) -> dict[str, int] | None:
    if not path.exists():
        return None
    after_time = parse_time(after)
    last_usage: dict[str, int] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError:
            continue
        timestamp = envelope.get("timestamp")
        if not timestamp or parse_time(timestamp) < after_time:
            continue
        payload = envelope.get("payload") or {}
        payload_type = payload.get("type")
        if envelope.get("type") == "event_msg" and payload_type == "token_count":
            last_usage = token_usage(payload) or last_usage
        if envelope.get("type") == "event_msg" and payload_type == "task_complete":
            return last_usage
    return None


def reconcile_pending(args: argparse.Namespace) -> int:
    path = history_path(args)
    runs = reconstruct(load_events(path))
    reconciled = 0
    for run in runs.values():
        finish = run.get("finish")
        if (
            not finish
            or finish.get("outcome") != "completed"
            or run.get("reconcile")
            or run.get("invalidate")
        ):
            continue
        stored_session = run.get("session_file")
        if not stored_session:
            continue
        usage = last_usage_for_turn(Path(stored_session), run["forecast_at"])
        if usage is None:
            continue
        append_event(
            path,
            {
                "event": "reconcile",
                "run_id": run["run_id"],
                "reconciled_at": utc_now(),
                "token_metric": "last_token_usage",
                "token_usage": usage,
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


def completed_runs(args: argparse.Namespace) -> list[dict[str, Any]]:
    runs = reconstruct(load_events(history_path(args)))
    completed = [
        run
        for run in runs.values()
        if run.get("finish", {}).get("outcome") == "completed" and not run.get("invalidate")
    ]
    return sorted(completed, key=lambda run: run["finish"]["finished_at"])[-20:]


def observations(runs: list[dict[str, Any]], metric: str) -> list[float]:
    ratios: list[float] = []
    for run in runs:
        if metric == "time":
            predicted = midpoint(run["forecast_time_minutes"])
            actual = run["finish"].get("active_elapsed_seconds", 0) / 60
        elif metric == "tokens":
            if not run.get("reconcile"):
                continue
            predicted = midpoint(run["forecast_tokens"])
            actual = run["reconcile"]["token_usage"]["total_tokens"]
        elif metric == "files":
            predicted = len(set(run.get("expected_files", []) + run.get("possible_files", [])))
            actual = len(run["finish"].get("actual_files", []))
        elif metric == "diff":
            additions = run.get("forecast_additions", [0, 0])
            deletions = run.get("forecast_deletions", [0, 0])
            predicted = midpoint(additions) + midpoint(deletions)
            actual = run["finish"].get("actual_additions", 0) + run["finish"].get("actual_deletions", 0)
        else:
            raise CalibrationError(f"unknown metric: {metric}")
        if predicted > 0 and actual >= 0:
            ratios.append(actual / predicted)
    return ratios


def select_runs(runs: list[dict[str, Any]], task_class: str) -> tuple[list[dict[str, Any]], str]:
    matching = [run for run in runs if run.get("task_class") == task_class]
    return (matching, "task_class") if len(matching) >= 5 else (runs, "global")


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


def calibrated_bounds(raw: list[int], summary: dict[str, Any], metric: str) -> list[int]:
    if not summary["applied"]:
        return raw
    center = midpoint(raw)
    return round_bounds(
        [center * summary["p20_factor"], center * summary["p80_factor"]], metric
    )


def token_floor_bounds(raw: list[int], observed_total: int | None) -> list[int]:
    if not observed_total:
        return raw
    unit = 1000 if observed_total >= 10000 else 500
    headroom = math.ceil((observed_total * 1.2) / unit) * unit
    return [max(raw[0], observed_total), max(raw[1], headroom)]


def normalize_relative_paths(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise CalibrationError(f"planned paths must be repository-relative: {value}")
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
    scope = {
        "files": metric_summary(selected, "files"),
        "diff_lines": metric_summary(selected, "diff"),
    }
    raw_time = [args.time_low, args.time_high]
    submitted_tokens = [args.tokens_low, args.tokens_high]
    run_id = uuid.uuid4().hex[:12]
    sessions_dir = Path(args.sessions_dir).expanduser() if args.sessions_dir else DEFAULT_SESSIONS_DIR
    current_session = session_file(sessions_dir)
    current_usage = latest_usage(current_session) if current_session else None
    token_floor = current_usage["total_tokens"] if current_usage else None
    raw_tokens = token_floor_bounds(submitted_tokens, token_floor)
    event = {
        "event": "forecast",
        "run_id": run_id,
        "estimator_version": ESTIMATOR_VERSION,
        "forecast_at": utc_now(),
        "task_class": args.task_class,
        "forecast_time_minutes": raw_time,
        "forecast_tokens": raw_tokens,
        "submitted_forecast_tokens": submitted_tokens,
        "observed_token_floor": token_floor,
        "expected_files": normalize_relative_paths(args.expected_file),
        "possible_files": normalize_relative_paths(args.possible_file),
        "forecast_additions": [args.add_low, args.add_high],
        "forecast_deletions": [args.delete_low, args.delete_high],
        "session_file": str(current_session) if current_session else None,
    }
    append_event(history_path(args), event)
    calibrated_tokens = calibrated_bounds(raw_tokens, token_summary, "tokens")
    if token_floor:
        calibrated_tokens = [
            max(calibrated_tokens[0], token_floor),
            max(calibrated_tokens[1], token_floor),
        ]
    return {
        "run_id": run_id,
        "reconciled_prior_runs": reconciled,
        "calibration_source": source,
        "time_minutes": {
            "raw": raw_time,
            "calibrated": calibrated_bounds(raw_time, time_summary, "time"),
            **time_summary,
        },
        "tokens": {
            "submitted": submitted_tokens,
            "baseline": raw_tokens,
            "calibrated": calibrated_tokens,
            "observed_floor": token_floor,
            "metric": "last_token_usage.total_tokens",
            **token_summary,
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
        "git_scope_reason": None if identity["clean"] else "repository was dirty at start",
    }
    append_event(history_path(args), event)
    return {key: value for key, value in event.items() if key not in {"event", "run_id"}}


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


def command_finish(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    require_valid_run(run)
    if run.get("finish"):
        raise CalibrationError("run is already finished")
    finished_at = utc_now()
    finish: dict[str, Any] = {
        "event": "finish",
        "run_id": args.run_id,
        "finished_at": finished_at,
        "outcome": args.outcome,
        "active_elapsed_seconds": active_elapsed(run["events"], finished_at),
        "actual_files": [],
        "actual_additions": 0,
        "actual_deletions": 0,
    }
    if not run.get("start"):
        if args.outcome == "completed":
            raise CalibrationError("a completed run must be started before it is finished")
        append_event(history_path(args), finish)
        return {
            "finished_at": finished_at,
            "outcome": args.outcome,
            "active_elapsed_seconds": 0,
            "actual_files": [],
            "actual_additions": 0,
            "actual_deletions": 0,
            "token_reconciliation": "excluded",
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
        "token_reconciliation": "pending" if args.outcome == "completed" else "excluded",
    }


def command_reconcile(args: argparse.Namespace) -> dict[str, Any]:
    return {"reconciled_runs": reconcile_pending(args)}


def command_invalidate(args: argparse.Namespace) -> dict[str, Any]:
    run = find_run(args)
    if run.get("invalidate"):
        raise CalibrationError("run is already invalidated")
    reason = args.reason.strip()
    if not reason or len(reason) > 200 or "\n" in reason:
        raise CalibrationError("reason must be a single non-empty line of at most 200 characters")
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
    ordered = sorted(runs.values(), key=lambda run: run.get("forecast_at", ""), reverse=True)
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
                "actual_file_count": len(run.get("finish", {}).get("actual_files", [])),
                "invalidation_reason": run.get("invalidate", {}).get("reason"),
            }
        )
    return {"runs": items}


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
        "invalidated_runs": sum(bool(run.get("invalidate")) for run in all_runs.values()),
        "calibration_source": source,
        "completed_runs": len(selected),
        "time": metric_summary(selected, "time"),
        "tokens": metric_summary(selected, "tokens"),
        "files": metric_summary(selected, "files"),
        "diff_lines": metric_summary(selected, "diff"),
        "planned_path_precision_median": round(statistics.median(planned_precision), 3)
        if planned_precision
        else None,
        "planned_path_recall_median": round(statistics.median(planned_recall), 3)
        if planned_recall
        else None,
    }


def bounded_pair(parser: argparse.ArgumentParser, low: str, high: str) -> None:
    parser.add_argument(low, type=int, required=True)
    parser.add_argument(high, type=int, required=True)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--state-dir", help="override the private calibration state directory")
    commands = root.add_subparsers(dest="command", required=True)

    forecast = commands.add_parser("forecast")
    forecast.add_argument("--task-class", default="general")
    bounded_pair(forecast, "--time-low", "--time-high")
    bounded_pair(forecast, "--tokens-low", "--tokens-high")
    forecast.add_argument("--expected-file", action="append", default=[])
    forecast.add_argument("--possible-file", action="append", default=[])
    forecast.add_argument("--add-low", type=int, default=0)
    forecast.add_argument("--add-high", type=int, default=0)
    forecast.add_argument("--delete-low", type=int, default=0)
    forecast.add_argument("--delete-high", type=int, default=0)
    forecast.add_argument("--sessions-dir")
    forecast.set_defaults(handler=command_forecast)

    for name, handler in (("start", command_start), ("pause", command_pause), ("resume", command_resume)):
        command = commands.add_parser(name)
        command.add_argument("run_id")
        if name == "start":
            command.add_argument("--repo", default=".")
            command.add_argument("--allow-dirty", action="store_true")
            command.add_argument("--allow-protected-branch", action="store_true")
        command.set_defaults(handler=handler)

    finish = commands.add_parser("finish")
    finish.add_argument("run_id")
    finish.add_argument("--repo", default=".")
    finish.add_argument("--outcome", choices=("completed", "blocked", "abandoned"), default="completed")
    finish.set_defaults(handler=command_finish)

    reconcile = commands.add_parser("reconcile")
    reconcile.set_defaults(handler=command_reconcile)

    runs = commands.add_parser("runs")
    runs.add_argument("--limit", type=int, default=20)
    runs.set_defaults(handler=command_runs)

    invalidate = commands.add_parser("invalidate")
    invalidate.add_argument("run_id")
    invalidate.add_argument("--reason", required=True)
    invalidate.set_defaults(handler=command_invalidate)

    stats = commands.add_parser("stats")
    stats.add_argument("--task-class", default="general")
    stats.set_defaults(handler=command_stats)
    return root


def validate_ranges(args: argparse.Namespace) -> None:
    if args.command != "forecast":
        return
    for low_name, high_name in (
        ("time_low", "time_high"),
        ("tokens_low", "tokens_high"),
        ("add_low", "add_high"),
        ("delete_low", "delete_high"),
    ):
        low, high = getattr(args, low_name), getattr(args, high_name)
        if low < 0 or high < low:
            raise CalibrationError(f"invalid range: --{low_name.replace('_', '-')} / --{high_name.replace('_', '-')}")
    if args.time_low == 0 or args.tokens_low == 0:
        raise CalibrationError("time and token lower bounds must be greater than zero")


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
