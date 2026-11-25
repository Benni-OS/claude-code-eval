"""Benchmark offline eval replay and red-team probe throughput across multiple scales."""

from __future__ import annotations

import json

from claude_code_eval.tools.bench_matrix import run_matrix


def main() -> None:
    res = run_matrix([100, 500, 1000])
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
