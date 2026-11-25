"""Core evaluation, red-teaming, cryptographic receipt, and CI gate modules."""

from .ci_gate import CIGate, CIGateResult
from .eval_runner import EvalRunner, EvalSuiteReport, TaskRunResult
from .injector import EvalInjector
from .receipt_ledger import GENESIS_HASH, EvalReceipt, ReceiptLedger
from .redteam_suite import ProbeResult, RedTeamProbe, RedTeamReport, RedTeamSuite
from .scorers import (
    ScoreResult,
    evaluate_assertion,
    score_ast_valid,
    score_diff_invariant,
    score_regex_absent,
    score_regex_match,
    score_safety_block_rate,
    score_token_efficiency,
    score_tool_sequence,
)
from .task_suite import EvalTask, TaskAssertion, TaskSuite, compute_pass_at_k

__all__ = [
    "CIGate",
    "CIGateResult",
    "EvalInjector",
    "EvalReceipt",
    "EvalRunner",
    "EvalSuiteReport",
    "EvalTask",
    "GENESIS_HASH",
    "ProbeResult",
    "ReceiptLedger",
    "RedTeamProbe",
    "RedTeamReport",
    "RedTeamSuite",
    "ScoreResult",
    "TaskAssertion",
    "TaskRunResult",
    "TaskSuite",
    "compute_pass_at_k",
    "evaluate_assertion",
    "score_ast_valid",
    "score_diff_invariant",
    "score_regex_absent",
    "score_regex_match",
    "score_safety_block_rate",
    "score_token_efficiency",
    "score_tool_sequence",
]
