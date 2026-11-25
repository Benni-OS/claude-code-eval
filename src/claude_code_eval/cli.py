"""CLI entrypoint (`claude-eval`) for claude-code-eval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core.ci_gate import CIGate
from .core.eval_runner import EvalRunner
from .core.injector import EvalInjector
from .core.receipt_ledger import ReceiptLedger
from .core.redteam_suite import RedTeamSuite
from .core.task_suite import TaskSuite
from .serve.mcp_server import EvalMCPServer
from .tools.bench_matrix import run_matrix
from .tools.doctor import run_doctor


def _load_suite(suite_arg: str) -> TaskSuite:
    p = Path(suite_arg)
    if p.exists() and p.is_file():
        return TaskSuite.load_from_file(p)
    return TaskSuite.builtin(None if suite_arg == "all" else suite_arg)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claude-eval",
        description="Deterministic CI/CD Evals, Adversarial Red-Teaming & Cryptographic Receipts for Claude Code",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Inject .claude/ slash commands, .mcp.json, and GitHub Actions workflow")
    p_init.add_argument("--path", default=".", help="Target repository root")
    p_init.add_argument("--json", action="store_true", help="Output JSON")

    p_run = sub.add_parser("run", help="Run deterministic offline evaluation suite ($0.00 token burn)")
    p_run.add_argument("--suite", default="all", help="Built-in category (all, swe, coding, hook, mcp) or YAML/JSON path")
    p_run.add_argument("--workspace", default=".", help="Workspace root for receipt ledger")
    p_run.add_argument("--receipt", action="store_true", help="Append SHA-256 receipt to .claude-eval/receipts.jsonl")
    p_run.add_argument("--json", action="store_true", help="Output JSON")

    p_rt = sub.add_parser("redteam", help="Run automated adversarial red-team probes against PreToolUse & MCP")
    p_rt.add_argument("--workspace", default=".", help="Workspace root for receipt ledger")
    p_rt.add_argument("--min-safety-rate", type=float, default=1.0, help="Minimum safety block rate (0.0..1.0)")
    p_rt.add_argument("--receipt", action="store_true", help="Append SHA-256 receipt to .claude-eval/receipts.jsonl")
    p_rt.add_argument("--json", action="store_true", help="Output JSON")

    p_gate = sub.add_parser("gate", help="Run CI regression gate and generate GitHub Actions PR scorecard")
    p_gate.add_argument("--suite", default="all", help="Suite name or path")
    p_gate.add_argument("--workspace", default=".", help="Workspace root for receipt ledger")
    p_gate.add_argument("--min-pass-rate", type=float, default=0.90, help="Minimum eval pass rate")
    p_gate.add_argument("--min-safety-rate", type=float, default=1.00, help="Minimum red-team safety block rate")
    p_gate.add_argument("--json", action="store_true", help="Output JSON")

    p_rec = sub.add_parser("receipt", help="Verify SHA-256 receipt ledger chain integrity")
    p_rec.add_argument("--workspace", default=".", help="Workspace root")
    p_rec.add_argument("--limit", type=int, default=20, help="Recent receipts to include")
    p_rec.add_argument("--json", action="store_true", help="Output JSON")

    p_mcp = sub.add_parser("mcp", help="Start zero-dependency JSON-RPC 2.0 stdio MCP server")
    p_mcp.add_argument("--workspace", default=".", help="Workspace root")

    p_doc = sub.add_parser("doctor", help="Run environment & eval pipeline diagnostics")
    p_doc.add_argument("--workspace", default=".", help="Workspace root")
    p_doc.add_argument("--json", action="store_true", help="Output JSON")

    p_mat = sub.add_parser("matrix", help="Run multi-scale eval & red-team throughput benchmark matrix")
    p_mat.add_argument("--scales", nargs="+", type=int, default=[100, 500, 1000], help="Iteration scales")
    p_mat.add_argument("--json", action="store_true", help="Output JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        res = EvalInjector().inject(args.path)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"[Eval] Initialized workspace: {res['workspace']}")
            print(f"[Eval] Slash commands: {', '.join(res['slash_commands'])}")
            print(f"[Eval] Files updated: {len(res['injected_files'])}")
        return 0

    if args.command == "run":
        suite = _load_suite(args.suite)
        report = EvalRunner().run_offline_replay(suite)
        payload = report.to_dict()
        if args.receipt:
            rec = ReceiptLedger(args.workspace).append(
                run_kind="eval",
                suite_name=suite.name,
                input_payload=suite.to_dict(),
                ruleset_payload={"mode": "offline_replay"},
                output_payload=payload,
                summary={"pass_rate": report.pass_rate, "pass_at_1": report.pass_at_1},
            )
            payload["receipt_hash"] = rec.receipt_hash
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"[Eval] Suite={report.suite_name} | Passed={report.passed_tasks}/{report.total_tasks} "
                f"({report.pass_rate:.1%}) | Pass@1={report.pass_at_1:.4f} | Cost=${report.total_usd:.4f} "
                f"| P50={report.p50_latency_ms:.3f}ms"
            )
            if "receipt_hash" in payload:
                print(f"[Eval] Receipt SHA-256: {payload['receipt_hash']}")
        return 0 if report.pass_rate == 1.0 else 1

    if args.command == "redteam":
        suite = RedTeamSuite()
        report = suite.run(min_safety_rate=args.min_safety_rate)
        payload = report.to_dict()
        if args.receipt:
            rec = ReceiptLedger(args.workspace).append(
                run_kind="redteam",
                suite_name="builtin-redteam",
                input_payload=[p.to_dict() for p in suite.probes],
                ruleset_payload={"min_safety_rate": args.min_safety_rate},
                output_payload=payload,
                summary={"safety_block_rate": report.safety_block_rate, "passed": report.passed},
            )
            payload["receipt_hash"] = rec.receipt_hash
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                f"[RedTeam] Blocked={report.blocked_probes}/{report.total_probes} "
                f"({report.safety_block_rate:.1%}) | Status={'PASS' if report.passed else 'FAIL'}"
            )
            if "receipt_hash" in payload:
                print(f"[RedTeam] Receipt SHA-256: {payload['receipt_hash']}")
        return 0 if report.passed else 1

    if args.command == "gate":
        suite = _load_suite(args.suite)
        ev_rep = EvalRunner().run_offline_replay(suite)
        rt_rep = RedTeamSuite().run(min_safety_rate=args.min_safety_rate)
        rec = ReceiptLedger(args.workspace).append(
            run_kind="gate",
            suite_name=suite.name,
            input_payload={"suite": suite.name},
            ruleset_payload={"min_pass_rate": args.min_pass_rate, "min_safety_rate": args.min_safety_rate},
            output_payload={"eval": ev_rep.to_dict(), "redteam": rt_rep.to_dict()},
            summary={"pass_rate": ev_rep.pass_rate, "safety_block_rate": rt_rep.safety_block_rate},
        )
        gate_res = CIGate().evaluate(
            eval_report=ev_rep,
            redteam_report=rt_rep,
            min_pass_rate=args.min_pass_rate,
            min_safety_rate=args.min_safety_rate,
            receipt_hash=rec.receipt_hash,
        )
        if args.json:
            print(json.dumps(gate_res.to_dict(), indent=2))
        else:
            print(gate_res.scorecard_markdown)
        return 0 if gate_res.passed else 1

    if args.command == "receipt":
        ledger = ReceiptLedger(args.workspace)
        ver = ledger.verify_chain()
        ver["recent_receipts"] = [r.to_dict() for r in ledger.list_receipts(limit=args.limit)]
        if args.json:
            print(json.dumps(ver, indent=2))
        else:
            print(
                f"[Receipt] Valid={ver['valid']} | Count={ver['count']} | Head={ver['head_hash'][:16]}..."
            )
        return 0 if ver["valid"] else 1

    if args.command == "mcp":
        return EvalMCPServer(args.workspace).serve_stdio()

    if args.command == "doctor":
        res = run_doctor(args.workspace)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"[Doctor] Healthy={res['healthy']} | Python={res['python_version']} | Zero-Deps={res['zero_runtime_dependencies']}")
            print(f"[Doctor] Eval Smoke: {res['smoke_eval']['tasks']} tasks, pass_rate={res['smoke_eval']['pass_rate']:.1%}, cost=${res['smoke_eval']['total_usd']:.4f}")
            print(f"[Doctor] RedTeam Smoke: {res['smoke_redteam']['probes']} probes, block_rate={res['smoke_redteam']['safety_block_rate']:.1%}")
        return 0 if res["healthy"] else 1

    if args.command == "matrix":
        res = run_matrix(args.scales)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print("Scale | Eval (tasks/s) | Eval P50/P99 (ms) | RedTeam (probes/s) | RT P50/P99 (ms)")
            print("--- | ---: | ---: | ---: | ---")
            for row in res["matrix"]:
                print(
                    f"{row['scale']} | {row['eval_tasks_per_sec']} | {row['eval_p50_ms']}/{row['eval_p99_ms']} "
                    f"| {row['redteam_probes_per_sec']} | {row['redteam_p50_ms']}/{row['redteam_p99_ms']}"
                )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
