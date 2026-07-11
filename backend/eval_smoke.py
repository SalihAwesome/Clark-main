"""
Live smoke test / mini-evaluation of the Clark agent loop.

Runs the agent against the REAL LLM and a REAL browser, prints the full
reason/act/observe trace, and reports simple metrics (steps, tool calls).

Usage:
    BROWSER_HEADLESS=true python -u eval_smoke.py
    # (omit BROWSER_HEADLESS to watch the real browser window)

Requires GEMINI_API_KEY or FIREWORKS_API_KEY in backend/.env and Chrome or Edge installed.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

load_dotenv()

from agent import AgentRun  # noqa: E402
from llm_client import LLMClient  # noqa: E402

SCENARIOS = [
    "What is the capital of France? Use web_search first, then tell me.",
    "Open https://www.wikipedia.org and search for Python programming language.",
]


def run_one(prompt: str, idx: int) -> dict:
    print(f"\n{'=' * 70}\nSCENARIO {idx}: {prompt}\n{'=' * 70}", flush=True)
    run = AgentRun(f"eval-{idx}", LLMClient())
    run.add_user_message(prompt)
    for ev in run.run():
        t = ev["type"]
        if t == "thought":
            print(f"  💭 {ev['content']}", flush=True)
        elif t == "action":
            print(f"  ⚙  {ev['tool']}  {ev['input']}", flush=True)
        elif t == "screenshot":
            print(f"  📸 {ev['url']}  ({ev.get('page_url', '')})", flush=True)
        elif t == "observation":
            r = ev["result"]
            keys = list(r.keys())[:6]
            print(f"  ✓  {ev['tool']} -> keys={keys}", flush=True)
        elif t == "awaiting_user":
            print(f"  🙋 AWAITING USER: {ev['reason']}", flush=True)
        elif t == "final":
            print(f"\n  ★ FINAL:\n{ev['content']}\n", flush=True)
        elif t == "error":
            print(f"  ⚠ ERROR: {ev['content']}", flush=True)
    return {"steps": run.steps, "tools_used": run._tools_used, "corrections": run._corrections}


def main() -> None:
    client = LLMClient()
    if not client.configured:
        print("LLM not configured — set GEMINI_API_KEY (or FIREWORKS_API_KEY) in .env.", file=sys.stderr)
        sys.exit(1)

    metrics = []
    for i, prompt in enumerate(SCENARIOS, 1):
        try:
            metrics.append(run_one(prompt, i))
        except Exception as exc:
            print(f"  ⚠ scenario {i} crashed: {exc}", flush=True)
            metrics.append({"steps": 0, "tools_used": 0, "corrections": 0})

    print(f"\n{'=' * 70}\nSUMMARY", flush=True)
    for i, m in enumerate(metrics, 1):
        print(f"  scenario {i}: steps={m['steps']} tools={m['tools_used']} corrections={m['corrections']}", flush=True)


if __name__ == "__main__":
    main()
