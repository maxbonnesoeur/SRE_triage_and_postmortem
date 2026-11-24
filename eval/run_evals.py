"""Evaluation runner supporting deterministic offline checks and live `adk eval`.

Usage:
    python3 -m eval.run_evals --mode offline
    python3 -m eval.run_evals --mode adk
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from sre_triage_agent.memory.incident_memory import IncidentMemoryStore
from sre_triage_agent.tools.telemetry_tools import (
    get_recent_deployments,
    get_service_metrics,
    list_active_alerts,
    query_service_logs,
    search_runbooks,
)

EVAL_DIR = Path(__file__).parent
EVALSET_PATH = EVAL_DIR / "sre_triage.evalset.json"
CONFIG_PATH = EVAL_DIR / "test_config.json"


def run_offline_evaluations() -> dict[str, Any]:
    """Validate evalset schema, golden tool outputs, and memory recall without LLM calls."""
    evalset = json.loads(EVALSET_PATH.read_text(encoding="utf-8"))
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    checks: list[dict[str, Any]] = []

    # Check 1: Evalset structure
    cases = evalset.get("eval_cases", [])
    checks.append(
        {
            "name": "evalset_schema_valid",
            "passed": len(cases) >= 3 and "criteria" in config,
            "details": f"{len(cases)} eval cases loaded",
        }
    )

    # Check 2: Golden scenario data completeness (payments-api SEV1)
    alerts = list_active_alerts("payments-api")
    logs = query_service_logs("payments-api", level="ERROR")
    metrics = get_service_metrics("payments-api")
    deploys = get_recent_deployments("payments-api")
    runbooks = search_runbooks("payments-api", "503 connection pool")
    checks.append(
        {
            "name": "payments_api_signal_correlation",
            "passed": (
                alerts["count"] == 1
                and logs["count"] >= 2
                and metrics["metrics"]["db_pool_saturation_pct"] == 100.0
                and deploys["deployments"][0]["version"] == "v2.18.4"
                and runbooks["count"] >= 1
            ),
            "details": "All 5 diagnostic signals return expected SEV1 evidence",
        }
    )

    # Check 3: Institutional memory recall
    mem = IncidentMemoryStore(db_path=":memory:", seed=True)
    recalled = mem.search(service_name="payments-api", query="connection pool")
    checks.append(
        {
            "name": "long_term_memory_recall",
            "passed": len(recalled) >= 1 and recalled[0]["incident_id"] == "INC-2026-0198",
            "details": f"Top recalled incident: {recalled[0]['incident_id'] if recalled else 'none'}",
        }
    )

    passed_count = sum(1 for c in checks if c["passed"])
    score = round(passed_count / len(checks), 2) if checks else 0.0
    return {
        "mode": "offline",
        "score": score,
        "passed": passed_count,
        "total": len(checks),
        "checks": checks,
    }


def run_adk_eval() -> int:
    """Delegate live trajectory + response evaluation to the official `adk eval` CLI."""
    cmd = [
        "adk",
        "eval",
        "sre_triage_agent",
        str(EVALSET_PATH),
        "--config_file_path",
        str(CONFIG_PATH),
    ]
    return subprocess.call(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SRE Triage Agent evaluations.")
    parser.add_argument(
        "--mode",
        choices=["offline", "adk"],
        default="offline",
        help="Choose deterministic offline checks (CI-safe) or live `adk eval`.",
    )
    args = parser.parse_args()

    if args.mode == "offline":
        report = run_offline_evaluations()
        print(json.dumps(report, indent=2))
        if report["passed"] != report["total"]:
            sys.exit(1)
    else:
        sys.exit(run_adk_eval())


if __name__ == "__main__":
    main()
