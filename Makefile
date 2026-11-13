PY ?= python

.PHONY: report rescore test all

report:            ## rebuild results/summary.json and figures/ from saved results ($0, seconds)
	$(PY) analyze.py

rescore:           ## re-run the programmatic checks on the saved agent logs ($0, no API calls)
	$(PY) rescore.py results/rescored.jsonl logs/dev/*.eval
	$(PY) rescore.py results/rescored-heldout.jsonl logs/heldout/*.eval

test:              ## check self-tests: good runs pass, bad runs fail, do-nothing and talk-only agents fail
	$(PY) test_checks.py
	$(PY) -c "import test_checks as t; t.test_noop_agent_fails_every_task(); t.test_final_text_alone_never_passes(); print('guards ok')"

all: test rescore report
