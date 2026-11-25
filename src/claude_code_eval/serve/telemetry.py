"""Rolling pass@k, safety block rate, token efficiency, and P50/P99 latency telemetry."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

from ..core.eval_runner import EvalSuiteReport, percentile
from ..core.redteam_suite import RedTeamReport


@dataclass
class TelemetrySnapshot:
    eval_runs: int
    redteam_runs: int
    rolling_pass_at_1: float
    rolling_safety_block_rate: float
    rolling_token_efficiency: float
    p50_latency_ms: float
    p99_latency_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvalTelemetry:
    """In-memory bounded rolling telemetry collector for eval & red-team runs."""

    def __init__(self, window: int = 100) -> None:
        self._pass_at_1: deque[float] = deque(maxlen=window)
        self._safety_rates: deque[float] = deque(maxlen=window)
        self._token_eff: deque[float] = deque(maxlen=window)
        self._latencies: deque[float] = deque(maxlen=window * 10)

    def record_eval(self, report: EvalSuiteReport) -> None:
        self._pass_at_1.append(report.pass_at_1)
        self._token_eff.append(report.avg_token_efficiency)
        for r in report.results:
            self._latencies.append(r.latency_ms)

    def record_redteam(self, report: RedTeamReport) -> None:
        self._safety_rates.append(report.safety_block_rate)
        for r in report.results:
            self._latencies.append(r.latency_ms)

    def snapshot(self) -> TelemetrySnapshot:
        lat = list(self._latencies)
        return TelemetrySnapshot(
            eval_runs=len(self._pass_at_1),
            redteam_runs=len(self._safety_rates),
            rolling_pass_at_1=round(sum(self._pass_at_1) / len(self._pass_at_1), 4) if self._pass_at_1 else 0.0,
            rolling_safety_block_rate=round(sum(self._safety_rates) / len(self._safety_rates), 4) if self._safety_rates else 0.0,
            rolling_token_efficiency=round(sum(self._token_eff) / len(self._token_eff), 4) if self._token_eff else 0.0,
            p50_latency_ms=percentile(lat, 50),
            p99_latency_ms=percentile(lat, 99),
        )
