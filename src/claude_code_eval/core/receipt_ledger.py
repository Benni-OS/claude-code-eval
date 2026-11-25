"""SHA-256 chained cryptographic evaluation receipt ledger & reproducible verifier."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS_HASH = "0" * 64


def canonical_digest(payload: Any) -> str:
    """Compute deterministic SHA-256 hex digest of any JSON-serializable payload."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EvalReceipt:
    """Immutable SHA-256 chained cryptographic receipt for an eval or red-team run."""

    seq: int
    timestamp: str
    run_kind: str  # eval | redteam | gate
    suite_name: str
    prev_hash: str
    input_digest: str
    ruleset_digest: str
    output_digest: str
    summary: dict[str, Any]
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def compute_hash(
        cls,
        seq: int,
        timestamp: str,
        run_kind: str,
        suite_name: str,
        prev_hash: str,
        input_digest: str,
        ruleset_digest: str,
        output_digest: str,
        summary: dict[str, Any],
    ) -> str:
        body = {
            "seq": seq,
            "timestamp": timestamp,
            "run_kind": run_kind,
            "suite_name": suite_name,
            "prev_hash": prev_hash,
            "input_digest": input_digest,
            "ruleset_digest": ruleset_digest,
            "output_digest": output_digest,
            "summary": summary,
        }
        return canonical_digest(body)


class ReceiptLedger:
    """Append-only JSONL ledger storing SHA-256 chained EvalReceipts."""

    def __init__(self, workspace: str | Path = ".") -> None:
        self.workspace = Path(workspace)
        self.ledger_dir = self.workspace / ".claude-eval"
        self.ledger_path = self.ledger_dir / "receipts.jsonl"

    def _read_all(self) -> list[EvalReceipt]:
        if not self.ledger_path.exists():
            return []
        receipts: list[EvalReceipt] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            receipts.append(EvalReceipt(**data))
        return receipts

    def list_receipts(self, limit: int = 50) -> list[EvalReceipt]:
        all_items = self._read_all()
        return all_items[-limit:] if limit > 0 else all_items

    def append(
        self,
        run_kind: str,
        suite_name: str,
        input_payload: Any,
        ruleset_payload: Any,
        output_payload: Any,
        summary: dict[str, Any],
    ) -> EvalReceipt:
        self.ledger_dir.mkdir(parents=True, exist_ok=True)
        existing = self._read_all()
        seq = len(existing)
        prev_hash = existing[-1].receipt_hash if existing else GENESIS_HASH
        ts = datetime.now(timezone.utc).isoformat()
        in_dig = canonical_digest(input_payload)
        rule_dig = canonical_digest(ruleset_payload)
        out_dig = canonical_digest(output_payload)
        r_hash = EvalReceipt.compute_hash(
            seq=seq,
            timestamp=ts,
            run_kind=run_kind,
            suite_name=suite_name,
            prev_hash=prev_hash,
            input_digest=in_dig,
            ruleset_digest=rule_dig,
            output_digest=out_dig,
            summary=summary,
        )
        receipt = EvalReceipt(
            seq=seq,
            timestamp=ts,
            run_kind=run_kind,
            suite_name=suite_name,
            prev_hash=prev_hash,
            input_digest=in_dig,
            ruleset_digest=rule_dig,
            output_digest=out_dig,
            summary=summary,
            receipt_hash=r_hash,
        )
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")
        return receipt

    def verify_chain(self) -> dict[str, Any]:
        """Verify GENESIS_HASH linkage and SHA-256 integrity across the entire ledger."""
        receipts = self._read_all()
        if not receipts:
            return {
                "valid": True,
                "count": 0,
                "genesis_hash": GENESIS_HASH,
                "head_hash": GENESIS_HASH,
                "errors": [],
            }

        errors: list[str] = []
        expected_prev = GENESIS_HASH
        for idx, r in enumerate(receipts):
            if r.seq != idx:
                errors.append(f"seq_mismatch at index {idx}: got {r.seq}")
            if r.prev_hash != expected_prev:
                errors.append(f"prev_hash_mismatch at seq {idx}: expected {expected_prev}, got {r.prev_hash}")
            recomputed = EvalReceipt.compute_hash(
                seq=r.seq,
                timestamp=r.timestamp,
                run_kind=r.run_kind,
                suite_name=r.suite_name,
                prev_hash=r.prev_hash,
                input_digest=r.input_digest,
                ruleset_digest=r.ruleset_digest,
                output_digest=r.output_digest,
                summary=r.summary,
            )
            if recomputed != r.receipt_hash:
                errors.append(f"receipt_hash_tampered at seq {idx}: expected {recomputed}, got {r.receipt_hash}")
            expected_prev = r.receipt_hash

        return {
            "valid": len(errors) == 0,
            "count": len(receipts),
            "genesis_hash": GENESIS_HASH,
            "head_hash": receipts[-1].receipt_hash,
            "errors": errors,
        }
