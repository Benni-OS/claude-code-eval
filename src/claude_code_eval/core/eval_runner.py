"""Deterministic evaluation runner: $0.00 offline trajectory replay & sandboxed execution."""

from __future__ import annotations

import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .scorers import ScoreResult, evaluate_assertion, score_token_efficiency
from .task_suite import EvalTask, TaskSuite, compute_pass_at_k


def percentile(values: list[float], p: float) -> float:
    """Compute linear-interpolated percentile (0..100) for a list of floats."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    k = (len(ordered) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    val = ordered[f] + (ordered[c] - ordered[f]) * (k - f)
    return round(val, 4)


@dataclass
class TaskRunResult:
    """Execution and scoring outcome for a single EvalTask."""

    task_id: str
    category: str
    passed: bool
    score: float
    latency_ms: float
    tokens_used: int
    usd_used: float
    token_efficiency: float
    mode: str
    tool_calls: list[str] = field(default_factory=list)
    assertion_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalSuiteReport:
    """Aggregated evaluation report for a TaskSuite run."""

    suite_name: str
    mode: str
    total_tasks: int
    passed_tasks: int
    pass_rate: float
    pass_at_1: float
    avg_token_efficiency: float
    total_tokens: int
    total_usd: float
    p50_latency_ms: float
    p90_latency_ms: float
    p99_latency_ms: float
    results: list[TaskRunResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["results"] = [r.to_dict() for r in self.results]
        return data


class EvalRunner:
    """Runs declarative TaskSuites via offline trajectory replay ($0.00) or sandboxed subprocess."""

    def run_task_offline(
        self,
        task: EvalTask,
        trajectory_override: dict[str, Any] | None = None,
    ) -> TaskRunResult:
        t0 = time.perf_counter()
        if trajectory_override is not None:
            output = str(trajectory_override.get("output", ""))
            tools = list(trajectory_override.get("tools", []))
            tokens_used = int(trajectory_override.get("tokens", task.reference_tokens))
            usd_used = float(trajectory_override.get("usd", 0.0))
        else:
            output = task.reference_output
            tools = list(task.reference_trajectory or task.expected_tools)
            tokens_used = task.reference_tokens
            usd_used = 0.0

        ctx = {"output": output, "tools": tools}
        assertion_scores: list[ScoreResult] = [
            evaluate_assertion(assertion, ctx) for assertion in task.assertions
        ]
        eff = score_token_efficiency(tokens_used, task.max_tokens, usd_used, task.max_usd)
        all_passed = all(s.passed for s in assertion_scores) and eff.passed
        avg_score = (
            sum(s.score for s in assertion_scores) / len(assertion_scores)
            if assertion_scores
            else 1.0
        )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 4)
        return TaskRunResult(
            task_id=task.task_id,
            category=task.category,
            passed=all_passed,
            score=round(avg_score, 4),
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            usd_used=usd_used,
            token_efficiency=eff.score,
            mode="offline_replay",
            tool_calls=tools,
            assertion_results=[s.to_dict() for s in assertion_scores],
        )

    def run_offline_replay(
        self,
        suite: TaskSuite,
        trajectories: dict[str, dict[str, Any]] | None = None,
    ) -> EvalSuiteReport:
        """Execute a full TaskSuite in $0.00 offline trajectory replay mode."""
        traj_map = trajectories or {}
        results: list[TaskRunResult] = []
        for task in suite.tasks:
            results.append(self.run_task_offline(task, traj_map.get(task.task_id)))

        total = len(results)
        passed_count = sum(1 for r in results if r.passed)
        pass_rate = round(passed_count / total, 4) if total else 0.0
        pass_at_1 = round(compute_pass_at_k(total, passed_count, 1), 4) if total else 0.0
        avg_eff = round(sum(r.token_efficiency for r in results) / total, 4) if total else 0.0
        latencies = [r.latency_ms for r in results]

        return EvalSuiteReport(
            suite_name=suite.name,
            mode="offline_replay",
            total_tasks=total,
            passed_tasks=passed_count,
            pass_rate=pass_rate,
            pass_at_1=pass_at_1,
            avg_token_efficiency=avg_eff,
            total_tokens=sum(r.tokens_used for r in results),
            total_usd=round(sum(r.usd_used for r in results), 6),
            p50_latency_ms=percentile(latencies, 50),
            p90_latency_ms=percentile(latencies, 90),
            p99_latency_ms=percentile(latencies, 99),
            results=results,
        )

    def run_sandbox_command(
        self,
        command: list[str],
        cwd: str | Path = ".",
        timeout_s: float = 10.0,
    ) -> dict[str, Any]:
        """Run a deterministic sandboxed subprocess check (no shell=True)."""
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                shell=False,
            )
            elapsed = round((time.perf_counter() - t0) * 1000.0, 4)
            return {
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "latency_ms": elapsed,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            elapsed = round((time.perf_counter() - t0) * 1000.0, 4)
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Timed out after {timeout_s}s",
                "latency_ms": elapsed,
                "timed_out": True,
            }
