"""Builds an evaluation report from `adk eval` results and gates CI on it.

`adk eval` exits 0 even when cases fail, so this script is the quality gate:
it exits 1 when the pass rate is below --min-pass-rate.

Usage:
  python scripts/eval_report.py --history-dir agents/simpleagent/.adk/eval_history \
      --evalset tests/eval/simpleagent_core.evalset.json --out-dir reports
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

STATUS = {1: "PASSED", 2: "FAILED", 3: "NOT_EVALUATED"}


def _text(content: dict | None) -> str:
    if not content:
        return ""
    return "".join(p.get("text") or "" for p in content.get("parts") or [])


def _md_cell(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text.replace("|", "\\|")


def load_results(history_dir: Path) -> list[dict]:
    cases = []
    for path in sorted(history_dir.glob("*.evalset_result.json")):
        data = json.loads(path.read_text())
        if isinstance(data, str):  # older ADK versions double-encode
            data = json.loads(data)
        cases.extend(data["eval_case_results"])
    return cases


def summarize(cases: list[dict], criteria: dict) -> dict:
    metric_scores: dict[str, list[float]] = {name: [] for name in criteria}
    rubric_scores: dict[str, list[float]] = {}
    rows = []
    for case in sorted(cases, key=lambda c: c["eval_id"]):
        metrics = {}
        for m in case["overall_eval_metric_results"]:
            metrics[m["metric_name"]] = m["score"]
            if m["score"] is not None:
                metric_scores.setdefault(m["metric_name"], []).append(m["score"])
            for r in (m.get("details") or {}).get("rubric_scores") or []:
                if r.get("score") is not None:
                    rubric_scores.setdefault(r["rubric_id"], []).append(r["score"])
        turns = [
            {
                "user": _text(inv["actual_invocation"]["user_content"]),
                "expected": _text((inv.get("expected_invocation") or {}).get("final_response")),
                "actual": _text(inv["actual_invocation"].get("final_response")),
            }
            for inv in case["eval_metric_result_per_invocation"]
        ]
        rows.append(
            {
                "eval_id": case["eval_id"],
                "status": STATUS.get(case["final_eval_status"], str(case["final_eval_status"])),
                "metrics": metrics,
                "turns": turns,
            }
        )

    passed = sum(r["status"] == "PASSED" for r in rows)
    return {
        "total": len(rows),
        "passed": passed,
        "pass_rate": passed / len(rows) if rows else 0.0,
        "metric_means": {k: statistics.fmean(v) for k, v in metric_scores.items() if v},
        "rubric_means": {k: statistics.fmean(v) for k, v in rubric_scores.items()},
        "cases": rows,
    }


def _git_sha() -> str:
    sha = os.getenv("GITHUB_SHA")
    if sha:
        return sha[:7]
    try:
        cmd = ["git", "rev-parse", "--short", "HEAD"]
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()  # noqa: S603
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def render_markdown(summary: dict, criteria: dict, evalset: dict, min_pass_rate: float) -> str:
    gate = "PASS ✅" if summary["pass_rate"] >= min_pass_rate else "FAIL ❌"
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# simpleagent — Evaluation Report",
        "",
        f"- **Generated:** {now}",
        f"- **Commit:** `{_git_sha()}`",
        f"- **Agent model:** `{os.getenv('AGENT_MODEL', 'gemini-2.5-flash')}`",
        f"- **Eval set:** `{evalset['eval_set_id']}` — {evalset.get('description', '')}",
        f"- **Quality gate:** {gate} — {summary['passed']}/{summary['total']} cases passed "
        f"({summary['pass_rate']:.0%}), required ≥ {min_pass_rate:.0%}",
        "",
        "## Metrics",
        "",
        "| Metric | Threshold | Mean score |",
        "|---|---|---|",
    ]
    for name, crit in criteria.items():
        threshold = crit["threshold"] if isinstance(crit, dict) else crit
        mean = summary["metric_means"].get(name)
        lines.append(f"| `{name}` | {threshold} | {'n/a' if mean is None else f'{mean:.2f}'} |")

    if summary["rubric_means"]:
        lines += ["", "### Rubric breakdown", "", "| Rubric | Mean score |", "|---|---|"]
        for rid, mean in summary["rubric_means"].items():
            lines.append(f"| `{rid}` | {mean:.2f} |")

    metric_names = list(criteria)
    lines += [
        "",
        "## Results by case",
        "",
        "| Case | Status | " + " | ".join(f"`{m}`" for m in metric_names) + " |",
        "|---|---|" + "---|" * len(metric_names),
    ]
    for row in summary["cases"]:
        scores = [row["metrics"].get(m) for m in metric_names]
        cells = ["n/a" if s is None else f"{s:.2f}" for s in scores]
        icon = "✅" if row["status"] == "PASSED" else "❌"
        lines.append(f"| `{row['eval_id']}` | {icon} {row['status']} | " + " | ".join(cells) + " |")

    lines += ["", "## Transcripts", ""]
    for row in summary["cases"]:
        lines += [f"### `{row['eval_id']}` — {row['status']}", ""]
        lines += ["| Turn | User | Expected | Actual |", "|---|---|---|---|"]
        for i, turn in enumerate(row["turns"], 1):
            lines.append(
                f"| {i} | {_md_cell(turn['user'])} | {_md_cell(turn['expected'])} "
                f"| {_md_cell(turn['actual'], 400)} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history-dir", type=Path, required=True)
    parser.add_argument("--evalset", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("tests/eval/test_config.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=float(os.getenv("EVAL_MIN_PASS_RATE", "0.9")),
        help="Minimum fraction of eval cases that must pass (LLM judges are noisy).",
    )
    args = parser.parse_args()

    cases = load_results(args.history_dir)
    if not cases:
        print(f"No eval results found in {args.history_dir}", file=sys.stderr)
        return 1

    criteria = json.loads(args.config.read_text())["criteria"]
    evalset = json.loads(args.evalset.read_text())
    summary = summarize(cases, criteria)
    report = render_markdown(summary, criteria, evalset, args.min_pass_rate)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "evaluation_report.md").write_text(report + "\n")
    (args.out_dir / "evaluation_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if step_summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(step_summary, "a") as f:
            f.write(report.split("## Transcripts")[0])

    ok = summary["pass_rate"] >= args.min_pass_rate
    print(
        f"Eval {'PASSED' if ok else 'FAILED'}: {summary['passed']}/{summary['total']} cases "
        f"({summary['pass_rate']:.0%}, required ≥ {args.min_pass_rate:.0%}). "
        f"Report: {args.out_dir / 'evaluation_report.md'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
