# OpsBench: auditing the graders of agent safety evals

[![attested by humans](https://github.com/aidankaras/opsbench/actions/workflows/git-signoff.yml/badge.svg)](https://github.com/aidankaras/opsbench/actions/workflows/git-signoff.yml)

Agent benchmarks are scored by programmatic checks or by LLM judges, and both get treated as ground truth. This project measures how often each one is wrong on agent safety tasks, using human-reviewed labels on the cases where they disagree.

![Grader verdicts vs human-reviewed labels](figures/grader_accuracy.png)

## Result
- The original programmatic checks were right on 38 of 98 labeled disagreements. Most errors were false fails: the checks could not see the agent's final reply or read-only tool calls.
- After repairing them with the development labels, the checks were right on 56 of 63 disagreements in a fresh held-out run.
- On that held-out run, the GPT-6 Luna judge was right on 28 of 57 and the Mistral Small judge on 19 of 63. Both judges erred in both directions, mostly by failing correct runs.

These are accuracies on disagreement cases only, not overall error rates. Full write-up, method and limits: [REPORT.md](REPORT.md).

## What's here
- `opsbench/` 28 tasks across 7 trap types (prompt injection, destructive action, tool error, scope creep, ambiguity, calendar conflict, policy), each with a simulated workspace, a programmatic check, and a rubric written before any model run.
- `opsbench_task.py` the [Inspect](https://inspect.aisi.org.uk/) task.
- `judge.py` LLM-judge pass over finished logs. Judges never grade a model from their own family.
- `rescore.py` re-applies the checks to saved logs with no API calls.
- `label_batches.py` builds blind labeling batches from disagreements (labelers do not see any verdict).
- `labels/` human labels, rule labels with the rule used for each, and spot-check results.
- `logs/` the raw Inspect logs for both rounds (4 models x 28 tasks x 3 epochs each).
- `analyze.py` computes every number in the report and draws the figure.

## Reproduce
```
pip install -r requirements.txt   # Python 3.14
make test       # check self-tests, including do-nothing and talk-only agents
make rescore    # re-score saved logs, $0
make report     # rebuild results/summary.json and the figure, $0
```
Re-running the agents or judges needs an OpenRouter API key (see `judge.py`). Both rounds together cost about $0.31.

## Limits
One human labeler. Rule labels were spot-checked (20 of 20 agreed), not fully reviewed. 28 tasks and small, cheap models. Cases where all graders were wrong together are not measured.

MIT license.
