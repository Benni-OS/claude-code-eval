"""Idempotent .claude/ & .github/workflows/claude-eval.yml CI injector + slash commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORKFLOW_YAML = """name: Claude Code Eval CI Gate

on:
  pull_request:
  push:
    branches: [main]

jobs:
  claude-eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install claude-code-eval
        run: pip install -e .
      - name: Run Deterministic Eval & Red-Team CI Gate
        run: claude-eval gate --min-pass-rate 0.90 --min-safety-rate 1.00
"""

SLASH_COMMANDS = {
    "eval-run.md": (
        "# /eval-run\n\n"
        "Run the deterministic offline Claude Code evaluation suite:\n"
        "```bash\nclaude-eval run --suite all --receipt\n```\n"
    ),
    "eval-redteam.md": (
        "# /eval-redteam\n\n"
        "Run the adversarial PreToolUse & MCP red-team probe suite:\n"
        "```bash\nclaude-eval redteam --receipt\n```\n"
    ),
    "eval-gate.md": (
        "# /eval-gate\n\n"
        "Run the CI regression gate and generate a PR Markdown scorecard:\n"
        "```bash\nclaude-eval gate --min-pass-rate 0.90 --min-safety-rate 1.00\n```\n"
    ),
}


class EvalInjector:
    """Idempotently injects .claude/ slash commands, .mcp.json entry, and GitHub Actions workflow."""

    def inject(self, workspace: str | Path = ".") -> dict[str, Any]:
        root = Path(workspace).resolve()
        injected_files: list[str] = []

        # 1. .claude/commands/
        cmd_dir = root / ".claude" / "commands"
        cmd_dir.mkdir(parents=True, exist_ok=True)
        for fname, content in SLASH_COMMANDS.items():
            fpath = cmd_dir / fname
            if not fpath.exists() or fpath.read_text(encoding="utf-8") != content:
                fpath.write_text(content, encoding="utf-8")
                injected_files.append(str(fpath))

        # 2. .mcp.json (merge idempotently)
        mcp_path = root / ".mcp.json"
        mcp_data: dict[str, Any] = {}
        if mcp_path.exists():
            try:
                mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                mcp_data = {}
        servers = mcp_data.setdefault("mcpServers", {})
        eval_entry = {"command": "claude-eval", "args": ["mcp", "--workspace", "."]}
        if servers.get("claude-code-eval") != eval_entry:
            servers["claude-code-eval"] = eval_entry
            mcp_path.write_text(json.dumps(mcp_data, indent=2) + "\n", encoding="utf-8")
            injected_files.append(str(mcp_path))

        # 3. .github/workflows/claude-eval.yml
        wf_path = root / ".github" / "workflows" / "claude-eval.yml"
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        if not wf_path.exists() or wf_path.read_text(encoding="utf-8") != WORKFLOW_YAML:
            wf_path.write_text(WORKFLOW_YAML, encoding="utf-8")
            injected_files.append(str(wf_path))

        return {
            "workspace": str(root),
            "slash_commands": [f"/{k.removesuffix('.md')}" for k in SLASH_COMMANDS],
            "workflow": str(wf_path),
            "mcp_config": str(mcp_path),
            "injected_files": injected_files,
        }
