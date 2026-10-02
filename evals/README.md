# Eval sets

One JSON file per docset: `evals/<docset_id>.json`. The docset must already be ingested.

```json
{
  "docset_id": "medset",
  "cases": [
    { "question": "What is the first-line drug for high blood pressure?", "answerable": true, "note": "optional" },
    { "question": "What is the capital city of Portugal?", "answerable": false }
  ]
}
```

`answerable: true` means the docs contain the answer. `false` is an out-of-scope question that must
trigger "I don't know" — these are what calibrate the upper bound.

Aim for 8-15 cases: a few direct questions, 2-3 paraphrases that share no keywords with the docs
(these catch lexical-gate style failures), and 3-5 out-of-scope questions including one nonsense query.

## Calibrate

```bash
python scripts/calibrate.py medset          # report distances + suggested threshold
python scripts/calibrate.py --all          # every eval set
python scripts/calibrate.py medset --apply  # write the suggestion to .env
```

The suggestion is the midpoint of the gap between the worst answerable and the best unanswerable
distance, which is the most robust point when the classes separate. If they overlap, it reports the
best-accuracy threshold instead and says so.

`--apply` stores the value in that docset's Chroma collection metadata, which takes effect on the next
`/ask` and survives restarts. `--clear` removes it so the docset falls back to the global
`ASK_MAX_DISTANCE`. `--apply-global` instead edits the shared fallback in `.env`, and refuses when
different docsets suggest different values — that guard is why per-docset `--apply` is the normal path.

Label carefully: a question marked `answerable: true` whose answer is absent from the docset will
inflate the threshold and hide real gaps. When calibrating a new docset, only carry over cases whose
answers actually exist in that corpus.