"""Quickstart: Run automated adversarial red-team audit against PreToolUse & MCP surfaces."""

from __future__ import annotations

from claude_code_eval.core import RedTeamSuite


def main() -> None:
    suite = RedTeamSuite()
    report = suite.run(min_safety_rate=1.0)
    print(
        f"Probes={report.total_probes} | Blocked={report.blocked_probes} "
        f"| Safety Block Rate={report.safety_block_rate:.1%} | Passed={report.passed}"
    )
    for cat, stats in sorted(report.by_category.items()):
        print(f"  - {cat}: {stats['blocked']}/{stats['total']} blocked")


if __name__ == "__main__":
    main()
