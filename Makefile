PY ?= python

.PHONY: report rescore test all regrade-dry regrade

report:            ## rebuild results/summary.json and figures/ from saved results ($0, seconds)
	$(PY) analyze.py

rescore:           ## re-run the programmatic checks on the saved agent logs ($0, no API calls)
	$(PY) rescore.py results/rescored.jsonl logs/dev/*.eval
	$(PY) rescore.py results/rescored-heldout.jsonl logs/heldout/*.eval

test:              ## self-tests: checks (good runs pass, bad runs fail, do-nothing and talk-only agents fail) and judge.py offline
	$(PY) -m pytest -q

all: test rescore report

regrade-dry:       ## count calls, tokens and cost of re-grading both rounds with the v2 rubrics ($0, no key)
	$(PY) judge.py --dry-run --rubrics v2 results/judged-all-rubric-v2.jsonl logs/dev/*.eval
	$(PY) judge.py --dry-run --rubrics v2 results/judged-heldout-rubric-v2.jsonl logs/heldout/*.eval

regrade:           ## PAID (about $0.07-0.19): re-grade both rounds with the v2 rubrics, then rebuild the report
	$(PY) judge.py --rubrics v2 results/judged-all-rubric-v2.jsonl logs/dev/*.eval
	$(PY) judge.py --rubrics v2 results/judged-heldout-rubric-v2.jsonl logs/heldout/*.eval
	$(PY) analyze.py
