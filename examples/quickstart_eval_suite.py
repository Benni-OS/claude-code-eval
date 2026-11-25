"""Quickstart: Run $0.00 deterministic offline evaluation suite and append a SHA-256 receipt."""

from __future__ import annotations

import tempfile
from pathlib import Path

from claude_code_eval.core import EvalRunner, ReceiptLedger, TaskSuite


def main() -> None:
    suite = TaskSuite.builtin("all")
    report = EvalRunner().run_offline_replay(suite)
    print(
        f"Suite={report.suite_name} | Passed={report.passed_tasks}/{report.total_tasks} "
        f"| Pass@1={report.pass_at_1:.4f} | Cost=${report.total_usd:.4f}"
    )

    with tempfile.TemporaryDirectory() as tmp:
        ledger = ReceiptLedger(Path(tmp))
        receipt = ledger.append(
            run_kind="eval",
            suite_name=suite.name,
            input_payload=suite.to_dict(),
            ruleset_payload={"mode": "offline_replay"},
            output_payload=report.to_dict(),
            summary={"pass_rate": report.pass_rate},
        )
        verification = ledger.verify_chain()
        print(f"Receipt SHA-256: {receipt.receipt_hash}")
        print(f"Chain valid: {verification['valid']} (count={verification['count']})")


if __name__ == "__main__":
    main()
