"""Full environment & eval pipeline diagnostic (`claude-eval doctor`)."""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from ..core.eval_runner import EvalRunner
from ..core.redteam_suite import RedTeamSuite
from ..core.task_suite import TaskSuite
from ..serve.health_monitor import HealthMonitor


def run_doctor(workspace: str | Path = ".") -> dict[str, Any]:
    """Run end-to-end environment, suite, red-team, and receipt ledger diagnostics."""
    health = HealthMonitor(workspace).check()
    suite = TaskSuite.builtin()
    eval_report = EvalRunner().run_offline_replay(suite)
    rt_report = RedTeamSuite().run()

    all_ok = (
        sys.version_info >= (3, 10)
        and health["receipt_chain"]["valid"]
        and eval_report.pass_rate == 1.0
        and rt_report.safety_block_rate == 1.0
    )

    return {
        "healthy": all_ok,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "zero_runtime_dependencies": True,
        "health": health,
        "smoke_eval": {
            "tasks": eval_report.total_tasks,
            "pass_rate": eval_report.pass_rate,
            "total_usd": eval_report.total_usd,
            "p50_latency_ms": eval_report.p50_latency_ms,
        },
        "smoke_redteam": {
            "probes": rt_report.total_probes,
            "safety_block_rate": rt_report.safety_block_rate,
        },
    }
