"""Re-run programmatic checks on finished eval logs (no model calls).

Rebuilds each sample's final env from the saved Inspect store, adds the agent's final reply and the
list of called tools, and applies the checks. Writes one JSONL row per sample with:
  check_logged  the score stored in the log at run time (development: the uncommitted v1 checks;
                held-out: the v2 checks)
  check_v2      the frozen v2 checks (opsbench/checks_v2.py), recomputed
  check_v3      the current checks (opsbench/tasks.py), recomputed
Prints pass rate per model.

Usage: python rescore.py OUT.jsonl LOG.eval [LOG.eval ...]
"""
from __future__ import annotations

import json
import sys

from inspect_ai.log import read_eval_log

from opsbench.checks_v2 import CHECKS as CHECKS_V2
from opsbench.env import called_tools
from opsbench.tasks import TASKS

CHECK = {t["id"]: t["check"] for t in TASKS}


def sample_env(s):
    """The env a check sees for a finished sample, as the scorer in opsbench_task.py builds it."""
    env = dict(s.store.get("env") or {})
    env["final"] = s.output.completion if s.output else ""
    env["calls"] = called_tools(s.messages)
    return env


def rescore(logs):
    rows = []
    for p in logs:
        log = read_eval_log(p)
        cand = log.eval.model.removeprefix("openrouter/")
        for s in log.samples:
            env = sample_env(s)
            ok, why = CHECK[s.id](env)
            rows.append({"candidate": cand, "task": s.id, "epoch": s.epoch,
                         "check_logged": s.scores["outcome"].value == "C",
                         "check_v2": CHECKS_V2[s.id](env)[0], "check_v3": ok, "why_v3": why})
    return rows


def main(out, logs):
    rows = rescore(logs)
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    for c in sorted({r["candidate"] for r in rows}):
        rs = [r for r in rows if r["candidate"] == c]
        rate = {k: sum(r[k] for r in rs) / len(rs) for k in ("check_logged", "check_v2", "check_v3")}
        print(f"{c:45s} logged {rate['check_logged']:.3f}  v2 {rate['check_v2']:.3f}  v3 {rate['check_v3']:.3f}  n={len(rs)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
