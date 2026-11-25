"""Task suite, SHA-256 receipt ledger & CI workflow health monitor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.receipt_ledger import ReceiptLedger
from ..core.redteam_suite import RedTeamSuite
from ..core.task_suite import TaskSuite


class HealthMonitor:
    """Inspects built-in suites, receipt ledger integrity, and workspace CI configuration."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace).resolve()

    def check(self) -> dict[str, Any]:
        suite = TaskSuite.builtin()
        probes = RedTeamSuite().probes
        ledger = ReceiptLedger(self.workspace)
        chain = ledger.verify_chain()

        workflow_path = self.workspace / ".github" / "workflows" / "claude-eval.yml"
        cmd_dir = self.workspace / ".claude" / "commands"
        slash_present = (cmd_dir / "eval-run.md").exists() and (cmd_dir / "eval-redteam.md").exists()

        status = "healthy" if chain["valid"] and len(suite.tasks) > 0 and len(probes) > 0 else "degraded"
        return {
            "status": status,
            "workspace": str(self.workspace),
            "builtin_tasks": len(suite.tasks),
            "builtin_redteam_probes": len(probes),
            "receipt_chain": chain,
            "ci_workflow_present": workflow_path.exists(),
            "claude_slash_commands_present": slash_present,
        }
