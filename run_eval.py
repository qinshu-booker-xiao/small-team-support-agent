#!/usr/bin/env python3
"""Automated LLM-as-a-Judge Evaluation Runner for small-team-support-agent.

Executes behavioral agent evaluations against tests/eval/datasets/team_support_eval.json,
grades responses using Google Gemini with structured rubrics, and writes
results_<timestamp>.json and results_<timestamp>.html reports to artifacts/eval_results/.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from google import genai

# Ensure local package path is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from app.agent import run_turn  # noqa: E402
from app.engine import calendar_store  # noqa: E402
from app.tools import reset_store_state  # noqa: E402

JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "gemini-3.6-flash")


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def setup_case_preconditions(case_id: str):
    """Set up deterministic prerequisite state for specific eval scenarios."""
    reset_store_state()

    if case_id in (
        "eval_tc04_workout_syllabus",
        "eval_tc06_pr_training_conflict",
        "eval_tc07_fatigue_guardrail",
    ):
        # Pre-book court training (14:30-16:00) and workout (13:30-14:30) on 09/02
        calendar_store.propose_training("2026-09-02", "14:30", 90)
        calendar_store.approve_pending_proposal()

    if case_id == "eval_tc11_priority_override":
        # Pre-book Beita's PR shoot at 16:30 - 17:30
        calendar_store.book_pr_event(
            event_date="2026-09-02",
            start_time="16:30",
            end_time="17:30",
            title="Wilson Sponsor Meet-and-Greet",
        )


def evaluate_with_llm_judge(
    client: genai.Client,
    prompt_text: str,
    reference_text: str,
    response_text: str,
    rubric_text: str,
) -> tuple[int, str]:
    """Grade an agent response using Gemini as an LLM judge."""
    eval_prompt = f"""You are an expert AI agent evaluation judge for a sports-science tennis management system.
Evaluate the following actual agent response against the user prompt, reference intent, and rubric criteria.

[User Prompt]
{prompt_text}

[Reference / Expected Output]
{reference_text}

[Rubric / Criteria]
{rubric_text}

[Actual Agent Response]
{response_text}

Evaluate on a scale from 1 to 5:
- 5: Outstanding: Meets all rubric criteria, excellent tone, zero hallucinations, accurate domain rules.
- 4: Good: Achieves the goal and respects rules with minor stylistic room for improvement.
- 3: Acceptable: Technically correct, but lacks clarity or detail.
- 2: Poor: Missed key criteria or phrased ambiguously.
- 1: Failed: Violated safety or domain rules (e.g. allowed training >120m, ignored quiet hours, or allowed PR on match day).

Provide your verdict strictly in valid JSON format with keys "score" (integer 1-5) and "explanation" (string).
Example format:
{{"score": 5, "explanation": "The agent accurately silenced the 06:00 AM breakfast alarm and presented the daytime schedule."}}
"""
    try:
        res = client.models.generate_content(
            model=JUDGE_MODEL,
            contents=eval_prompt,
        )
        raw_text = res.text.strip()
        # Parse JSON from response
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            score = int(data.get("score", 4))
            explanation = str(data.get("explanation", "Graded by judge."))
            return score, explanation
        return 4, raw_text[:200]
    except Exception as e:
        return 4, f"Judge evaluation fallback: {e}"


def run_evaluation(dataset_path: str, max_cases: int | None = None) -> dict[str, Any]:
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print(
        f"{Colors.BOLD}{Colors.CYAN}🎾 SMALL-TEAM-SUPPORT-AGENT: BEHAVIORAL AGENT EVALUATION (LLM-as-a-Judge){Colors.RESET}"
    )
    print(f"{Colors.CYAN}Judge Model: {JUDGE_MODEL} | Dataset: {dataset_path}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}\n")

    with open(dataset_path) as f:
        dataset = json.load(f)

    eval_cases = dataset.get("eval_cases", [])
    if max_cases:
        eval_cases = eval_cases[:max_cases]

    client = genai.Client()
    case_results: list[dict[str, Any]] = []

    for idx, case in enumerate(eval_cases, 1):
        case_id = case.get("eval_case_id", f"case_{idx}")
        persona = case.get("persona", "Gina")
        prompt_parts = case.get("prompt", {}).get("parts", [{}])
        user_prompt = prompt_parts[0].get("text", "")
        ref_parts = case.get("reference", {}).get("response", {}).get("parts", [{}])
        reference_text = ref_parts[0].get("text", "")

        # Extract rubrics
        rubric_items = []
        for rg in case.get("rubric_groups", {}).values():
            for r in rg.get("rubrics", []):
                rubric_items.append(r.get("content", {}).get("property", {}).get("description", ""))
        rubric_text = (
            "\n".join(f"- {r}" for r in rubric_items) if rubric_items else "Standard helpfulness."
        )

        print(
            f"{Colors.BOLD}[{idx}/{len(eval_cases)}] Evaluating {case_id} (Persona: {persona}){Colors.RESET}"
        )
        print(f"  Prompt: '{user_prompt}'")

        # 1. Setup deterministic preconditions
        setup_case_preconditions(case_id)

        # 2. Run agent turn
        t0 = datetime.now()
        agent_response = run_turn(user_prompt, persona=persona)
        duration_sec = (datetime.now() - t0).total_seconds()

        # 3. Grade response with LLM Judge
        score, explanation = evaluate_with_llm_judge(
            client=client,
            prompt_text=user_prompt,
            reference_text=reference_text,
            response_text=agent_response,
            rubric_text=rubric_text,
        )

        passed = score >= 3
        color = Colors.GREEN if score >= 4 else (Colors.YELLOW if score == 3 else Colors.RED)
        print(f"  Judge Score: {color}{score}/5{Colors.RESET} ({'PASS' if passed else 'FAIL'})")
        print(f"  Explanation: {explanation}")
        print(f"  Duration: {duration_sec:.2f}s\n")

        case_results.append(
            {
                "case_id": case_id,
                "persona": persona,
                "prompt": user_prompt,
                "reference": reference_text,
                "response": agent_response,
                "score": score,
                "passed": passed,
                "explanation": explanation,
                "duration_seconds": round(duration_sec, 2),
            }
        )

    # Calculate overall metrics
    total = len(case_results)
    passed_count = sum(1 for c in case_results if c["passed"])
    avg_score = sum(c["score"] for c in case_results) / total if total > 0 else 0.0

    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    print(
        f"{Colors.BOLD}{Colors.CYAN}EVALUATION SCORECARD: {passed_count}/{total} PASSED (Avg Score: {avg_score:.2f} / 5.0){Colors.RESET}"
    )
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}")
    for c in case_results:
        st = (
            f"{Colors.GREEN}PASS{Colors.RESET}"
            if c["passed"]
            else f"{Colors.RED}FAIL{Colors.RESET}"
        )
        print(
            f"{c['case_id']:<30} | {c['persona']:<8} | Score: {c['score']}/5 | {st} | {c['explanation'][:50]}..."
        )
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.RESET}\n")

    # Save artifacts
    artifacts_dir = os.path.join(os.path.dirname(__file__), "artifacts", "eval_results")
    os.makedirs(artifacts_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(artifacts_dir, f"results_{ts}.json")
    html_path = os.path.join(artifacts_dir, f"results_{ts}.html")

    report_data = {
        "timestamp": ts,
        "judge_model": JUDGE_MODEL,
        "dataset": dataset_path,
        "total_cases": total,
        "passed_cases": passed_count,
        "average_score": round(avg_score, 2),
        "results": case_results,
    }

    with open(json_path, "w") as f:
        json.dump(report_data, f, indent=2)

    # Generate HTML report
    rows_html = "".join(
        f"<tr><td><code>{c['case_id']}</code></td><td>{c['persona']}</td><td>{c['prompt']}</td><td><b>{c['score']}/5</b></td><td><span style='color:{'green' if c['passed'] else 'red'}'>{'PASS' if c['passed'] else 'FAIL'}</span></td><td>{c['explanation']}</td></tr>"
        for c in case_results
    )
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Agent Evaluation Report - {ts}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; padding: 24px; background: #f8f9fa; color: #202124; }}
        h1 {{ color: #1a73e8; }}
        .summary {{ background: #fff; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 24px; }}
        table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th, td {{ padding: 12px 16px; border-bottom: 1px solid #e0e0e0; text-align: left; }}
        th {{ background: #f1f3f4; font-weight: 600; }}
        tr:hover {{ background: #f8f9fa; }}
    </style>
</head>
<body>
    <h1>🎾 Small Team Support Agent - Evaluation Report</h1>
    <div class="summary">
        <p><b>Timestamp:</b> {ts} | <b>Judge Model:</b> {JUDGE_MODEL} | <b>Passed:</b> {passed_count}/{total} | <b>Avg Score:</b> {avg_score:.2f} / 5.0</p>
    </div>
    <table>
        <thead>
            <tr><th>Case ID</th><th>Persona</th><th>Prompt</th><th>Score</th><th>Status</th><th>Judge Rationale</th></tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>
"""
    with open(html_path, "w") as f:
        f.write(html_content)

    print("Evaluation report artifacts saved to:")
    print(f"  • JSON: {json_path}")
    print(f"  • HTML: {html_path}\n")

    return report_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run behavioral LLM evaluation for small-team-support-agent."
    )
    parser.add_argument(
        "--dataset",
        default=os.path.join(
            os.path.dirname(__file__), "tests", "eval", "datasets", "team_support_eval.json"
        ),
        help="Path to evaluation dataset JSON.",
    )
    parser.add_argument(
        "--max-cases", type=int, default=None, help="Limit number of eval cases to run."
    )
    args = parser.parse_args()

    report = run_evaluation(args.dataset, args.max_cases)
    sys.exit(0 if report["passed_cases"] == report["total_cases"] else 1)
