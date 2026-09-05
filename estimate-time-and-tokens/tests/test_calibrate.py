import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "estimate-time-and-tokens"
    / "scripts"
    / "calibrate.py"
)
SPEC = importlib.util.spec_from_file_location("calibrate", SCRIPT)
calibrate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(calibrate)


class CalibrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path.cwd() / ".scratch" / "estimate-time-and-tokens-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=scratch)
        cls.root = Path(cls.temporary.name)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def state_args(self, name):
        return argparse.Namespace(state_dir=str(self.root / name))

    def test_reconcile_uses_last_usage_before_first_task_complete(self):
        args = self.state_args("reconcile")
        session = self.root / "session.jsonl"
        envelopes = [
            {
                "timestamp": "2026-01-01T00:00:01Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 50,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 10,
                            "total_tokens": 120,
                        },
                        "total_token_usage": {"total_tokens": 9999},
                    },
                },
            },
            {
                "timestamp": "2026-01-01T00:00:02Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 200,
                            "cached_input_tokens": 100,
                            "output_tokens": 40,
                            "reasoning_output_tokens": 25,
                            "total_tokens": 240,
                        }
                    },
                },
            },
            {
                "timestamp": "2026-01-01T00:00:03Z",
                "type": "event_msg",
                "payload": {"type": "task_complete"},
            },
            {
                "timestamp": "2026-01-01T00:00:04Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"total_tokens": 500}},
                },
            },
        ]
        session.write_text("".join(json.dumps(item) + "\n" for item in envelopes))
        path = calibrate.history_path(args)
        calibrate.append_event(
            path,
            {
                "event": "forecast",
                "run_id": "run-one",
                "forecast_at": "2026-01-01T00:00:00Z",
                "forecast_time_minutes": [10, 20],
                "forecast_tokens": [100, 200],
                "task_class": "test",
                "session_file": str(session),
            },
        )
        calibrate.append_event(
            path,
            {
                "event": "finish",
                "run_id": "run-one",
                "finished_at": "2026-01-01T00:00:02Z",
                "outcome": "completed",
                "active_elapsed_seconds": 600,
            },
        )

        self.assertEqual(calibrate.reconcile_pending(args), 1)
        run = calibrate.reconstruct(calibrate.load_events(path))["run-one"]
        self.assertEqual(run["reconcile"]["token_usage"]["total_tokens"], 240)
        self.assertEqual(run["reconcile"]["token_metric"], "last_token_usage")

    def test_forecast_applies_calibration_after_five_runs(self):
        args = self.state_args("forecast")
        path = calibrate.history_path(args)
        for index in range(5):
            run_id = f"run-{index}"
            calibrate.append_event(
                path,
                {
                    "event": "forecast",
                    "run_id": run_id,
                    "forecast_at": f"2026-01-0{index + 1}T00:00:00Z",
                    "forecast_time_minutes": [10, 20],
                    "forecast_tokens": [10000, 20000],
                    "forecast_additions": [10, 20],
                    "forecast_deletions": [0, 0],
                    "expected_files": ["one.py"],
                    "possible_files": [],
                    "task_class": "feature",
                    "session_file": None,
                },
            )
            calibrate.append_event(
                path,
                {
                    "event": "finish",
                    "run_id": run_id,
                    "finished_at": f"2026-01-0{index + 1}T01:00:00Z",
                    "outcome": "completed",
                    "active_elapsed_seconds": 1800,
                    "actual_files": ["one.py", "two.py"],
                    "actual_additions": 30,
                    "actual_deletions": 0,
                },
            )
            calibrate.append_event(
                path,
                {
                    "event": "reconcile",
                    "run_id": run_id,
                    "reconciled_at": f"2026-01-0{index + 1}T01:01:00Z",
                    "measurement_version": 2,
                    "token_metric": "cumulative_counter_delta",
                    "measurement_status": "available",
                    "token_usage": {"total_tokens": 45000},
                },
            )
        forecast_args = argparse.Namespace(
            state_dir=args.state_dir,
            task_class="feature",
            time_low=10,
            time_high=20,
            tokens_low=10000,
            tokens_high=20000,
            expected_file=["src/change.py"],
            possible_file=["tests/test_change.py"],
            add_low=20,
            add_high=40,
            delete_low=0,
            delete_high=10,
            sessions_dir=str(self.root / "missing-sessions"),
        )

        result = calibrate.command_forecast(forecast_args)

        self.assertEqual(result["calibration_source"], "task_class")
        self.assertEqual(result["time_minutes"]["calibrated"], [30, 30])
        self.assertEqual(result["tokens"]["calibrated"], [45000, 45000])
        self.assertEqual(
            result["code_scope"]["historical_factors"]["files"]["median_factor"], 2
        )

    def test_forecast_adds_incremental_tokens_to_current_context(self):
        args = self.state_args("floor")
        sessions = self.root / "sessions"
        sessions.mkdir()
        session = sessions / "rollout-thread-for-test.jsonl"
        session.write_text(
            json.dumps(
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {"total_tokens": 8020000},
                            "last_token_usage": {"input_tokens": 120000, "total_tokens": 50000},
                        },
                    },
                }
            )
            + "\n"
        )
        forecast_args = argparse.Namespace(
            state_dir=args.state_dir,
            task_class="feature",
            time_low=10,
            time_high=20,
            tokens_low=20000,
            tokens_high=40000,
            expected_file=[],
            possible_file=[],
            add_low=0,
            add_high=0,
            delete_low=0,
            delete_high=0,
            sessions_dir=str(sessions),
        )

        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "thread-for-test"}):
            result = calibrate.command_forecast(forecast_args)

        self.assertEqual(result["tokens"]["observed_floor"], 120000)
        self.assertEqual(result["tokens"]["incremental"], [20000, 40000])
        self.assertEqual(result["tokens"]["final_context"], [140000, 160000])
        self.assertEqual(result["tokens"]["calibrated"], [140000, 160000])

    def test_token_calibration_learns_incremental_work_not_existing_context(self):
        run = {
            "submitted_forecast_tokens": [20000, 40000],
            "forecast_tokens": [120000, 140000],
            "observed_token_floor": 100000,
            "reconcile": {"token_usage": {"total_tokens": 160000}},
        }

        self.assertEqual(calibrate.observations([run], "tokens"), [2.0])

    def test_canary_checkpoint_requires_reforecast_before_completion(self):
        args = self.state_args("checkpoint")
        path = calibrate.history_path(args)
        calibrate.append_event(
            path,
            {
                "event": "forecast",
                "run_id": "controlled-run",
                "forecast_at": calibrate.utc_now(),
                "forecast_time_minutes": [10, 100],
                "forecast_tokens": [100, 300],
                "forecast_aggregate_tokens": [200, 600],
                "work_units": 4,
                "implementation_agents": 1,
                "reviewers": 1,
                "max_correction_passes": 1,
                "task_class": "feature",
                "session_file": None,
            },
        )
        calibrate.append_event(
            path,
            {
                "event": "start",
                "run_id": "controlled-run",
                "started_at": calibrate.utc_now(),
                "git_scope_available": False,
            },
        )
        checkpoint_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="controlled-run",
            completed_units=1,
            correction_passes=0,
            root_tokens=150,
            aggregate_tokens=250,
            implementation_agents=1,
            reviewers=1,
            trigger=[],
            reason="first repeated unit complete",
        )

        checkpoint = calibrate.command_checkpoint(checkpoint_args)

        self.assertEqual(checkpoint["control_action"], "reforecast-required")
        self.assertIn("canary-checkpoint", checkpoint["triggers"])
        finish_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="controlled-run",
            repo=".",
            outcome="completed",
            aggregate_tokens=300,
        )
        with self.assertRaisesRegex(calibrate.CalibrationError, "unresolved"):
            calibrate.command_finish(finish_args)

        reforecast_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="controlled-run",
            remaining_time_low=10,
            remaining_time_high=20,
            remaining_tokens_low=20,
            remaining_tokens_high=40,
            root_tokens=150,
            aggregate_tokens=250,
            remaining_aggregate_tokens_low=40,
            remaining_aggregate_tokens_high=80,
            work_units=None,
            implementation_agents=None,
            reviewers=None,
            max_correction_passes=None,
            deviation="canary-variance",
            reason="canary confirms the remaining rate",
            approved=False,
        )
        reforecast = calibrate.command_reforecast(reforecast_args)

        self.assertEqual(reforecast["control_action"], "continue")
        self.assertEqual(reforecast["projected_root_tokens"], [170, 190])
        self.assertEqual(
            calibrate.current_envelope(calibrate.find_run(reforecast_args))[
                "root_tokens"
            ],
            [170, 190],
        )
        finished = calibrate.command_finish(finish_args)
        self.assertEqual(finished["outcome"], "completed")
        self.assertEqual(finished["actual_aggregate_tokens"], 300)

    def test_checkpoint_and_reforecast_use_incremental_tokens_after_large_history(self):
        args = self.state_args("incremental-budget")
        start_at = calibrate.utc_now()
        before = (calibrate.parse_time(start_at) - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        after = (calibrate.parse_time(start_at) + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        session = self.root / "incremental-budget.jsonl"
        def usage(total):
            return {"input_tokens": total, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": total}
        session.write_text("".join(json.dumps(row) + "\n" for row in [
            {"timestamp": before, "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage(8_000_000)}}},
            {"timestamp": after, "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage(8_020_000)}}},
        ]))
        path = calibrate.history_path(args)
        calibrate.append_event(path, {"event": "forecast", "run_id": "incremental", "forecast_at": before, "forecast_time_minutes": [10, 20], "forecast_tokens": [8_020_000, 8_040_000], "submitted_forecast_tokens": [20_000, 40_000], "task_class": "feature", "session_file": str(session), "work_units": 1})
        calibrate.append_event(path, {"event": "start", "run_id": "incremental", "started_at": start_at, "session_file": str(session), "execution_token_baseline": 8_000_000})
        checkpoint_args = argparse.Namespace(state_dir=args.state_dir, run_id="incremental", completed_units=0, correction_passes=0, root_tokens=None, aggregate_tokens=None, implementation_agents=1, reviewers=0, trigger=[], reason=None)
        checkpoint = calibrate.command_checkpoint(checkpoint_args)
        self.assertEqual(checkpoint["root_token_usage"], 20_000)
        self.assertEqual(checkpoint["control_action"], "continue")
        reforecast_args = argparse.Namespace(state_dir=args.state_dir, run_id="incremental", remaining_time_low=5, remaining_time_high=10, remaining_tokens_low=10_000, remaining_tokens_high=20_000, root_tokens=None, aggregate_tokens=None, remaining_aggregate_tokens_low=None, remaining_aggregate_tokens_high=None, work_units=None, implementation_agents=None, reviewers=None, max_correction_passes=None, deviation="estimator-error", reason="incremental budget check", approved=False)
        reforecast = calibrate.command_reforecast(reforecast_args)
        self.assertEqual(reforecast["projected_root_tokens"], [30_000, 40_000])
        self.assertEqual(reforecast["control_action"], "continue")

    def test_scope_deviation_is_retained_but_excluded_from_calibration(self):
        args = self.state_args("deviation")
        path = calibrate.history_path(args)
        calibrate.append_event(
            path,
            {
                "event": "forecast",
                "run_id": "expanded-run",
                "forecast_at": "2026-01-01T00:00:00Z",
                "forecast_time_minutes": [10, 20],
                "forecast_tokens": [10000, 20000],
                "task_class": "feature",
                "session_file": None,
            },
        )
        calibrate.append_event(
            path,
            {
                "event": "reforecast",
                "run_id": "expanded-run",
                "reforecast_at": "2026-01-01T00:10:00Z",
                "deviation": "workflow-expansion",
                "approval_state": "approved",
                "projected_total_time_minutes": [20, 40],
                "projected_root_tokens": [20000, 40000],
                "execution_model": {"reviewers": 2},
            },
        )
        calibrate.append_event(
            path,
            {
                "event": "finish",
                "run_id": "expanded-run",
                "finished_at": "2026-01-01T00:40:00Z",
                "outcome": "completed",
                "active_elapsed_seconds": 2400,
                "actual_files": [],
                "actual_additions": 0,
                "actual_deletions": 0,
            },
        )

        self.assertEqual(calibrate.completed_runs(args), [])
        stats = calibrate.command_stats(
            argparse.Namespace(state_dir=args.state_dir, task_class="feature")
        )
        self.assertEqual(stats["deviation_excluded_runs"], 1)

    def test_correction_cap_cannot_be_cleared_without_approval(self):
        args = self.state_args("approval")
        path = calibrate.history_path(args)
        calibrate.append_event(
            path,
            {
                "event": "forecast",
                "run_id": "approval-run",
                "forecast_at": calibrate.utc_now(),
                "forecast_time_minutes": [10, 100],
                "forecast_tokens": [100, 500],
                "work_units": 1,
                "max_correction_passes": 1,
                "task_class": "feature",
                "session_file": None,
            },
        )
        calibrate.append_event(
            path,
            {
                "event": "start",
                "run_id": "approval-run",
                "started_at": calibrate.utc_now(),
                "git_scope_available": False,
            },
        )
        checkpoint_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="approval-run",
            completed_units=0,
            correction_passes=2,
            root_tokens=120,
            aggregate_tokens=None,
            implementation_agents=1,
            reviewers=0,
            trigger=[],
            reason="second correction pass",
        )
        self.assertEqual(
            calibrate.command_checkpoint(checkpoint_args)["control_action"],
            "approval-required",
        )
        reforecast_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="approval-run",
            remaining_time_low=5,
            remaining_time_high=10,
            remaining_tokens_low=10,
            remaining_tokens_high=20,
            root_tokens=120,
            aggregate_tokens=None,
            remaining_aggregate_tokens_low=None,
            remaining_aggregate_tokens_high=None,
            work_units=None,
            implementation_agents=None,
            reviewers=None,
            max_correction_passes=None,
            deviation="estimator-error",
            reason="review requires another correction",
            approved=False,
        )

        pending = calibrate.command_reforecast(reforecast_args)

        self.assertTrue(pending["approval_required"])
        self.assertEqual(pending["control_action"], "stop-for-approval")
        reforecast_args.approved = True
        approved = calibrate.command_reforecast(reforecast_args)
        self.assertEqual(approved["control_action"], "continue")

    def test_required_finding_requires_reforecast(self):
        args = self.state_args("classify")
        path = calibrate.history_path(args)
        calibrate.append_event(
            path,
            {
                "event": "forecast",
                "run_id": "finding-run",
                "forecast_at": calibrate.utc_now(),
                "forecast_time_minutes": [10, 20],
                "forecast_tokens": [100, 200],
                "task_class": "bugfix",
                "session_file": None,
            },
        )
        calibrate.append_event(
            path,
            {
                "event": "start",
                "run_id": "finding-run",
                "started_at": calibrate.utc_now(),
                "git_scope_available": False,
            },
        )
        classify_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="finding-run",
            classification="required-now",
            summary="breaks the accepted contract",
        )

        result = calibrate.command_classify(classify_args)

        self.assertEqual(result["control_action"], "reforecast-required")
        self.assertEqual(
            calibrate.unresolved_control(calibrate.find_run(classify_args)),
            "reforecast-required",
        )

    def test_active_elapsed_excludes_paused_interval(self):
        events = [
            {"event": "start", "started_at": "2026-01-01T00:00:00Z"},
            {"event": "pause", "paused_at": "2026-01-01T00:10:00Z"},
            {"event": "resume", "resumed_at": "2026-01-01T00:20:00Z"},
        ]
        self.assertEqual(
            calibrate.active_elapsed(events, "2026-01-01T00:25:00Z"),
            900,
        )

    def test_start_rejects_protected_dirty_and_changed_branches(self):
        args = self.state_args("start-guards")
        path = calibrate.history_path(args)
        calibrate.append_event(
            path,
            {
                "event": "forecast",
                "run_id": "guarded-run",
                "forecast_at": "2026-01-01T00:00:00Z",
                "forecast_time_minutes": [10, 20],
                "forecast_tokens": [10000, 20000],
                "task_class": "feature",
                "session_file": None,
            },
        )
        repo = self.root / "guard-repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"], check=True
        )
        (repo / "tracked.txt").write_text("first\n")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
        start_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="guarded-run",
            repo=str(repo),
            allow_dirty=False,
            allow_protected_branch=False,
        )

        with self.assertRaisesRegex(calibrate.CalibrationError, "protected branch"):
            calibrate.command_start(start_args)

        subprocess.run(["git", "-C", str(repo), "switch", "-qc", "feature"], check=True)
        (repo / "tracked.txt").write_text("dirty\n")
        with self.assertRaisesRegex(calibrate.CalibrationError, "dirty repository"):
            calibrate.command_start(start_args)

        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "clean feature"], check=True
        )
        result = calibrate.command_start(start_args)
        self.assertEqual(result["branch"], "feature")

        subprocess.run(
            ["git", "-C", str(repo), "switch", "-qc", "other-feature"], check=True
        )
        finish_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="guarded-run",
            repo=str(repo),
            outcome="completed",
        )
        with self.assertRaisesRegex(calibrate.CalibrationError, "branch used at start"):
            calibrate.command_finish(finish_args)

    def test_invalidation_excludes_a_completed_run(self):
        args = self.state_args("invalidate")
        path = calibrate.history_path(args)
        calibrate.append_event(
            path,
            {
                "event": "forecast",
                "run_id": "bad-run",
                "forecast_at": "2026-01-01T00:00:00Z",
                "forecast_time_minutes": [10, 20],
                "forecast_tokens": [10000, 20000],
                "task_class": "feature",
                "session_file": None,
            },
        )
        calibrate.append_event(
            path,
            {
                "event": "finish",
                "run_id": "bad-run",
                "finished_at": "2026-01-01T01:00:00Z",
                "outcome": "completed",
                "active_elapsed_seconds": 3600,
                "actual_files": [],
                "actual_additions": 0,
                "actual_deletions": 0,
            },
        )
        calibrate.append_event(
            path,
            {
                "event": "reconcile",
                "run_id": "bad-run",
                "reconciled_at": "2026-01-01T01:01:00Z",
                "token_metric": "last_token_usage",
                "token_usage": {"total_tokens": 45000},
            },
        )
        invalidate_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="bad-run",
            reason="wrong-worktree",
        )

        result = calibrate.command_invalidate(invalidate_args)

        self.assertEqual(result["status"], "invalidated")
        self.assertEqual(calibrate.completed_runs(args), [])
        listed = calibrate.command_runs(
            argparse.Namespace(state_dir=args.state_dir, limit=20)
        )
        self.assertEqual(listed["runs"][0]["status"], "invalidated")
        stats = calibrate.command_stats(
            argparse.Namespace(state_dir=args.state_dir, task_class="feature")
        )
        self.assertEqual(stats["invalidated_runs"], 1)
        self.assertEqual(stats["completed_runs"], 0)

    def test_unstarted_forecast_can_only_close_without_completion(self):
        args = self.state_args("unstarted")
        path = calibrate.history_path(args)
        calibrate.append_event(
            path,
            {
                "event": "forecast",
                "run_id": "declined-run",
                "forecast_at": "2026-01-01T00:00:00Z",
                "forecast_time_minutes": [10, 20],
                "forecast_tokens": [10000, 20000],
                "task_class": "feature",
                "session_file": None,
            },
        )
        finish_args = argparse.Namespace(
            state_dir=args.state_dir,
            run_id="declined-run",
            repo=".",
            outcome="completed",
        )
        with self.assertRaisesRegex(calibrate.CalibrationError, "must be started"):
            calibrate.command_finish(finish_args)

        finish_args.outcome = "abandoned"
        result = calibrate.command_finish(finish_args)

        self.assertEqual(result["outcome"], "abandoned")
        self.assertEqual(result["active_elapsed_seconds"], 0)
        listed = calibrate.command_runs(
            argparse.Namespace(state_dir=args.state_dir, limit=20)
        )
        self.assertEqual(listed["runs"][0]["status"], "abandoned")

    def test_diff_stats_includes_untracked_text(self):
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "Test"], check=True
        )
        tracked = repo / "tracked.txt"
        tracked.write_text("first\n")
        subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)
        base = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tracked.write_text("first\nsecond\n")
        (repo / "new.txt").write_text("one\ntwo\n")

        stats = calibrate.diff_stats(repo, base)

        self.assertEqual(stats["actual_files"], ["new.txt", "tracked.txt"])
        self.assertEqual(stats["actual_additions"], 3)
        self.assertEqual(stats["actual_deletions"], 0)

    def test_reconcile_attributes_execution_interval_not_planning_turn(self):
        args = self.state_args("execution-boundary")
        session = self.root / "execution-boundary.jsonl"
        rows = [
            {"timestamp": "2026-01-01T00:00:01Z", "type": "session_meta", "payload": {"id": "s1"}},
            {"timestamp": "2026-01-01T00:01:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10, "reasoning_output_tokens": 5, "total_tokens": 100}}}},
            {"timestamp": "2026-01-01T00:02:00Z", "type": "event_msg", "payload": {"type": "task_started", "turn_id": "t1"}},
            {"timestamp": "2026-01-01T00:02:01Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 200, "cached_input_tokens": 40, "output_tokens": 20, "reasoning_output_tokens": 10, "total_tokens": 200}, "last_token_usage": {"total_tokens": 900}, "context_size": 800}}},
            {"timestamp": "2026-01-01T00:03:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 300, "cached_input_tokens": 60, "output_tokens": 30, "reasoning_output_tokens": 15, "total_tokens": 300}, "last_token_usage": {"total_tokens": 100}, "context_size": 500}}},
            {"timestamp": "2026-01-01T00:04:00Z", "type": "event_msg", "payload": {"type": "task_complete"}},
        ]
        session.write_text("".join(json.dumps(row) + "\n" for row in rows))
        path = calibrate.history_path(args)
        calibrate.append_event(path, {"event": "forecast", "run_id": "boundary", "forecast_at": "2026-01-01T00:00:00Z", "forecast_time_minutes": [1, 2], "forecast_tokens": [1, 2], "task_class": "feature", "session_file": str(session)})
        calibrate.append_event(path, {"event": "start", "run_id": "boundary", "started_at": "2026-01-01T00:02:00Z", "execution_session_id": "s1", "execution_turn_id": "t1"})
        calibrate.append_event(path, {"event": "finish", "run_id": "boundary", "finished_at": "2026-01-01T00:04:00Z", "outcome": "completed", "active_elapsed_seconds": 120})

        self.assertEqual(calibrate.reconcile_pending(args), 1)
        measurement = calibrate.reconstruct(calibrate.load_events(path))["boundary"]["reconcile"]
        self.assertEqual(measurement["token_usage"]["total_tokens"], 200)
        self.assertEqual(measurement["token_usage"]["uncached_input_tokens"], 160)
        self.assertEqual(measurement["context_size"], 500)

    def test_counter_reset_is_unavailable_but_zero_delta_is_valid(self):
        before = {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 13}
        reset = dict(before, total_tokens=12)
        zero = dict(before)
        self.assertIsNone(calibrate.token_counter_delta(before, reset))
        self.assertEqual(calibrate.token_counter_delta(before, zero)["total_tokens"], 0)

    def test_reconciliation_is_idempotent(self):
        args = self.state_args("idempotent")
        session = self.root / "idempotent.jsonl"
        rows = [
            {"timestamp": "2026-01-01T00:00:30Z", "type": "event_msg", "session_id": "s", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 10}}}},
            {"timestamp": "2026-01-01T00:01:00Z", "type": "event_msg", "session_id": "s", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 10}}}},
            {"timestamp": "2026-01-01T00:02:00Z", "type": "event_msg", "session_id": "s", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 10}}}},
        ]
        session.write_text("".join(json.dumps(row) + "\n" for row in rows))
        path = calibrate.history_path(args)
        calibrate.append_event(path, {"event": "forecast", "run_id": "once", "forecast_at": "2026-01-01T00:00:00Z", "forecast_time_minutes": [1, 2], "forecast_tokens": [1, 2], "task_class": "feature", "session_file": str(session)})
        calibrate.append_event(path, {"event": "start", "run_id": "once", "started_at": "2026-01-01T00:01:00Z", "execution_session_id": "s"})
        calibrate.append_event(path, {"event": "finish", "run_id": "once", "finished_at": "2026-01-01T00:02:00Z", "outcome": "completed", "active_elapsed_seconds": 60})
        self.assertEqual(calibrate.reconcile_pending(args), 1)
        self.assertEqual(calibrate.reconcile_pending(args), 0)

    def test_reconcile_requires_distinct_closing_sample(self):
        args = self.state_args("missing-closing")
        session = self.root / "missing-closing.jsonl"
        usage = {"input_tokens": 10, "cached_input_tokens": 2, "output_tokens": 3, "reasoning_output_tokens": 1, "total_tokens": 10}
        rows = [
            {"timestamp": "2026-01-01T00:00:01Z", "type": "session_meta", "payload": {"id": "s"}},
            {"timestamp": "2026-01-01T00:01:00Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": usage}}},
        ]
        session.write_text("".join(json.dumps(row) + "\n" for row in rows))
        path = calibrate.history_path(args)
        calibrate.append_event(path, {"event": "forecast", "run_id": "missing", "forecast_at": "2026-01-01T00:00:00Z", "forecast_time_minutes": [1, 2], "forecast_tokens": [10, 20], "task_class": "feature", "session_file": str(session)})
        calibrate.append_event(path, {"event": "start", "run_id": "missing", "started_at": "2026-01-01T00:01:00Z", "execution_session_id": "s"})
        calibrate.append_event(path, {"event": "finish", "run_id": "missing", "finished_at": "2026-01-01T00:02:00Z", "outcome": "completed", "active_elapsed_seconds": 60})
        calibrate.reconcile_pending(args)
        measurement = calibrate.reconstruct(calibrate.load_events(path))["missing"]["reconcile"]
        self.assertEqual(measurement["measurement_status"], "unavailable")
        self.assertIsNone(measurement["token_usage"])

    def test_backtest_reports_chronological_samples(self):
        args = self.state_args("backtest")
        path = calibrate.history_path(args)
        for index in range(6):
            run_id = f"chronological-{index}"
            calibrate.append_event(path, {"event": "forecast", "run_id": run_id, "forecast_at": "2026-01-01T00:00:00Z", "forecast_time_minutes": [10, 20], "forecast_tokens": [100, 200], "task_class": "bug-fix"})
            calibrate.append_event(path, {"event": "finish", "run_id": run_id, "finished_at": f"2026-01-0{index + 1}T01:00:00Z", "outcome": "completed", "active_elapsed_seconds": 900})
        result = calibrate.backtest(calibrate.completed_runs(args), "time", "bugfix")
        self.assertEqual(result["existing"]["sample_count"], 0)
        self.assertEqual(result["class_correction"]["sample_count"], 0)

    def test_stats_skips_unavailable_git_metrics(self):
        args = self.state_args("stats-unavailable-git")
        path = calibrate.history_path(args)
        calibrate.append_event(path, {"event": "forecast", "run_id": "no-git", "forecast_at": "2026-01-01T00:00:00Z", "forecast_time_minutes": [1, 2], "forecast_tokens": [10, 20], "task_class": "feature"})
        calibrate.append_event(path, {"event": "finish", "run_id": "no-git", "finished_at": "2026-01-01T00:01:00Z", "outcome": "completed", "active_elapsed_seconds": 60, "actual_files": None, "actual_additions": None, "actual_deletions": None})
        result = calibrate.command_stats(argparse.Namespace(state_dir=args.state_dir, task_class="feature"))
        self.assertEqual(result["completed_runs"], 1)
        self.assertEqual(result["files"]["sample_size"], 0)

    def test_token_backtest_uses_incremental_prediction_units(self):
        args = self.state_args("token-backtest")
        path = calibrate.history_path(args)
        for run_id, forecast_at, finished_at, actual in (
            ("prior", "2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z", 100),
            ("target", "2026-01-02T00:00:00Z", "2026-01-02T01:00:00Z", 200),
        ):
            calibrate.append_event(path, {"event": "forecast", "run_id": run_id, "forecast_at": forecast_at, "forecast_time_minutes": [1, 2], "forecast_tokens": [10100, 10100], "submitted_forecast_tokens": [100, 100], "task_class": "feature"})
            calibrate.append_event(path, {"event": "finish", "run_id": run_id, "finished_at": finished_at, "outcome": "completed", "active_elapsed_seconds": 60})
            calibrate.append_event(path, {"event": "reconcile", "run_id": run_id, "measurement_version": 2, "token_metric": "cumulative_counter_delta", "measurement_status": "available", "token_usage": {"total_tokens": actual}})
        result = calibrate.backtest(calibrate.completed_runs(args), "tokens", "feature")
        self.assertEqual(result["existing"]["sample_count"], 1)
        self.assertEqual(result["existing"]["midpoint_error"], 100)


if __name__ == "__main__":
    unittest.main()
