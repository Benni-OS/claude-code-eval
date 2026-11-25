"""Multi-scale eval & red-team throughput benchmark matrix (`claude-eval matrix`)."""

from __future__ import annotations

import time
from typing import Any

from ..core.eval_runner import EvalRunner, percentile
from ..core.redteam_suite import RedTeamSuite
from ..core.task_suite import TaskSuite


def run_matrix(scales: list[int] | None = None) -> dict[str, Any]:
    """Benchmark eval replay & red-team probe throughput across multiple iteration scales."""
    target_scales = scales or [100, 500, 1000]
    suite = TaskSuite.builtin()
    runner = EvalRunner()
    rt = RedTeamSuite()
    rows: list[dict[str, Any]] = []

    for scale in target_scales:
        eval_latencies: list[float] = []
        t0 = time.perf_counter()
        for i in range(scale):
            task = suite.tasks[i % len(suite.tasks)]
            res = runner.run_task_offline(task)
            eval_latencies.append(res.latency_ms)
        eval_total_s = max(time.perf_counter() - t0, 1e-9)

        rt_t0 = time.perf_counter()
        rt_latencies: list[float] = []
        for _ in range(max(1, scale // 10)):
            rep = rt.run()
            for pr in rep.results:
                rt_latencies.append(pr.latency_ms)
        rt_total_s = max(time.perf_counter() - rt_t0, 1e-9)

        rows.append(
            {
                "scale": scale,
                "eval_tasks_per_sec": round(scale / eval_total_s, 1),
                "eval_p50_ms": percentile(eval_latencies, 50),
                "eval_p99_ms": percentile(eval_latencies, 99),
                "redteam_probes_executed": len(rt_latencies),
                "redteam_probes_per_sec": round(len(rt_latencies) / rt_total_s, 1),
                "redteam_p50_ms": percentile(rt_latencies, 50),
                "redteam_p99_ms": percentile(rt_latencies, 99),
            }
        )

    return {"scales": target_scales, "matrix": rows}
