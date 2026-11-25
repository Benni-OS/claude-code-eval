# Architecture — `claude-code-eval`

`claude-code-eval` is a zero-dependency Python 3.10+ evaluation, adversarial red-teaming, and cryptographic receipt engine designed for **Claude Code** workflows, `PreToolUse` hooks, MCP servers, and GitHub Actions CI/CD pipelines.

## Design Principles

1. **Zero Runtime Dependencies**: Runs purely on the Python 3.10+ standard library (`ast`, `hashlib`, `json`, `re`, `subprocess`, `time`, `pathlib`, `argparse`, `statistics`). No fragile LLM-as-a-judge API keys or heavy ML dependencies are required.
2. **Deterministic Scoring**: Every task assertion is graded via deterministic static & runtime checks: Python `ast.parse` syntax verification, regex/diff invariance, tool-call sequence accuracy, token/USD efficiency bounds, and safety block-rate calculation.
3. **$0.00 Offline Trajectory Replay**: Evaluation suites can replay recorded Claude Code JSONL/JSON trajectories offline with zero token burn, or execute sandboxed subprocess checks with P50/P90/P99 latency telemetry.
4. **Cryptographic Provenance (`GENESIS_HASH`)**: Every evaluation and red-team run appends an immutable SHA-256 chained receipt linking `prev_hash`, `input_digest`, `ruleset_digest`, `output_digest`, and `receipt_hash`. Any tampering invalidates the chain.
5. **CI/CD Regression Gate**: Generates GitHub Actions PR scorecards and enforces configurable `--min-pass-rate` and `--min-safety-rate` thresholds.

## Module Topology

- `src/claude_code_eval/core/task_suite.py`: Declarative YAML-subset & JSON task loader, built-in SWE/coding/hook benchmark suites, `EvalTask`, `TaskAssertion`, `Pass@k`, and token-budget bounds.
- `src/claude_code_eval/core/scorers.py`: Deterministic scorers (`ast_valid`, `regex_match`, `regex_absent`, `diff_invariant`, `tool_sequence`, `token_budget`, `safety_block`).
- `src/claude_code_eval/core/eval_runner.py`: Offline trajectory replay & sandboxed subprocess evaluator with P50/P90/P99 latency & token efficiency scoring.
- `src/claude_code_eval/core/redteam_suite.py`: Adversarial probe suite testing `PreToolUse` hooks and MCP servers against indirect prompt injection, `.env`/API key exfiltration, SSRF, path traversal, and destructive shell commands.
- `src/claude_code_eval/core/receipt_ledger.py`: SHA-256 chained cryptographic receipt ledger (`GENESIS_HASH`) & reproducible chain verifier.
- `src/claude_code_eval/core/ci_gate.py`: GitHub Actions PR Markdown scorecard generator & pass/fail regression gate.
- `src/claude_code_eval/core/injector.py`: Idempotent `.claude/` & `.github/workflows/claude-eval.yml` CI injector + `/eval-run`, `/eval-redteam`, `/eval-gate` slash commands.
- `src/claude_code_eval/serve/`: Zero-dependency JSON-RPC 2.0 stdio MCP server (`mcp_server.py`), rolling `telemetry.py`, and `health_monitor.py`.
- `src/claude_code_eval/tools/`: Environment & pipeline diagnostics (`doctor.py`) and multi-scale benchmark matrix (`bench_matrix.py`).
