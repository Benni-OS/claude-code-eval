"""Tests for MCP server JSON-RPC 2.0, telemetry, health monitor, doctor, and matrix."""

from __future__ import annotations

import json
from pathlib import Path

from claude_code_eval.core.eval_runner import EvalRunner
from claude_code_eval.core.redteam_suite import RedTeamSuite
from claude_code_eval.core.task_suite import TaskSuite
from claude_code_eval.serve.health_monitor import HealthMonitor
from claude_code_eval.serve.mcp_server import MCP_TOOLS, EvalMCPServer
from claude_code_eval.serve.telemetry import EvalTelemetry
from claude_code_eval.tools.bench_matrix import run_matrix
from claude_code_eval.tools.doctor import run_doctor


def test_mcp_server_initialize_and_tools_list(tmp_path: Path) -> None:
    srv = EvalMCPServer(tmp_path)
    init_resp = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp is not None
    assert init_resp["result"]["serverInfo"]["name"] == "claude-code-eval"

    list_resp = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert list_resp is not None
    names = {t["name"] for t in list_resp["result"]["tools"]}
    assert names == {
        "eval_run_suite",
        "eval_run_redteam",
        "eval_verify_receipt",
        "eval_ci_gate",
        "eval_list_tasks",
    }
    assert len(MCP_TOOLS) == 5


def test_mcp_server_tools_call_flow(tmp_path: Path) -> None:
    srv = EvalMCPServer(tmp_path)
    for tool_name in ("eval_list_tasks", "eval_run_suite", "eval_run_redteam", "eval_ci_gate", "eval_verify_receipt"):
        resp = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": {}},
            }
        )
        assert resp is not None
        assert resp["result"]["isError"] is False
        payload = json.loads(resp["result"]["content"][0]["text"])
        assert isinstance(payload, dict)


def test_mcp_server_unknown_method_and_tool(tmp_path: Path) -> None:
    srv = EvalMCPServer(tmp_path)
    err = srv.handle_request({"jsonrpc": "2.0", "id": 99, "method": "unknown/method"})
    assert err is not None and "error" in err

    tool_err = srv.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }
    )
    assert tool_err is not None and tool_err["result"]["isError"] is True


def test_telemetry_and_health_monitor_and_tools(tmp_path: Path) -> None:
    tel = EvalTelemetry()
    ev_rep = EvalRunner().run_offline_replay(TaskSuite.builtin("all"))
    rt_rep = RedTeamSuite().run()
    tel.record_eval(ev_rep)
    tel.record_redteam(rt_rep)
    snap = tel.snapshot()
    assert snap.eval_runs == 1
    assert snap.redteam_runs == 1
    assert snap.rolling_pass_at_1 == 1.0
    assert snap.rolling_safety_block_rate == 1.0

    health = HealthMonitor(tmp_path).check()
    assert health["status"] == "healthy"
    assert health["builtin_tasks"] >= 5

    doc = run_doctor(tmp_path)
    assert doc["healthy"] is True

    mat = run_matrix([10, 25])
    assert len(mat["matrix"]) == 2
    assert mat["matrix"][0]["eval_tasks_per_sec"] > 0


def test_mcp_server_notifications_initialized_returns_none(tmp_path: Path) -> None:
    srv = EvalMCPServer(tmp_path)
    assert srv.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

