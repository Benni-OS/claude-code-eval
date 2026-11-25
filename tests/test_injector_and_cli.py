"""Tests for EvalInjector idempotency and all claude-eval CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from claude_code_eval.cli import main as cli_main
from claude_code_eval.core.injector import EvalInjector


def test_injector_creates_and_is_idempotent(tmp_path: Path) -> None:
    inj = EvalInjector()
    first = inj.inject(tmp_path)
    assert len(first["injected_files"]) == 5
    assert (tmp_path / ".claude" / "commands" / "eval-run.md").exists()
    assert (tmp_path / ".claude" / "commands" / "eval-redteam.md").exists()
    assert (tmp_path / ".claude" / "commands" / "eval-gate.md").exists()
    assert (tmp_path / ".github" / "workflows" / "claude-eval.yml").exists()
    assert (tmp_path / ".mcp.json").exists()

    second = inj.inject(tmp_path)
    assert second["injected_files"] == []


def test_cli_init_run_redteam_gate_receipt_doctor_matrix(tmp_path: Path, capsys) -> None:
    assert cli_main(["init", "--path", str(tmp_path), "--json"]) == 0
    init_out = json.loads(capsys.readouterr().out)
    assert len(init_out["slash_commands"]) == 3

    assert cli_main(["run", "--suite", "all", "--workspace", str(tmp_path), "--receipt", "--json"]) == 0
    run_out = json.loads(capsys.readouterr().out)
    assert run_out["pass_rate"] == 1.0
    assert "receipt_hash" in run_out

    assert cli_main(["redteam", "--workspace", str(tmp_path), "--receipt", "--json"]) == 0
    rt_out = json.loads(capsys.readouterr().out)
    assert rt_out["safety_block_rate"] == 1.0

    assert cli_main(["gate", "--workspace", str(tmp_path), "--json"]) == 0
    gate_out = json.loads(capsys.readouterr().out)
    assert gate_out["passed"] is True

    assert cli_main(["receipt", "--workspace", str(tmp_path), "--json"]) == 0
    rec_out = json.loads(capsys.readouterr().out)
    assert rec_out["valid"] is True
    assert rec_out["count"] == 3

    assert cli_main(["doctor", "--workspace", str(tmp_path), "--json"]) == 0
    doc_out = json.loads(capsys.readouterr().out)
    assert doc_out["healthy"] is True

    assert cli_main(["matrix", "--scales", "20", "--json"]) == 0
    mat_out = json.loads(capsys.readouterr().out)
    assert len(mat_out["matrix"]) == 1
