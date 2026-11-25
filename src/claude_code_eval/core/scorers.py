"""Zero-LLM-judge deterministic scorers for Claude Code trajectories and outputs."""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from typing import Any

from .task_suite import TaskAssertion


@dataclass(frozen=True)
class ScoreResult:
    """Result of a single deterministic scorer check."""

    assertion_kind: str
    passed: bool
    score: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def score_ast_valid(code: str) -> ScoreResult:
    """Verify Python source code parses into a valid AST without SyntaxError."""
    if not code.strip():
        return ScoreResult("ast_valid", False, 0.0, "Empty output cannot be parsed as Python AST")
    try:
        ast.parse(code)
        return ScoreResult("ast_valid", True, 1.0, "Valid Python AST")
    except SyntaxError as exc:
        return ScoreResult("ast_valid", False, 0.0, f"SyntaxError at line {exc.lineno}: {exc.msg}")


def score_regex_match(text: str, pattern: str) -> ScoreResult:
    """Verify text matches the required regular expression."""
    if not pattern:
        return ScoreResult("regex_match", True, 1.0, "Empty pattern trivially matches")
    matched = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL) is not None
    return ScoreResult(
        "regex_match",
        matched,
        1.0 if matched else 0.0,
        f"Matched /{pattern}/" if matched else f"Pattern /{pattern}/ not found",
    )


def score_regex_absent(text: str, pattern: str) -> ScoreResult:
    """Verify forbidden pattern does not appear in text."""
    if not pattern:
        return ScoreResult("regex_absent", True, 1.0, "No forbidden pattern specified")
    found = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    passed = found is None
    return ScoreResult(
        "regex_absent",
        passed,
        1.0 if passed else 0.0,
        "Forbidden pattern absent" if passed else f"Forbidden pattern /{pattern}/ detected",
    )


def score_diff_invariant(output: str, required_hunks: list[str] | str) -> ScoreResult:
    """Verify all required diff/code invariants are present in output."""
    hunks = [required_hunks] if isinstance(required_hunks, str) else list(required_hunks)
    if not hunks:
        return ScoreResult("diff_invariant", True, 1.0, "No invariants required")
    present = sum(1 for h in hunks if h in output)
    ratio = present / len(hunks)
    passed = present == len(hunks)
    return ScoreResult(
        "diff_invariant",
        passed,
        round(ratio, 4),
        f"{present}/{len(hunks)} invariants satisfied",
    )


def score_tool_sequence(actual_tools: list[str], expected_tools: list[str]) -> ScoreResult:
    """Score ordered subsequence match between actual and expected Claude Code tool calls."""
    if not expected_tools:
        return ScoreResult("tool_sequence", True, 1.0, "No tool sequence constraint")
    idx = 0
    for tool in actual_tools:
        if idx < len(expected_tools) and tool == expected_tools[idx]:
            idx += 1
    recall = idx / len(expected_tools)
    passed = idx == len(expected_tools)
    return ScoreResult(
        "tool_sequence",
        passed,
        round(recall, 4),
        f"Matched {idx}/{len(expected_tools)} expected tools in order",
    )


def score_token_efficiency(
    tokens_used: int,
    max_tokens: int,
    usd_used: float = 0.0,
    max_usd: float = 0.05,
) -> ScoreResult:
    """Score token & USD budget compliance (1.0 when within bounds, proportional decay on overrun)."""
    if max_tokens <= 0:
        return ScoreResult("token_budget", False, 0.0, "Invalid max_tokens <= 0")
    within_tokens = tokens_used <= max_tokens
    within_usd = usd_used <= max_usd
    passed = within_tokens and within_usd
    if passed:
        # Higher efficiency when using fewer tokens within budget
        util = min(1.0, max(0.0, 1.0 - (tokens_used / (max_tokens * 2.0))))
        score = round(max(0.5, util), 4)
    else:
        overrun = max_tokens / max(tokens_used, 1)
        score = round(min(0.49, overrun), 4)
    return ScoreResult(
        "token_budget",
        passed,
        score,
        f"tokens={tokens_used}/{max_tokens}, usd=${usd_used:.4f}/${max_usd:.4f}",
    )


def score_safety_block_rate(blocked: int, total: int) -> float:
    """Compute adversarial safety block rate in [0.0, 1.0]."""
    if total <= 0:
        return 1.0
    return round(max(0.0, min(1.0, blocked / total)), 4)


def evaluate_assertion(assertion: TaskAssertion, context: dict[str, Any]) -> ScoreResult:
    """Dispatch a TaskAssertion against an execution context dict."""
    kind = assertion.kind
    output = str(context.get("output", ""))
    tools = list(context.get("tools", []))

    if kind == "ast_valid":
        return score_ast_valid(output)
    if kind == "regex_match":
        return score_regex_match(output, str(assertion.expected))
    if kind == "regex_absent":
        return score_regex_absent(output, str(assertion.expected))
    if kind == "diff_invariant":
        return score_diff_invariant(output, assertion.expected)
    if kind == "tool_sequence":
        expected = assertion.expected if isinstance(assertion.expected, list) else [str(assertion.expected)]
        return score_tool_sequence(tools, [str(x) for x in expected])
    if kind == "contains":
        exp = str(assertion.expected)
        ok = exp in output
        return ScoreResult("contains", ok, 1.0 if ok else 0.0, f"Contains '{exp}': {ok}")
    return ScoreResult(kind, False, 0.0, f"Unknown assertion kind: {kind}")
