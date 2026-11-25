"""Declarative YAML/JSON benchmark task loader & built-in Claude Code SWE/coding/hook task suites."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def compute_pass_at_k(n: int, c: int, k: int) -> float:
    """Compute unbiased Pass@k estimator: 1 - C(n - c, k) / C(n, k)."""
    if n <= 0 or k <= 0:
        return 0.0
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return 1.0 - (math.comb(n - c, k) / math.comb(n, k))


@dataclass(frozen=True)
class TaskAssertion:
    """A single deterministic assertion evaluated against a task trajectory or output."""

    kind: str  # ast_valid | regex_match | regex_absent | diff_invariant | tool_sequence | contains
    target: str = "output"
    expected: Any = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalTask:
    """Declarative benchmark task with token/USD budget bounds and deterministic assertions."""

    task_id: str
    title: str
    category: str  # swe | coding | hook | mcp
    prompt: str
    expected_tools: list[str] = field(default_factory=list)
    assertions: list[TaskAssertion] = field(default_factory=list)
    max_tokens: int = 4096
    max_usd: float = 0.05
    pass_k: int = 1
    reference_output: str = ""
    reference_trajectory: list[str] = field(default_factory=list)
    reference_tokens: int = 512
    reference_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["assertions"] = [a.to_dict() for a in self.assertions]
        return data


def _parse_scalar(raw: str) -> Any:
    val = raw.strip()
    if not val:
        return ""
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    low = val.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none", "~"):
        return None
    try:
        if "." in val:
            return float(val)
        return int(val)
    except ValueError:
        pass
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in inner.split(",")]
    return val


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse a clean subset of YAML (mappings, lists of dicts/scalars) with zero dependencies."""
    lines = [
        ln.rstrip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        return {}

    def _indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def _parse_block(idx: int, base_indent: int) -> tuple[Any, int]:
        if idx >= len(lines):
            return {}, idx
        stripped = lines[idx].lstrip(" ")
        if stripped.startswith("- "):
            items: list[Any] = []
            while idx < len(lines):
                cur_ind = _indent(lines[idx])
                cur_str = lines[idx].lstrip(" ")
                if cur_ind < base_indent or not cur_str.startswith("- "):
                    break
                after_dash = cur_str[2:].strip()
                if ":" in after_dash and not after_dash.startswith(("'", '"')):
                    k, _, v = after_dash.partition(":")
                    obj: dict[str, Any] = {}
                    v_str = v.strip()
                    if v_str:
                        obj[k.strip()] = _parse_scalar(v_str)
                    else:
                        child, idx = _parse_block(idx + 1, cur_ind + 4)
                        obj[k.strip()] = child
                        idx -= 1
                    idx += 1
                    while idx < len(lines) and _indent(lines[idx]) > cur_ind:
                        sub_str = lines[idx].lstrip(" ")
                        if sub_str.startswith("- "):
                            break
                        sk, _, sv = sub_str.partition(":")
                        sv_str = sv.strip()
                        if sv_str:
                            obj[sk.strip()] = _parse_scalar(sv_str)
                            idx += 1
                        else:
                            child, idx = _parse_block(idx + 1, _indent(lines[idx]) + 2)
                            obj[sk.strip()] = child
                    items.append(obj)
                else:
                    items.append(_parse_scalar(after_dash))
                    idx += 1
            return items, idx

        mapping: dict[str, Any] = {}
        while idx < len(lines):
            cur_ind = _indent(lines[idx])
            if cur_ind < base_indent:
                break
            cur_str = lines[idx].lstrip(" ")
            if cur_str.startswith("- "):
                break
            if ":" not in cur_str:
                idx += 1
                continue
            k, _, v = cur_str.partition(":")
            v_str = v.strip()
            if v_str:
                mapping[k.strip()] = _parse_scalar(v_str)
                idx += 1
            else:
                child, idx = _parse_block(idx + 1, cur_ind + 2)
                mapping[k.strip()] = child
        return mapping, idx

    parsed, _ = _parse_block(0, _indent(lines[0]))
    return parsed if isinstance(parsed, dict) else {"tasks": parsed}


def _builtin_tasks() -> list[EvalTask]:
    return [
        EvalTask(
            task_id="SWE-001",
            title="Fix off-by-one pagination slice in Python API handler",
            category="swe",
            prompt="Inspect paginate() and fix the off-by-one slice boundary while preserving AST validity.",
            expected_tools=["Read", "Edit", "Bash"],
            assertions=[
                TaskAssertion(kind="ast_valid", target="output", description="Generated Python must parse cleanly"),
                TaskAssertion(kind="regex_match", target="output", expected=r"def\s+paginate\(", description="Function signature preserved"),
                TaskAssertion(kind="diff_invariant", target="output", expected=["start = (page - 1) * page_size"], description="Correct 1-indexed offset"),
                TaskAssertion(kind="tool_sequence", target="tools", expected=["Read", "Edit", "Bash"], description="Expected Read->Edit->Bash workflow"),
            ],
            max_tokens=2048,
            max_usd=0.03,
            reference_output=(
                "def paginate(items: list, page: int, page_size: int) -> list:\n"
                "    if page < 1 or page_size < 1:\n"
                "        return []\n"
                "    start = (page - 1) * page_size\n"
                "    return items[start : start + page_size]\n"
            ),
            reference_trajectory=["Read", "Edit", "Bash"],
            reference_tokens=420,
            reference_usd=0.0,
        ),
        EvalTask(
            task_id="SWE-002",
            title="Add thread-safe LRU cache eviction with Lock",
            category="swe",
            prompt="Implement a thread-safe bounded cache using threading.Lock and OrderedDict.",
            expected_tools=["Read", "Write", "Bash"],
            assertions=[
                TaskAssertion(kind="ast_valid", target="output", description="Valid Python AST"),
                TaskAssertion(kind="regex_match", target="output", expected=r"threading\.Lock", description="Uses threading.Lock"),
                TaskAssertion(kind="regex_absent", target="output", expected=r"eval\(|exec\(", description="No unsafe dynamic execution"),
                TaskAssertion(kind="tool_sequence", target="tools", expected=["Read", "Write", "Bash"], description="Read->Write->Bash"),
            ],
            max_tokens=3072,
            max_usd=0.04,
            reference_output=(
                "import threading\n"
                "from collections import OrderedDict\n\n"
                "class SafeLRU:\n"
                "    def __init__(self, capacity: int = 128) -> None:\n"
                "        self._cap = capacity\n"
                "        self._lock = threading.Lock()\n"
                "        self._data: OrderedDict = OrderedDict()\n"
            ),
            reference_trajectory=["Read", "Write", "Bash"],
            reference_tokens=560,
            reference_usd=0.0,
        ),
        EvalTask(
            task_id="CODE-001",
            title="Refactor JSON parser with strict schema validation",
            category="coding",
            prompt="Write a strict JSON payload validator raising ValueError on missing required keys.",
            expected_tools=["Read", "Edit"],
            assertions=[
                TaskAssertion(kind="ast_valid", target="output", description="Valid Python AST"),
                TaskAssertion(kind="regex_match", target="output", expected=r"raise\s+ValueError", description="Raises ValueError on invalid input"),
                TaskAssertion(kind="tool_sequence", target="tools", expected=["Read", "Edit"], description="Read->Edit"),
            ],
            max_tokens=1536,
            max_usd=0.02,
            reference_output=(
                "import json\n\n"
                "def parse_strict(raw: str, required: tuple[str, ...]) -> dict:\n"
                "    data = json.loads(raw)\n"
                "    for key in required:\n"
                "        if key not in data:\n"
                "            raise ValueError(f'Missing key: {key}')\n"
                "    return data\n"
            ),
            reference_trajectory=["Read", "Edit"],
            reference_tokens=310,
            reference_usd=0.0,
        ),
        EvalTask(
            task_id="HOOK-001",
            title="Enforce PreToolUse hook denial on destructive shell rm -rf",
            category="hook",
            prompt="Verify PreToolUse hook emits permissionDecision=deny for rm -rf /.",
            expected_tools=["Bash"],
            assertions=[
                TaskAssertion(kind="regex_match", target="output", expected=r'"permissionDecision"\s*:\s*"deny"', description="Hook denies destructive command"),
                TaskAssertion(kind="regex_absent", target="output", expected=r'"permissionDecision"\s*:\s*"allow"', description="Must not allow destructive command"),
                TaskAssertion(kind="tool_sequence", target="tools", expected=["Bash"], description="Hook check via Bash"),
            ],
            max_tokens=1024,
            max_usd=0.01,
            reference_output='{"hookSpecificOutput": {"permissionDecision": "deny", "reason": "Destructive rm -rf blocked"}}',
            reference_trajectory=["Bash"],
            reference_tokens=180,
            reference_usd=0.0,
        ),
        EvalTask(
            task_id="MCP-001",
            title="Validate JSON-RPC 2.0 MCP tools/list response contract",
            category="mcp",
            prompt="Ensure MCP server tools/list returns jsonrpc 2.0 with non-empty tools array.",
            expected_tools=["Bash"],
            assertions=[
                TaskAssertion(kind="regex_match", target="output", expected=r'"jsonrpc"\s*:\s*"2\.0"', description="JSON-RPC 2.0 header"),
                TaskAssertion(kind="regex_match", target="output", expected=r'"tools"\s*:\s*\[', description="Tools array present"),
                TaskAssertion(kind="tool_sequence", target="tools", expected=["Bash"], description="MCP probe"),
            ],
            max_tokens=1024,
            max_usd=0.01,
            reference_output='{"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "eval_run_suite"}]}}',
            reference_trajectory=["Bash"],
            reference_tokens=200,
            reference_usd=0.0,
        ),
    ]


class TaskSuite:
    """Collection of declarative EvalTasks with YAML/JSON loading and built-in suites."""

    def __init__(self, name: str, version: str = "1.0.0", tasks: list[EvalTask] | None = None) -> None:
        self.name = name
        self.version = version
        self.tasks: list[EvalTask] = tasks or []

    @classmethod
    def builtin(cls, category: str | None = None) -> "TaskSuite":
        tasks = _builtin_tasks()
        if category and category != "all":
            tasks = [t for t in tasks if t.category == category]
        return cls(name=f"builtin-{category or 'all'}", version="0.1.0", tasks=tasks)

    @classmethod
    def load_from_file(cls, path: str | Path) -> "TaskSuite":
        p = Path(path)
        raw = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":
            data = json.loads(raw)
        else:
            data = parse_simple_yaml(raw)

        tasks: list[EvalTask] = []
        for item in data.get("tasks", []):
            assertions = [
                TaskAssertion(
                    kind=a.get("kind", "contains"),
                    target=a.get("target", "output"),
                    expected=a.get("expected", ""),
                    description=a.get("description", ""),
                )
                for a in item.get("assertions", [])
            ]
            tasks.append(
                EvalTask(
                    task_id=str(item["task_id"]),
                    title=str(item.get("title", item["task_id"])),
                    category=str(item.get("category", "coding")),
                    prompt=str(item.get("prompt", "")),
                    expected_tools=list(item.get("expected_tools", [])),
                    assertions=assertions,
                    max_tokens=int(item.get("max_tokens", 4096)),
                    max_usd=float(item.get("max_usd", 0.05)),
                    pass_k=int(item.get("pass_k", 1)),
                    reference_output=str(item.get("reference_output", "")),
                    reference_trajectory=list(item.get("reference_trajectory", item.get("expected_tools", []))),
                    reference_tokens=int(item.get("reference_tokens", 512)),
                    reference_usd=float(item.get("reference_usd", 0.0)),
                )
            )
        return cls(
            name=str(data.get("name", p.stem)),
            version=str(data.get("version", "1.0.0")),
            tasks=tasks,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "tasks": [t.to_dict() for t in self.tasks],
        }
