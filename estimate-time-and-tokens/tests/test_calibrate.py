import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
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
                    "token_metric": "last_token_usage",
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
        self.assertEqual(result["code_scope"]["historical_factors"]["files"]["median_factor"], 2)

    def test_forecast_uses_current_turn_tokens_as_a_floor(self):
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
                        "info": {"last_token_usage": {"total_tokens": 120000}},
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
        self.assertEqual(result["tokens"]["baseline"], [120000, 144000])
        self.assertEqual(result["tokens"]["calibrated"], [120000, 144000])

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

    def test_diff_stats_includes_untracked_text(self):
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
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


if __name__ == "__main__":
    unittest.main()
