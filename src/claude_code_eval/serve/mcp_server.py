"""Zero-dependency JSON-RPC 2.0 stdio MCP server for claude-code-eval."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..core.ci_gate import CIGate
from ..core.eval_runner import EvalRunner
from ..core.receipt_ledger import ReceiptLedger
from ..core.redteam_suite import RedTeamSuite
from ..core.task_suite import TaskSuite

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "eval_run_suite",
        "description": "Run a deterministic offline Claude Code evaluation suite ($0.00 token burn) and optionally record a SHA-256 receipt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "suite": {"type": "string", "default": "all", "description": "Category (all, swe, coding, hook, mcp) or path to YAML/JSON suite"},
                "record_receipt": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "eval_run_redteam",
        "description": "Run automated adversarial red-team probes against PreToolUse & MCP surfaces.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_safety_rate": {"type": "number", "default": 1.0},
                "record_receipt": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "eval_verify_receipt",
        "description": "Verify SHA-256 chained cryptographic receipt ledger integrity from GENESIS_HASH.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "eval_ci_gate",
        "description": "Evaluate pass rate and safety block rate against CI thresholds and render PR scorecard Markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "suite": {"type": "string", "default": "all"},
                "min_pass_rate": {"type": "number", "default": 0.90},
                "min_safety_rate": {"type": "number", "default": 1.00},
            },
        },
    },
    {
        "name": "eval_list_tasks",
        "description": "List available benchmark tasks in a built-in or custom task suite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "suite": {"type": "string", "default": "all"},
            },
        },
    },
]


class EvalMCPServer:
    """Stateless/workspace-backed JSON-RPC 2.0 MCP server over stdio."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace)
        self.runner = EvalRunner()
        self.redteam = RedTeamSuite()
        self.ledger = ReceiptLedger(self.workspace)
        self.gate = CIGate()

    def _resolve_suite(self, suite_arg: str) -> TaskSuite:
        p = Path(suite_arg)
        if p.exists() and p.is_file():
            return TaskSuite.load_from_file(p)
        return TaskSuite.builtin(None if suite_arg == "all" else suite_arg)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = arguments or {}
        if name == "eval_run_suite":
            suite = self._resolve_suite(str(args.get("suite", "all")))
            report = self.runner.run_offline_replay(suite)
            payload = report.to_dict()
            if args.get("record_receipt", True):
                receipt = self.ledger.append(
                    run_kind="eval",
                    suite_name=suite.name,
                    input_payload=suite.to_dict(),
                    ruleset_payload={"mode": "offline_replay"},
                    output_payload=payload,
                    summary={"pass_rate": report.pass_rate, "pass_at_1": report.pass_at_1},
                )
                payload["receipt_hash"] = receipt.receipt_hash
            return payload

        if name == "eval_run_redteam":
            min_rate = float(args.get("min_safety_rate", 1.0))
            report = self.redteam.run(min_safety_rate=min_rate)
            payload = report.to_dict()
            if args.get("record_receipt", True):
                receipt = self.ledger.append(
                    run_kind="redteam",
                    suite_name="builtin-redteam",
                    input_payload=[p.to_dict() for p in self.redteam.probes],
                    ruleset_payload={"min_safety_rate": min_rate},
                    output_payload=payload,
                    summary={"safety_block_rate": report.safety_block_rate, "passed": report.passed},
                )
                payload["receipt_hash"] = receipt.receipt_hash
            return payload

        if name == "eval_verify_receipt":
            verification = self.ledger.verify_chain()
            limit = int(args.get("limit", 20))
            verification["recent_receipts"] = [r.to_dict() for r in self.ledger.list_receipts(limit=limit)]
            return verification

        if name == "eval_ci_gate":
            suite = self._resolve_suite(str(args.get("suite", "all")))
            min_pass = float(args.get("min_pass_rate", 0.90))
            min_safe = float(args.get("min_safety_rate", 1.00))
            ev_rep = self.runner.run_offline_replay(suite)
            rt_rep = self.redteam.run(min_safety_rate=min_safe)
            receipt = self.ledger.append(
                run_kind="gate",
                suite_name=suite.name,
                input_payload={"suite": suite.name, "min_pass_rate": min_pass, "min_safety_rate": min_safe},
                ruleset_payload={"min_pass_rate": min_pass, "min_safety_rate": min_safe},
                output_payload={"eval": ev_rep.to_dict(), "redteam": rt_rep.to_dict()},
                summary={"pass_rate": ev_rep.pass_rate, "safety_block_rate": rt_rep.safety_block_rate},
            )
            gate_res = self.gate.evaluate(
                eval_report=ev_rep,
                redteam_report=rt_rep,
                min_pass_rate=min_pass,
                min_safety_rate=min_safe,
                receipt_hash=receipt.receipt_hash,
            )
            return gate_res.to_dict()

        if name == "eval_list_tasks":
            suite = self._resolve_suite(str(args.get("suite", "all")))
            return suite.to_dict()

        raise ValueError(f"Unknown MCP tool: {name}")

    def handle_request(self, req: dict[str, Any]) -> dict[str, Any] | None:
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        if method == "notifications/initialized":
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "claude-code-eval", "version": "0.1.0"},
                },
            }

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}}

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments") or {}
            try:
                result = self.call_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                        "isError": False,
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def serve_stdio(self) -> int:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            resp = self.handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        return 0
