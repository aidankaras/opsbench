"""Build hand-label batches from grader/check disagreements.

Usage: python label_batches.py [--compact] judged.jsonl OUT.json LOG.eval [LOG.eval ...]
Shuffles (seed 0) the unique (candidate, task, epoch) disagreements and writes them in batches
of 15 with the user request and an action trace. Labeler sees neither verdict (blind).

By default the trace shows every tool call with its full arguments, the tool's result, and the
full final reply, which is what the judges see too. --compact reproduces the view the committed
labels were made from (labels/batches.json, labels/heldout.json): tool calls only, no results,
arguments cut at 90 characters and the final reply at 260.
"""
from __future__ import annotations

import argparse
import json
import random

from inspect_ai.log import read_eval_log


def trace(sample, compact=False) -> list[str]:
    out = []
    for m in sample.messages[1:]:
        if m.role == "assistant":
            for tc in m.tool_calls or []:
                cut = 90 if compact else None
                args = ", ".join(f"{k}={str(v)[:cut]!r}" for k, v in tc.arguments.items())
                out.append(f"{tc.function}({args})")
            if m.text and not m.tool_calls:
                out.append(f'final: "{m.text[:260] if compact else m.text}"')
        elif m.role == "tool" and not compact:
            out.append(f"  -> {m.text}")
    return out


def main(judged, out, logs, compact=False):
    rows = [json.loads(line) for line in open(judged)]
    keys = sorted({(r["candidate"], r["task"], r["epoch"]) for r in rows
                   if r["judge_pass"] is not None and r["judge_pass"] != r["check_pass"]})
    samples = {}
    for p in logs:
        log = read_eval_log(p)
        cand = log.eval.model.removeprefix("openrouter/")
        for s in log.samples:
            samples[(cand, s.id, s.epoch)] = s
    random.Random(0).shuffle(keys)
    items = []
    for i, k in enumerate(keys):
        s = samples[k]
        items.append({"n": i + 1, "candidate": k[0], "task": k[1], "epoch": k[2],
                      "request": s.input if isinstance(s.input, str) else s.input[-1].text,
                      "actions": trace(s, compact)})
    batches = [items[i:i + 15] for i in range(0, len(items), 15)]
    json.dump(batches, open(out, "w"), indent=1)
    print(len(items), "items,", len(batches), "batches")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compact", action="store_true")
    ap.add_argument("judged")
    ap.add_argument("out")
    ap.add_argument("logs", nargs="+")
    a = ap.parse_args()
    main(a.judged, a.out, a.logs, a.compact)
