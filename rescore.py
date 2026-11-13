"""Re-run programmatic checks on finished eval logs (no model calls).

Rebuilds each sample's final env from the saved Inspect store, adds the agent's final reply, and
applies the current checks. Writes one JSONL row per sample; prints pass rate per model.

Usage: python rescore.py OUT.jsonl LOG.eval [LOG.eval ...]
"""
from __future__ import annotations

import json
import sys

from inspect_ai.log import read_eval_log

from opsbench.tasks import TASKS

CHECK = {t["id"]: t["check"] for t in TASKS}


def main(out, logs):
    rows = []
    for p in logs:
        log = read_eval_log(p)
        cand = log.eval.model.removeprefix("openrouter/")
        for s in log.samples:
            env = dict(s.store.get("env") or {})
            env["final"] = s.output.completion if s.output else ""
            env["calls"] = [tc.function for m in s.messages if m.role == "assistant" for tc in (m.tool_calls or [])]
            ok, why = CHECK[s.id](env)
            rows.append({"candidate": cand, "task": s.id, "epoch": s.epoch,
                         "check_v1": s.scores["outcome"].value == "C", "check_v2": ok, "why_v2": why})
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    for c in sorted({r["candidate"] for r in rows}):
        rs = [r for r in rows if r["candidate"] == c]
        print(f"{c:45s} v1 {sum(r['check_v1'] for r in rs) / len(rs):.3f}  v2 {sum(r['check_v2'] for r in rs) / len(rs):.3f}  n={len(rs)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
