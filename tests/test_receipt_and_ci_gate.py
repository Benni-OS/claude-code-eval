"""Tests for SHA-256 ReceiptLedger chain verification and CIGate PR scorecard."""

from __future__ import annotations

import json
from pathlib import Path

from claude_code_eval.core.ci_gate import CIGate
from claude_code_eval.core.eval_runner import EvalRunner
from claude_code_eval.core.receipt_ledger import GENESIS_HASH, ReceiptLedger
from claude_code_eval.core.redteam_suite import RedTeamSuite
from claude_code_eval.core.task_suite import TaskSuite


def test_receipt_ledger_empty_chain(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path)
    ver = ledger.verify_chain()
    assert ver["valid"] is True
    assert ver["count"] == 0
    assert ver["head_hash"] == GENESIS_HASH


def test_receipt_ledger_append_and_verify_chain(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path)
    r0 = ledger.append("eval", "all", {"t": 1}, {"m": "offline"}, {"ok": True}, {"pass_rate": 1.0})
    r1 = ledger.append("redteam", "rt", {"p": 10}, {"min": 1.0}, {"ok": True}, {"safety": 1.0})
    assert r0.seq == 0
    assert r0.prev_hash == GENESIS_HASH
    assert r1.seq == 1
    assert r1.prev_hash == r0.receipt_hash

    ver = ledger.verify_chain()
    assert ver["valid"] is True
    assert ver["count"] == 2
    assert ver["head_hash"] == r1.receipt_hash


def test_receipt_ledger_detects_tampering(tmp_path: Path) -> None:
    ledger = ReceiptLedger(tmp_path)
    ledger.append("eval", "all", {"a": 1}, {"b": 2}, {"c": 3}, {"pass_rate": 1.0})
    lines = ledger.ledger_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["summary"]["pass_rate"] = 0.0
    ledger.ledger_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")

    ver = ledger.verify_chain()
    assert ver["valid"] is False
    assert any("receipt_hash_tampered" in e for e in ver["errors"])


def test_ci_gate_pass_and_fail_scorecard() -> None:
    suite = TaskSuite.builtin("all")
    ev_rep = EvalRunner().run_offline_replay(suite)
    rt_rep = RedTeamSuite().run()
    gate = CIGate()

    ok_res = gate.evaluate(ev_rep, rt_rep, min_pass_rate=0.90, min_safety_rate=1.00, receipt_hash="abc123")
    assert ok_res.passed is True
    assert "PASS" in ok_res.scorecard_markdown
    assert "abc123" in ok_res.scorecard_markdown

    # Simulate red-team bypass failure
    rt_fail = RedTeamSuite().run(guard=lambda _t, _i: ("allow", "none"), min_safety_rate=1.0)
    fail_res = gate.evaluate(ev_rep, rt_fail, min_pass_rate=0.90, min_safety_rate=1.00)
    assert fail_res.passed is False
    assert "FAIL" in fail_res.scorecard_markdown
    assert len(fail_res.reasons) == 1
