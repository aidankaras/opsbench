"""Compute every number in the report from results/ and labels/, and draw the main figure.

Usage: python analyze.py   ->  results/summary.json, figures/grader_accuracy.png
Accuracy is measured only on runs where the graders disagreed and a label exists.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).parent
JUDGES = {"openai/gpt-6-luna": "GPT-6 Luna judge", "mistralai/mistral-small-3.2-24b-instruct": "Mistral Small judge"}


def jl(p):
    return [json.loads(line) for line in open(ROOT / p)]


def key(r):
    return (r["candidate"], r["task"], r["epoch"])


def labels(*files):
    out = {}
    for f in files:
        for r in jl(f):
            out[key(r)] = r["label"]
    return {k: v for k, v in out.items() if v is not None}


def score(pred, lab):
    ks = [k for k in lab if k in pred and pred[k] is not None]
    return {"right": sum(pred[k] == lab[k] for k in ks), "n": len(ks),
            "false_pass": sum(pred[k] and not lab[k] for k in ks),
            "false_fail": sum((not pred[k]) and lab[k] for k in ks)}


def judge_preds(rows):
    return {j: {key(r): r["judge_pass"] for r in rows if r["judge"] == j} for j in JUDGES}


def rates(rows, field):
    out = {}
    for c in sorted({r["candidate"] for r in rows}):
        rs = [r for r in rows if r["candidate"] == c]
        out[c] = round(sum(r[field] for r in rs) / len(rs), 3)
    return out


def main():
    dev_lab = labels("labels/hand-labels.jsonl", "labels/rule-labels.jsonl")
    ho_lab = labels("labels/heldout-rule-labels.jsonl", "labels/heldout-hand-labels.jsonl")
    dev_s, ho_s = jl("results/rescored.jsonl"), jl("results/rescored-heldout.jsonl")
    dev_j, ho_j = judge_preds(jl("results/judged-all.jsonl")), judge_preds(jl("results/judged-heldout.jsonl"))
    spot = jl("labels/spotcheck-result.jsonl") + jl("labels/heldout-spotcheck-result.jsonl")
    S = {
        "development": {
            "labeled": len(dev_lab),
            "checks_original": score({key(r): r["check_v1"] for r in dev_s}, dev_lab),
            "checks_repaired_in_sample": score({key(r): r["check_v2"] for r in dev_s}, dev_lab),
            **{JUDGES[j]: score(p, dev_lab) for j, p in dev_j.items()},
            "pass_rate_original": rates(dev_s, "check_v1"), "pass_rate_repaired": rates(dev_s, "check_v2"),
        },
        "held_out": {
            "labeled": len(ho_lab),
            "checks_repaired": score({key(r): r["check_v2"] for r in ho_s}, ho_lab),
            **{JUDGES[j]: score(p, ho_lab) for j, p in ho_j.items()},
            "pass_rate_repaired": rates(ho_s, "check_v2"),
        },
        "rule_label_spotcheck": {"agree": sum(r["aidan_agrees"] for r in spot), "n": len(spot)},
    }
    (ROOT / "results/summary.json").write_text(json.dumps(S, indent=1))

    bars = [("Checks, original\n(development)", S["development"]["checks_original"]),
            ("Checks, repaired\n(held-out)", S["held_out"]["checks_repaired"]),
            ("GPT-6 Luna judge\n(held-out)", S["held_out"]["GPT-6 Luna judge"]),
            ("Mistral Small judge\n(held-out)", S["held_out"]["Mistral Small judge"])]
    fig, ax = plt.subplots(figsize=(7.6, 4.6), dpi=150)
    for i, (name, s) in enumerate(bars):
        fp, ff = s["false_pass"] / s["n"], s["false_fail"] / s["n"]
        ok = s["right"] / s["n"]
        ax.barh(i, ok, color="#1f5f8b")
        ax.barh(i, fp, left=ok, color="#b8432f")
        ax.barh(i, ff, left=ok + fp, color="#e0a458")
        ax.text(0.01, i, f"{s['right']}/{s['n']}", va="center", color="white", fontsize=9)
    ax.set_yticks(range(len(bars)), [b[0] for b in bars], fontsize=9, color="#1a1a1a")
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of labeled disagreement cases", color="#1a1a1a")
    ax.set_title("Grader verdicts vs human-reviewed labels, on cases where graders disagreed",
                 fontsize=10, color="#1a1a1a", loc="left")
    ax.legend(["Right", "Passed a real failure", "Failed a correct run"], loc="upper left", bbox_to_anchor=(0, -0.16), ncol=3,
              fontsize=8, frameon=False, labelcolor="#1a1a1a")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.text(0.01, 0.01, "4 agent models x 28 tasks x 3 epochs per round. Development n=98, held-out n=63 "
             "(Luna n=57: 6 unparsed verdicts).", fontsize=7.5, color="#333333")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    (ROOT / "figures").mkdir(exist_ok=True)
    fig.savefig(ROOT / "figures/grader_accuracy.png")
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = [t.get_window_extent(r) for t in fig.findobj(matplotlib.text.Text) if t.get_text()]
    fb = fig.bbox
    clipped = [b for b in boxes if b.x0 < fb.x0 - 1 or b.x1 > fb.x1 + 1 or b.y0 < fb.y0 - 1 or b.y1 > fb.y1 + 1]
    leg = ax.get_legend().get_window_extent(r)
    assert not clipped, f"text clipped: {clipped}"
    assert leg.y1 < ax.get_window_extent(r).y0 - ax.xaxis.label.get_window_extent(r).height * 0, "legend on bars"
    print(json.dumps(S, indent=1))


if __name__ == "__main__":
    main()
