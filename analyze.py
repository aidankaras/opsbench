"""Compute every number in the report from results/ and labels/, and draw the main figure.

Usage: python analyze.py   ->  results/summary.json, results/heldout-check-errors.jsonl,
                               results/judge-errors-by-item.json, figures/grader_accuracy.png
Accuracy is measured only on runs where the graders disagreed and a label exists. Labels come from
two sources, reported apart: hand labels (one human) and rule labels (written rules applied to
clear-cut cases). Every rate gets a Wilson 95% interval and a task-clustered bootstrap 95% interval
(tasks resampled with replacement, fixed seed, so the output is identical on every run).
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).parent
JUDGES = {"openai/gpt-6-luna": "GPT-6 Luna judge", "mistralai/mistral-small-3.2-24b-instruct": "Mistral Small judge"}
BOOT, SEED = 2000, 0
REGRADE = {"development": "results/judged-all-rubric-v2.jsonl", "held_out": "results/judged-heldout-rubric-v2.jsonl"}


def jl(p):
    return [json.loads(line) for line in open(ROOT / p)]


def key(r):
    return (r["candidate"], r["task"], r["epoch"])


def labels(**files):
    """{key: (label, source)} for every non-null label; files are given as source=path."""
    out = {}
    for source, f in files.items():
        for r in jl(f):
            if r["label"] is not None:
                out[key(r)] = (r["label"], source)
    return out


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def boot(items, seed=SEED):
    """Task-clustered bootstrap 95% interval for the mean of 0/1 `ok` over items [(task, ok)]."""
    by = {}
    for t, ok in items:
        by.setdefault(t, []).append(ok)
    tasks = sorted(by)
    if not tasks:
        return None
    rng, stats = random.Random(seed), []
    for _ in range(BOOT):
        pick = [rng.choice(tasks) for _ in tasks]
        n = sum(len(by[t]) for t in pick)
        stats.append(sum(sum(by[t]) for t in pick) / n)
    stats.sort()
    return [round(stats[int(0.025 * BOOT)], 3), round(stats[int(0.975 * BOOT) - 1], 3)]


def rate(items):
    """items [(task, ok)] -> k, n, rate and both intervals."""
    k, n = sum(ok for _, ok in items), len(items)
    return {"k": k, "n": n, "rate": round(k / n, 3) if n else None, "wilson95": wilson(k, n), "task_boot95": boot(items)}


def score(pred, lab, source=None):
    """Accuracy of pred {key: bool|None} on labels {key: (label, source)}; None verdicts are skipped."""
    ks = [k for k in lab if k in pred and pred[k] is not None and source in (None, lab[k][1])]
    s = {"right": sum(pred[k] == lab[k][0] for k in ks), "n": len(ks),
         "false_pass": sum(pred[k] and not lab[k][0] for k in ks),
         "false_fail": sum((not pred[k]) and lab[k][0] for k in ks)}
    r = rate([(k[1], pred[k] == lab[k][0]) for k in ks])
    return {**s, "accuracy": r["rate"], "wilson95": r["wilson95"], "task_boot95": r["task_boot95"]}


def by_source(pred, lab):
    out = score(pred, lab)
    out["hand_labels"] = score(pred, lab, "hand")
    out["rule_labels"] = score(pred, lab, "rule")
    return out


def judge_rows(rows, recover=False):
    """{judge: {key: verdict}}; recover=True reads the verdict out of a cut-off reply."""
    out = {j: {} for j in JUDGES}
    for r in rows:
        v = r["judge_pass"]
        if v is None and recover:
            low = (r.get("reason") or "").replace(" ", "").lower()
            v = True if '"verdict":"pass"' in low else False if '"verdict":"fail"' in low else None
        out[r["judge"]][key(r)] = v
    return out


def judge_block(rows, lab):
    raw, rec = judge_rows(rows), judge_rows(rows, recover=True)
    out = {}
    for j, name in JUDGES.items():
        mine = [r for r in rows if r["judge"] == j]
        unparsed = [key(r) for r in mine if r["judge_pass"] is None]
        b = by_source(raw[j], lab)
        b["verdicts"] = {"total": len(mine), "unparsed": len(unparsed),
                         "recovered_from_cut_off_reply": sum(rec[j][k] is not None for k in unparsed),
                         "recovered_fail": sum(rec[j][k] is False for k in unparsed),
                         "recovered_pass": sum(rec[j][k] is True for k in unparsed),
                         "unparsed_among_labeled": sum(k in lab for k in unparsed)}
        b["with_recovered_verdicts"] = score(rec[j], lab)
        worst = {k: (v if v is not None else (not lab[k][0]) if k in lab else None) for k, v in rec[j].items()}
        b["sensitivity_unrecoverable_counted_wrong"] = score(worst, lab)
        out[name] = b
    return out


def pass_rates(rows, field):
    out = {}
    for c in sorted({r["candidate"] for r in rows}):
        r = rate([(x["task"], x[field]) for x in rows if x["candidate"] == c])
        out[c] = {"rate": r["rate"], "task_boot95": r["task_boot95"]}
    return out


def implied_error_rates(check, judged, lab):
    """Overall error rate per grader if runs where all graders agree are taken as correct and the
    labeled disagreements decide the rest. Unlabeled disagreements are excluded from the denominator."""
    preds = {"checks": check, **{JUDGES[j]: p for j, p in judge_rows(judged).items()}}
    out = {}
    for name, p in preds.items():
        items = []
        for k, v in p.items():
            if v is None:
                continue
            others = [q.get(k) for q in preds.values() if q.get(k) is not None]
            if len(set(others)) == 1:
                items.append((k[1], True))
            elif k in lab:
                items.append((k[1], v == lab[k][0]))
        r = rate([(t, not ok) for t, ok in items])
        out[name] = {"errors": r["k"], "n": r["n"], "rate": r["rate"], "task_boot95": r["task_boot95"]}
    return out


def judge_errors_by_item(rows, lab):
    """Held-out judge errors grouped by task, direction and the v1 rubric items the judge failed."""
    out = Counter()
    for r in rows:
        k = key(r)
        if k in lab and r["judge_pass"] is not None and r["judge_pass"] != lab[k][0]:
            kind = "false_fail" if lab[k][0] else "false_pass"
            out[(JUDGES[r["judge"]], r["task"], kind, json.dumps(r["failed_items"]))] += 1
    return [{"judge": j, "task": t, "error": e, "failed_items": json.loads(i), "count": c}
            for (j, t, e, i), c in sorted(out.items(), key=lambda kv: (kv[0][0], -kv[1], kv[0][1:]))]


def main():
    dev_lab = labels(hand="labels/hand-labels.jsonl", rule="labels/rule-labels.jsonl")
    ho_lab = labels(rule="labels/heldout-rule-labels.jsonl", hand="labels/heldout-hand-labels.jsonl")
    unsure = [key(r) for r in jl("labels/hand-labels.jsonl") if r["label"] is None]
    dev_s, ho_s = jl("results/rescored.jsonl"), jl("results/rescored-heldout.jsonl")
    dev_jr, ho_jr = jl("results/judged-all.jsonl"), jl("results/judged-heldout.jsonl")
    spot = jl("labels/spotcheck-result.jsonl") + jl("labels/heldout-spotcheck-result.jsonl")
    pred = lambda rows, f: {key(r): r[f] for r in rows}  # noqa: E731
    dev_logged = pred(dev_s, "check_logged")

    def round_summary(lab, s_rows, j_rows, checks):
        return {"labeled": len(lab), "labels_by_source": dict(sorted(Counter(v[1] for v in lab.values()).items())),
                **{name: by_source(pred(s_rows, f), lab) for name, f in checks.items()},
                **judge_block(j_rows, lab)}

    dev = round_summary(dev_lab, dev_s, dev_jr, {"checks_original": "check_logged", "checks_v2_in_sample": "check_v2",
                                                 "checks_v3_in_sample": "check_v3"})
    dev["unsure_excluded"] = {"n": len(unsure), "checks_original_pass": sum(dev_logged[k] for k in unsure),
                              **{f"{JUDGES[j]}_pass": sum(bool(p.get(k)) for k in unsure)
                                 for j, p in judge_rows(dev_jr).items()}}
    dev["pass_rate_original"] = pass_rates(dev_s, "check_logged")
    dev["pass_rate_v2"] = pass_rates(dev_s, "check_v2")
    dev["pass_rate_v3"] = pass_rates(dev_s, "check_v3")
    dev["implied_overall_error_rate"] = implied_error_rates(dev_logged, dev_jr, dev_lab)

    ho = round_summary(ho_lab, ho_s, ho_jr, {"checks_v2": "check_v2", "checks_v3_in_sample": "check_v3"})
    ho["pass_rate_v2"] = pass_rates(ho_s, "check_v2")
    ho["pass_rate_v3"] = pass_rates(ho_s, "check_v3")
    ho["implied_overall_error_rate"] = implied_error_rates(pred(ho_s, "check_v2"), ho_jr, ho_lab)
    ho["v3_changed_verdicts"] = {"n": sum(r["check_v2"] != r["check_v3"] for r in ho_s),
                                 "labeled": sum(r["check_v2"] != r["check_v3"] and key(r) in ho_lab for r in ho_s)}
    dev["v3_changed_verdicts"] = {"n": sum(r["check_v2"] != r["check_v3"] for r in dev_s),
                                  "labeled": sum(r["check_v2"] != r["check_v3"] and key(r) in dev_lab for r in dev_s)}

    agree = sum(r["reviewer_agrees"] for r in spot)
    S = {
        "development": dev,
        "held_out": ho,
        "rule_label_spotcheck": {"agree": agree, "n": len(spot),
                                 # exact one-sided 95% upper bound on the rule-label error rate (0 disagreements)
                                 "error_rate_upper95": round(1 - 0.05 ** (1 / len(spot)), 3) if agree == len(spot) else None},
        "regraded_v2_rubrics": {name: (judge_block(jl(p), lab) if (ROOT / p).exists() else None)
                                for (name, p), lab in zip(REGRADE.items(), (dev_lab, ho_lab))},
        "method": {"bootstrap": f"{BOOT} task-clustered resamples, seed {SEED}, percentile interval",
                   "wilson": "95% Wilson score interval"},
    }
    (ROOT / "results/summary.json").write_text(json.dumps(S, indent=1))

    errs = [{**dict(zip(("candidate", "task", "epoch"), k)), "label": v[0], "label_source": v[1],
             "check_v2": r["check_v2"], "check_v3": r["check_v3"], "why_v3": r["why_v3"]}
            for r in ho_s for k in [key(r)] if k in ho_lab for v in [ho_lab[k]] if r["check_v2"] != v[0]]
    (ROOT / "results/heldout-check-errors.jsonl").write_text("".join(json.dumps(e) + "\n" for e in errs))
    (ROOT / "results/judge-errors-by-item.json").write_text(json.dumps(judge_errors_by_item(ho_jr, ho_lab), indent=1))

    bars = [("Checks, original\n(development)", dev["checks_original"]),
            ("Checks, repaired v2\n(held-out)", ho["checks_v2"]),
            ("GPT-6 Luna judge\n(held-out, v1 rubrics)", ho["GPT-6 Luna judge"]),
            ("Mistral Small judge\n(held-out, v1 rubrics)", ho["Mistral Small judge"])]
    if S["regraded_v2_rubrics"]["held_out"]:
        bars += [(f"{n}\n(held-out, v2 rubrics)", S["regraded_v2_rubrics"]["held_out"][n]) for n in JUDGES.values()]
    fig, ax = plt.subplots(figsize=(7.6, 4.6 + 0.5 * (len(bars) - 4)), dpi=150)
    for i, (name, s) in enumerate(bars):
        fp, ff = s["false_pass"] / s["n"], s["false_fail"] / s["n"]
        ok = s["right"] / s["n"]
        ax.barh(i, ok, color="#1f5f8b")
        ax.barh(i, fp, left=ok, color="#b8432f")
        ax.barh(i, ff, left=ok + fp, color="#e0a458")
        lo, hi = s["task_boot95"]
        ax.errorbar(ok, i, xerr=[[ok - lo], [hi - ok]], fmt="none", ecolor="#1a1a1a", elinewidth=1, capsize=3)
        ax.text(0.01, i, f"{s['right']}/{s['n']}", va="center", color="white", fontsize=9)
    ax.set_yticks(range(len(bars)), [b[0] for b in bars], fontsize=9, color="#1a1a1a")
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of labeled disagreement cases (whisker: task-clustered bootstrap 95% CI on 'right')",
                  color="#1a1a1a", fontsize=8.5)
    ax.set_title("Grader verdicts vs human or rule labels, on cases where graders disagreed",
                 fontsize=10, color="#1a1a1a", loc="left")
    ax.legend(["Right", "Passed a real failure", "Failed a correct run"], loc="upper left", bbox_to_anchor=(0, -0.2), ncol=3,
              fontsize=8, frameon=False, labelcolor="#1a1a1a")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    src = lambda r: f"{r['labeled']} ({r['labels_by_source'].get('hand', 0)} hand, {r['labels_by_source'].get('rule', 0)} rule)"  # noqa: E731
    luna = ho["GPT-6 Luna judge"]
    fig.text(0.01, 0.01, f"4 agent models x 28 tasks x 3 epochs per round. Labeled: development {src(dev)}, held-out "
             f"{src(ho)}.\nLuna held-out n={luna['n']}: {ho['labeled'] - luna['n']} labeled runs had no parseable verdict.",
             fontsize=7.5, color="#333333")
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    (ROOT / "figures").mkdir(exist_ok=True)
    fig.savefig(ROOT / "figures/grader_accuracy.png")
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = [t.get_window_extent(r) for t in fig.findobj(matplotlib.text.Text) if t.get_text()]
    fb = fig.bbox
    clipped = [b for b in boxes if b.x0 < fb.x0 - 1 or b.x1 > fb.x1 + 1 or b.y0 < fb.y0 - 1 or b.y1 > fb.y1 + 1]
    assert not clipped, f"text clipped: {clipped}"
    leg, xlab = ax.get_legend().get_window_extent(r), ax.xaxis.label.get_window_extent(r)
    assert leg.y1 < xlab.y0, "legend overlaps the x-axis label"
    print(json.dumps({k: S[k] for k in ("rule_label_spotcheck",)}, indent=1))
    for rnd in ("development", "held_out"):
        for name, v in S[rnd].items():
            if isinstance(v, dict) and "right" in v:
                print(f"{rnd:12s} {name:22s} {v['right']}/{v['n']}  boot95 {v['task_boot95']}  "
                      f"hand {v['hand_labels']['right']}/{v['hand_labels']['n']}  rule {v['rule_labels']['right']}/{v['rule_labels']['n']}")


if __name__ == "__main__":
    main()
