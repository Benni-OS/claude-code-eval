"""Tests for TaskSuite YAML/JSON loading, Pass@k math, and deterministic scorers."""

from __future__ import annotations

import json
from pathlib import Path

from claude_code_eval.core.scorers import (
    evaluate_assertion,
    score_ast_valid,
    score_diff_invariant,
    score_regex_absent,
    score_regex_match,
    score_safety_block_rate,
    score_token_efficiency,
    score_tool_sequence,
)
from claude_code_eval.core.task_suite import TaskAssertion, TaskSuite, compute_pass_at_k


def test_pass_at_k_math() -> None:
    assert compute_pass_at_k(10, 0, 1) == 0.0
    assert compute_pass_at_k(10, 10, 1) == 1.0
    assert abs(compute_pass_at_k(10, 5, 1) - 0.5) < 1e-6
    assert compute_pass_at_k(5, 3, 3) == 1.0


def test_builtin_suites_by_category() -> None:
    all_suite = TaskSuite.builtin("all")
    assert len(all_suite.tasks) >= 5
    swe_suite = TaskSuite.builtin("swe")
    assert all(t.category == "swe" for t in swe_suite.tasks)
    assert len(swe_suite.tasks) >= 2


def test_load_json_and_yaml_suites(tmp_path: Path) -> None:
    json_path = tmp_path / "suite.json"
    json_path.write_text(
        json.dumps(
            {
                "name": "custom-json",
                "version": "1.0.0",
                "tasks": [
                    {
                        "task_id": "J-1",
                        "title": "JSON task",
                        "category": "coding",
                        "prompt": "Write hello()",
                        "expected_tools": ["Read", "Edit"],
                        "assertions": [{"kind": "ast_valid", "target": "output"}],
                        "reference_output": "def hello():\n    return 'hi'\n",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    js = TaskSuite.load_from_file(json_path)
    assert js.name == "custom-json"
    assert len(js.tasks) == 1
    assert js.tasks[0].task_id == "J-1"

    yaml_path = tmp_path / "suite.yaml"
    yaml_path.write_text(
        """name: custom-yaml
version: 1.0.0
tasks:
  - task_id: Y-1
    title: YAML task
    category: swe
    prompt: Fix bug
    expected_tools: [Read, Bash]
    max_tokens: 1024
    reference_output: "x = 1"
""",
        encoding="utf-8",
    )
    ys = TaskSuite.load_from_file(yaml_path)
    assert ys.name == "custom-yaml"
    assert len(ys.tasks) == 1
    assert ys.tasks[0].expected_tools == ["Read", "Bash"]
    assert ys.tasks[0].max_tokens == 1024


def test_ast_valid_scorer() -> None:
    assert score_ast_valid("def f(x):\n    return x + 1\n").passed is True
    assert score_ast_valid("def f(:\n").passed is False
    assert score_ast_valid("   ").passed is False


def test_regex_and_diff_scorers() -> None:
    assert score_regex_match("def paginate(a):", r"def\s+paginate\(").passed is True
    assert score_regex_absent("return x + 1", r"eval\(").passed is True
    assert score_regex_absent("eval('1+1')", r"eval\(").passed is False
    diff_ok = score_diff_invariant("a = 1\nb = 2\n", ["a = 1", "b = 2"])
    assert diff_ok.passed is True and diff_ok.score == 1.0
    diff_partial = score_diff_invariant("a = 1\n", ["a = 1", "b = 2"])
    assert diff_partial.passed is False and diff_partial.score == 0.5


def test_tool_sequence_and_token_efficiency_and_safety() -> None:
    assert score_tool_sequence(["Read", "Grep", "Edit", "Bash"], ["Read", "Edit", "Bash"]).passed is True
    assert score_tool_sequence(["Edit", "Read"], ["Read", "Edit"]).passed is False

    eff_ok = score_token_efficiency(400, 2000, 0.0, 0.05)
    assert eff_ok.passed is True and eff_ok.score >= 0.5

    eff_over = score_token_efficiency(5000, 2000, 0.0, 0.05)
    assert eff_over.passed is False and eff_over.score < 0.5

    assert score_safety_block_rate(10, 10) == 1.0
    assert score_safety_block_rate(7, 10) == 0.7

    res = evaluate_assertion(TaskAssertion(kind="contains", expected="ok"), {"output": "status: ok", "tools": []})
    assert res.passed is True

    unknown_res = evaluate_assertion(TaskAssertion(kind="nonexistent_kind", expected="x"), {"output": "x", "tools": []})
    assert unknown_res.passed is False and unknown_res.score == 0.0

    suite_dict = TaskSuite.builtin("hook").to_dict()
    assert suite_dict["name"] == "builtin-hook"
    assert len(suite_dict["tasks"]) >= 1

