"""Build hand-label batches from grader/check disagreements.

Usage: python label_batches.py judged-all.jsonl labels/batches.json LOG.eval [LOG.eval ...]
Shuffles (seed 0) the unique (candidate, task, epoch) disagreements and writes them in batches
of 15 with the user request and a compact action trace. Labeler sees neither verdict (blind).
"""
from __future__ import annotations

import json
import random
import sys

from inspect_ai.log import read_eval_log


def trace(sample) -> list[str]:
    out = []
    for m in sample.messages[1:]:
        if m.role == "assistant":
            for tc in m.tool_calls or []:
                args = ", ".join(f"{k}={str(v)[:90]!r}" for k, v in tc.arguments.items())
                out.append(f"{tc.function}({args})")
            if m.text and not m.tool_calls:
                out.append(f'final: "{m.text[:260]}"')
    return out


def main(judged, out, logs):
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
                      "actions": trace(s)})
    batches = [items[i:i + 15] for i in range(0, len(items), 15)]
    json.dump(batches, open(out, "w"), indent=1)
    print(len(items), "items,", len(batches), "batches")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
