"""Offline tests for judge.py: rubric sets, verdict parsing, family guard, dry run (no API calls)."""
import glob

import pytest

import judge
from opsbench.tasks import TASKS


def test_rubric_sets_cover_every_task():
    ids = {t["id"] for t in TASKS}
    for version, rubrics in judge.RUBRICS.items():
        assert set(rubrics) == ids, version
        assert all(rubrics[i] and all(isinstance(x, str) and x for x in rubrics[i]) for i in ids), version


@pytest.mark.parametrize("text, verdict, how", [
    ('{"verdict": "PASS", "failed_items": [], "reason": "ok"}', "PASS", "json"),
    ('Here you go:\n{"verdict":"fail","failed_items":[2],"reason":"x"}', "FAIL", "json"),
    ('{"verdict":"FAIL","failed_items":[1,2],"reason":"The assistant did not read the CI statu', "FAIL", "recovered"),
    ('{"verdict":"PASS","failed_items":[],"reason":"The assistant looked up Dana Whitfield, repo', "PASS", "recovered"),
    ('{"verdict', None, "none"),
    ("", None, "none"),
])
def test_parse_recovers_cut_off_verdicts(text, verdict, how):
    v, h = judge.parse(text)
    assert (v.get("verdict", "").upper() or None, h) == (verdict, how)


def test_family_guard_rejects_unknown_vendor():
    assert judge.family("openrouter/openai/gpt-6-luna") == judge.family("openai/gpt-6-luna") == "openai"
    with pytest.raises(ValueError):
        judge.family("openrouter/somevendor/model-x")


def test_dry_run_counts_every_call(capsys):
    tot = judge.dry_run(sorted(glob.glob("logs/heldout/*.eval")), "v2")
    assert tot["calls"] == 4 * 84 * 2  # no candidate shares a family with a judge
    assert tot["in"] > 0 and tot["cap"] >= tot["typ"] > 0
