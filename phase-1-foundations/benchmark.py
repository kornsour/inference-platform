#!/usr/bin/env python3
"""Benchmark OpenAI-compatible inference endpoints — speed *and* quality.

Works with vLLM (:8000/v1), Ollama (:11434/v1), or any OpenAI-compatible server.

Two modes:

  Performance (default) — stream completions to time the *first* token (TTFT)
  separately from decode, then sweep concurrency levels to show the
  latency/throughput trade-off that defines inference serving:

      python benchmark.py --base-url http://localhost:11434/v1 \
          --model qwen3.5:4b --concurrency 1 4 16

  Quality (--quality) — run a fixed prompt suite across one or more models,
  capture each answer (separating reasoning from the final answer), and write a
  side-by-side Markdown report for human review. Optionally score the answers
  with an LLM judge (--judge MODEL), blinded and against a per-prompt rubric:

      python benchmark.py --base-url http://localhost:11434/v1 --quality \
          --models qwen3.5:4b qwen2.5:14b-instruct gemma4:e4b \
          --judge qwen2.5:14b-instruct

Dependencies: see requirements.txt (openai>=1.0).
"""
import argparse
import json
import random
import statistics
import threading
import time
from dataclasses import dataclass

from openai import OpenAI

PROMPT = (
    "You are a systems engineer. Explain, in about 200 words, why decode is "
    "memory-bandwidth-bound while prefill is compute-bound in LLM inference."
)

# Small, categorized suite for the quality comparison. Each item carries a
# rubric describing what a good answer needs — used both to anchor human review
# and to prompt the optional LLM judge. Kept short so a multi-model run on a
# laptop finishes in a couple of minutes.
QUALITY_SUITE = [
    {
        "id": "factual",
        "category": "Factual recall",
        "prompt": "In 2-3 sentences, what was the key idea of the 2017 "
                  "'Attention Is All You Need' paper, and what limitation of "
                  "RNNs did it address?",
        "rubric": "Self-attention replaces recurrence; enables parallel "
                  "training and better long-range dependencies than sequential "
                  "RNNs.",
    },
    {
        "id": "reasoning",
        "category": "Reasoning / math",
        "prompt": "A model serves 3 requests per second. Each request "
                  "generates 500 output tokens. At $2 per million output "
                  "tokens, what is the hourly output-token cost? Show your steps.",
        "rubric": "3*500=1500 tok/s; *3600=5.4M tok/hr; *$2/1e6 = $10.80/hour.",
    },
    {
        "id": "instruction",
        "category": "Instruction-following",
        "prompt": "List exactly three differences between prefill and decode in "
                  "LLM inference. Respond ONLY as a numbered list, one line "
                  "each, with no preamble or closing remarks.",
        "rubric": "Exactly three numbered items, no preamble; technically "
                  "correct (compute- vs memory-bound, whole-prompt vs one "
                  "token, KV-cache growth, etc.).",
    },
    {
        "id": "coding",
        "category": "Coding",
        "prompt": "Write a Python function `ttft(timestamps)` that takes a list "
                  "of token arrival times in seconds (ascending) and returns "
                  "the time-to-first-token. Return None for an empty list.",
        "rubric": "Returns timestamps[0] when non-empty (or first-minus-start "
                  "if a start is defined), None when empty; correct and runnable.",
    },
    {
        "id": "concise",
        "category": "Conciseness",
        "prompt": "What does TTFT stand for? Answer in one short sentence.",
        "rubric": "'Time To First Token', in a single concise sentence; "
                  "penalize rambling or visible over-thinking.",
    },
    {
        "id": "summarize",
        "category": "Summarization",
        "prompt": "Summarize in one sentence: 'Continuous batching lets the "
                  "scheduler add and evict requests from the running batch every "
                  "decode step, so new requests join immediately and finished "
                  "ones free their slots, which is the biggest throughput win "
                  "in modern LLM serving.'",
        "rubric": "Faithful one-sentence summary capturing per-step batch "
                  "membership changes and the throughput benefit.",
    },
]


# --------------------------------------------------------------------------- #
# Performance mode
# --------------------------------------------------------------------------- #
@dataclass
class RequestResult:
    ttft: float          # seconds to first token
    total: float         # seconds for the full completion
    output_tokens: int   # tokens generated (approximate, counts streamed chunks)


def _delta_piece(delta):
    """Any generated text on a chunk, including reasoning-model 'thinking'.

    Reasoning models (Qwen3, gemma) stream chain-of-thought on a separate
    channel. From a serving standpoint every decoded token costs compute + KV
    cache, so all of them count toward TTFT and throughput — otherwise a model
    that spends its whole budget reasoning reads as 0 tokens/sec.
    """
    return (delta.content
            or getattr(delta, "reasoning_content", None)
            or getattr(delta, "reasoning", None))


def run_one(client: OpenAI, model: str, max_tokens: int) -> RequestResult:
    start = time.perf_counter()
    ttft = None
    tokens = 0
    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=max_tokens,
        temperature=0.7,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        if _delta_piece(chunk.choices[0].delta):
            if ttft is None:
                ttft = time.perf_counter() - start
            tokens += 1
    total = time.perf_counter() - start
    return RequestResult(ttft=ttft or total, total=total, output_tokens=tokens)


def run_concurrency_level(client, model, concurrency, requests, max_tokens):
    results: list[RequestResult] = []
    lock = threading.Lock()

    def worker(n):
        for _ in range(n):
            r = run_one(client, model, max_tokens)
            with lock:
                results.append(r)

    # divide requests across `concurrency` threads
    per = [requests // concurrency] * concurrency
    for i in range(requests % concurrency):
        per[i] += 1

    wall_start = time.perf_counter()
    threads = [threading.Thread(target=worker, args=(n,)) for n in per if n]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - wall_start
    return results, wall


def pct(values, p):
    if not values:
        return 0.0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round((p / 100) * (len(values) - 1)))))
    return values[k]


def run_perf(args, client):
    print(f"\nEndpoint: {args.base_url}   Model: {args.model}\n")
    header = f"{'conc':>5} {'reqs':>5} {'TTFT p50':>9} {'TTFT p95':>9} {'tok/s/req':>10} {'total tok/s':>12}"
    print(header)
    print("-" * len(header))

    for c in args.concurrency:
        reqs = args.requests or (c * 4)
        results, wall = run_concurrency_level(client, args.model, c, reqs, args.max_tokens)
        ttfts = [r.ttft for r in results]
        per_req_tps = [r.output_tokens / r.total for r in results if r.total > 0]
        total_tokens = sum(r.output_tokens for r in results)
        system_tps = total_tokens / wall if wall > 0 else 0
        print(f"{c:>5} {reqs:>5} {pct(ttfts,50):>8.3f}s {pct(ttfts,95):>8.3f}s "
              f"{statistics.mean(per_req_tps):>9.1f} {system_tps:>11.1f}")

    print("\nRead it as: as concurrency rises, total tok/s should climb (better GPU\n"
          "utilization via batching) while TTFT p95 and per-request tok/s degrade.\n"
          "That trade-off is the whole game.\n")


# --------------------------------------------------------------------------- #
# Quality mode
# --------------------------------------------------------------------------- #
@dataclass
class Answer:
    model: str
    content: str        # the user-facing final answer
    reasoning: str      # chain-of-thought, if the model exposed it
    latency: float      # seconds
    gen_tokens: int     # completion tokens, from usage if available
    truncated: bool = False  # hit the max_tokens cap before finishing


def complete_once(client, model, prompt, max_tokens, temperature) -> Answer:
    """Non-streaming completion; separates final answer from reasoning."""
    start = time.perf_counter()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    latency = time.perf_counter() - start
    choice = resp.choices[0]
    msg = choice.message
    content = (msg.content or "").strip()
    reasoning = (getattr(msg, "reasoning_content", None)
                 or getattr(msg, "reasoning", None) or "").strip()
    gen = getattr(getattr(resp, "usage", None), "completion_tokens", 0) or 0
    # finish_reason == "length" means the model was cut off at the token cap.
    # For a reasoning model that often means it spent the whole budget thinking
    # and never emitted a final answer — a budget problem, not a quality one.
    truncated = choice.finish_reason == "length"
    return Answer(model=model, content=content, reasoning=reasoning,
                  latency=latency, gen_tokens=gen, truncated=truncated)


def _extract_json(text):
    """Pull the first balanced JSON object out of a model response."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def judge_item(client, judge_model, item, answers, seed):
    """Blind-score each answer 1-5 against the rubric. Returns {model: {score, reason}}.

    Answers are relabeled Response 1..N in a shuffled order so the judge can't
    anchor on model names or position.
    """
    order = list(answers)
    random.Random(seed).shuffle(order)
    labels = {f"Response {i+1}": ans for i, ans in enumerate(order)}
    blocks = "\n\n".join(
        f"### {lab}\n{ans.content or '(model produced no final answer)'}"
        for lab, ans in labels.items()
    )
    system = ("You are a strict, fair evaluator of language-model answers. "
              "Judge only the answer text shown. Score each response 1-5 "
              "(5 = fully correct, complete, and well-formed; 1 = wrong or "
              "useless). Reward following the instructions exactly and penalize "
              "rambling. Output JSON only.")
    user = (f"Question:\n{item['prompt']}\n\n"
            f"What a good answer needs:\n{item['rubric']}\n\n"
            f"Responses:\n{blocks}\n\n"
            'Return ONLY this JSON shape:\n'
            '{"scores": {"Response 1": {"score": <1-5>, "reason": "<short>"}, '
            '...}, "winner": "Response N"}')
    resp = client.chat.completions.create(
        model=judge_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        max_tokens=800,
        temperature=0,
    )
    data = _extract_json(resp.choices[0].message.content or "")
    out = {}
    if data and isinstance(data.get("scores"), dict):
        for lab, info in data["scores"].items():
            if lab in labels and isinstance(info, dict):
                raw = info.get("score")
                if raw is None:
                    continue
                try:
                    score = int(raw)
                except (TypeError, ValueError):
                    continue
                out[labels[lab].model] = {
                    "score": max(1, min(5, score)),
                    "reason": str(info.get("reason", "")).strip(),
                }
    return out


def run_quality(args, client):
    models = args.models or ([args.model] if args.model else [])
    if not models:
        raise SystemExit("quality mode needs --models M1 M2 ... (or --model)")

    print(f"\nEndpoint: {args.base_url}   Quality comparison")
    print(f"Models: {', '.join(models)}")
    if args.judge:
        print(f"Judge:  {args.judge}  (blinded, rubric-scored)")
    print(f"Prompts: {len(QUALITY_SUITE)}   max_tokens: {args.max_tokens}\n")

    # collect answers: results[item_id] = {model: Answer}
    results = {}
    for item in QUALITY_SUITE:
        results[item["id"]] = {}
        for model in models:
            print(f"  [{item['id']:<11}] {model} ...", end="", flush=True)
            try:
                ans = complete_once(client, model, item["prompt"],
                                    args.max_tokens, args.temperature)
                results[item["id"]][model] = ans
                flag = "  ⚠ truncated/no-answer" if (ans.truncated and not ans.content) else ""
                print(f" {ans.latency:5.1f}s{flag}")
            except Exception as e:  # noqa: BLE001 - report and continue
                print(f" ERROR {type(e).__name__}")
                results[item["id"]][model] = Answer(model, f"(error: {e})", "", 0.0, 0)

    # optional judging
    scores = {}        # scores[item_id] = {model: {score, reason}}
    totals = {m: [] for m in models}
    if args.judge:
        print("\nJudging ...")
        for item in QUALITY_SUITE:
            answers = [results[item["id"]][m] for m in models]
            verdict = judge_item(client, args.judge, item, answers, seed=item["id"])
            scores[item["id"]] = verdict
            for m, info in verdict.items():
                totals[m].append(info["score"])
            print(f"  [{item['id']:<11}] " +
                  "  ".join(f"{m.split(':')[0]}={verdict.get(m,{}).get('score','-')}"
                           for m in models))

    _write_quality_report(args, models, results, scores, totals)
    print(f"\nWrote report -> {args.out}")

    # Warn loudly if a model never produced a final answer — that skews any
    # quality verdict and usually just means it needs a bigger --max-tokens.
    starved = sorted({m for itm in results.values() for m, a in itm.items()
                      if a.truncated and not a.content})
    if starved:
        print(f"\n⚠ No final answer (hit the {args.max_tokens}-token cap while "
              f"thinking): {', '.join(starved)}.\n  Re-run with a larger "
              f"--max-tokens for a fair comparison.")
    if args.judge:
        board = sorted(((statistics.mean(v) if v else 0.0, m)
                        for m, v in totals.items()), reverse=True)
        print("\nLeaderboard (mean judge score, 1-5):")
        for avg, m in board:
            print(f"  {avg:4.2f}  {m}")
        print("\nNote: LLM-as-judge is a useful signal, not ground truth — the "
              "judge has its own biases.\nFor anything that matters, read the "
              "answers in the report yourself.")


def _write_quality_report(args, models, results, scores, totals):
    lines = ["# Quality comparison report", ""]
    lines.append(f"- Endpoint: `{args.base_url}`")
    lines.append(f"- Models: {', '.join(f'`{m}`' for m in models)}")
    lines.append(f"- Prompts: {len(QUALITY_SUITE)}   max_tokens: {args.max_tokens}"
                 f"   temperature: {args.temperature}")
    if args.judge:
        lines.append(f"- Judge: `{args.judge}` (blinded, rubric-scored 1-5)")
    lines.append("")

    if args.judge and any(totals.values()):
        lines += ["## Leaderboard (mean judge score)", "",
                  "| Model | Mean | Scores |", "| --- | ---: | --- |"]
        board = sorted(((statistics.mean(v) if v else 0.0, m)
                        for m, v in totals.items()), reverse=True)
        for avg, m in board:
            lines.append(f"| `{m}` | {avg:.2f} | {totals[m]} |")
        lines += ["", "> LLM-as-judge is a noisy proxy, not ground truth. "
                  "Read the answers below before trusting the ranking.", ""]

    for item in QUALITY_SUITE:
        lines += [f"## {item['category']} — `{item['id']}`", "",
                  f"**Prompt:** {item['prompt']}", "",
                  f"*Good answer needs:* {item['rubric']}", ""]
        for m in models:
            ans = results[item["id"]][m]
            verdict = scores.get(item["id"], {}).get(m)
            badge = f" — judge {verdict['score']}/5" if verdict else ""
            meta = f"{ans.latency:.1f}s, {ans.gen_tokens} tok" if ans.latency else ""
            lines.append(f"### `{m}`{badge}  <sub>{meta}</sub>")
            if ans.truncated and not ans.content:
                lines.append("> ⚠ No final answer — hit the token cap while "
                             "thinking. Raise `--max-tokens`.")
            if verdict and verdict.get("reason"):
                lines.append(f"> judge: {verdict['reason']}")
            lines += ["", "```", ans.content or "(no final answer)", "```"]
            if ans.reasoning:
                short = ans.reasoning if len(ans.reasoning) < 600 else ans.reasoning[:600] + " …"
                lines += ["<details><summary>thinking</summary>", "", "```",
                          short, "```", "</details>"]
            lines.append("")
    with open(args.out, "w") as f:
        f.write("\n".join(lines))


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:8000/v1")
    ap.add_argument("--api-key", default="not-needed", help="any value for local servers")
    ap.add_argument("--model", help="single model (performance mode, or quality with one model)")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="token cap (default: 200 perf, 1536 quality — reasoning "
                         "models need room to think AND answer)")

    perf = ap.add_argument_group("performance mode")
    perf.add_argument("--concurrency", type=int, nargs="+", default=[1, 4, 16])
    perf.add_argument("--requests", type=int, default=None,
                      help="total requests per level (default: 4x concurrency)")

    qual = ap.add_argument_group("quality mode")
    qual.add_argument("--quality", action="store_true",
                      help="run the quality suite instead of the perf sweep")
    qual.add_argument("--models", nargs="+", help="models to compare in quality mode")
    qual.add_argument("--judge", help="model to score answers (LLM-as-judge)")
    qual.add_argument("--temperature", type=float, default=0.0,
                      help="sampling temperature for quality mode (default 0 for reproducibility)")
    qual.add_argument("--out", default="quality-report.md", help="Markdown report path")

    args = ap.parse_args()
    client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    if args.quality:
        if args.max_tokens is None:
            args.max_tokens = 1536   # reasoning models need room to think + answer
        run_quality(args, client)
    else:
        if args.max_tokens is None:
            args.max_tokens = 200
        if not args.model:
            ap.error("performance mode needs --model (or use --quality --models ...)")
        run_perf(args, client)


if __name__ == "__main__":
    main()
