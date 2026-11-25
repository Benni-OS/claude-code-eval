"""Tests for EvalRunner offline replay, sandbox execution, and RedTeamSuite."""

from __future__ import annotations

import sys
from pathlib import Path

from claude_code_eval.core.eval_runner import EvalRunner, percentile
from claude_code_eval.core.redteam_suite import RedTeamSuite, default_pretool_guard
from claude_code_eval.core.task_suite import TaskSuite


def test_percentile_helper() -> None:
    assert percentile([], 50) == 0.0
    assert percentile([4.2], 99) == 4.2
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 50) == 3.0


def test_offline_replay_zero_cost_all_pass() -> None:
    suite = TaskSuite.builtin("all")
    report = EvalRunner().run_offline_replay(suite)
    assert report.mode == "offline_replay"
    assert report.total_tasks == len(suite.tasks)
    assert report.passed_tasks == len(suite.tasks)
    assert report.pass_rate == 1.0
    assert report.total_usd == 0.0
    assert report.p50_latency_ms >= 0.0


def test_offline_replay_detects_regression() -> None:
    suite = TaskSuite.builtin("swe")
    runner = EvalRunner()
    overrides = {
        "SWE-001": {
            "output": "def broken(:\n",
            "tools": ["Edit"],
            "tokens": 99999,
            "usd": 0.0,
        }
    }
    report = runner.run_offline_replay(suite, trajectories=overrides)
    assert report.passed_tasks < report.total_tasks
    assert report.pass_rate < 1.0


def test_sandbox_command_execution(tmp_path: Path) -> None:
    runner = EvalRunner()
    res = runner.run_sandbox_command([sys.executable, "-c", "print('sandbox-ok')"], cwd=tmp_path)
    assert res["returncode"] == 0
    assert "sandbox-ok" in res["stdout"]
    assert res["timed_out"] is False


def test_redteam_builtin_blocks_all_categories() -> None:
    rt = RedTeamSuite()
    report = rt.run(min_safety_rate=1.0)
    assert report.total_probes >= 10
    assert report.blocked_probes == report.total_probes
    assert report.bypassed_probes == 0
    assert report.safety_block_rate == 1.0
    assert report.passed is True
    for cat in ("prompt_injection", "secret_exfiltration", "ssrf", "path_traversal", "destructive_shell"):
        assert cat in report.by_category
        assert report.by_category[cat]["blocked"] == report.by_category[cat]["total"]


def test_redteam_detects_permissive_guard_bypass() -> None:
    rt = RedTeamSuite()
    report = rt.run(guard=lambda _tool, _inp: ("allow", "permissive"), min_safety_rate=1.0)
    assert report.blocked_probes == 0
    assert report.safety_block_rate == 0.0
    assert report.passed is False


def test_default_pretool_guard_allows_safe_command() -> None:
    decision, _ = default_pretool_guard("Bash", {"command": "pytest -q"})
    assert decision == "allow"


def test_redteam_hook_command_subprocess(tmp_path: Path) -> None:
    hook_script = tmp_path / "hook.py"
    hook_script.write_text(
        "import json, sys\n"
        "data = json.load(sys.stdin)\n"
        "print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'deny', 'reason': 'blocked-by-hook'}}))\n",
        encoding="utf-8",
    )
    rt = RedTeamSuite()
    report = rt.run_hook_command([sys.executable, str(hook_script)], min_safety_rate=1.0)
    assert report.passed is True
    assert report.blocked_probes == report.total_probes

