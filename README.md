# RAG Generator Service

Upload documents at runtime, then ask questions answered only from those documents, with citations.
FastAPI + persistent Chroma + sentence-transformers, with a Streamlit UI on top.

## Contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Run it locally](#run-it-locally)
4. [Verify it works](#verify-it-works)
5. [Try it end to end with curl](#try-it-end-to-end-with-curl)
6. [The web UI](#the-web-ui)
7. [Calibrating the threshold](#calibrating-the-threshold)
8. [Run it in Docker](#run-it-in-docker)
9. [Configuration](#configuration)
10. [Layout](#layout)
11. [Gotchas](#gotchas)

## What it does

- `/ingest` takes `.pdf`, `.txt`, `.md` at runtime, chunks them on sentence boundaries at ~500 tokens
  with 50-token overlap, and stores them in a Chroma collection per docset
- `/ask` retrieves the top 5 passages for a docset, discards anything past that docset's relevance
  threshold, and answers from what is left at temperature 0 with `[1]`-style citations
- Nothing relevant means `I don't know based on the provided documents.` — no citations, no invention
- Duplicate content is skipped on upload and collapsed on search, per docset
- Runs with no API key: set `LLM_MODEL` to swap the extractive fallback for a real LLM

## Architecture

```
  browser ──▶ Streamlit UI (ui/)
                   │  POST /ingest                    ┌──────────────────────────────┐
                   ├────────────────────────────────▶ │ FastAPI (app/api/routes/)    │
                   │                                   │  ingest / ask / docsets      │
                   │  POST /ask                        └──────────────┬───────────────┘
                   │                                                  │
                   │                                   ┌──────────────▼───────────────┐
                   │                                   │ services/                   │
                   │                                   │  loaders.py    pdf/txt/md   │
                   │                                   │  chunker.py    ~500 tok / 50 │
                   │                                   │  dedupe.py     per docset   │
                   │                                   │  vectorstore.py              │
                   │                                   │  retrieval.py  top-k + dist │
                   │                                   │  qa.py         threshold,   │
                   │                                   │                prompt, cites │
                   │                                   │  evaluation.py              │
                   │                                   └──────────────┬───────────────┘
                   │                                                  │
                   │                                   ┌──────────────▼───────────────┐
                   └────────────────────────────────── │ Chroma (persistent)          │
                       grounded answer + citations     │ one collection per docset:   │
                                                       │ chunks + threshold override  │
                                                       └──────────────────────────────┘

  evals/<docset>.json ──▶ scripts/calibrate.py ──▶ per-docset threshold override
```

Flow for `/ask`: retrieve top-k from the docset's collection → drop passages beyond the docset's
threshold → nothing left means "I don't know" → otherwise build a numbered, cited context and
generate at temperature 0.

## Run it locally

**Prerequisites:** Python 3.11 or 3.12, and roughly 6 GB of free disk for the dependencies. The
embedding model (~90 MB) downloads on the first ingest, so give that first request a generous timeout.

```bash
# 1. get the code and enter the project directory
cd health-recon-rag-assignment

# 2. create an isolated environment (a system Python install will conflict)
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. install dependencies (a few minutes; torch is the bulk of it)
pip install --upgrade pip
pip install -r requirements.txt

# 4. create your config
cp .env.example .env

# 5. start the API
uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
source .venv/bin/activate
streamlit run ui/streamlit_app.py        # http://localhost:8501
```

The UI defaults to `http://rag-test:8000` for Docker. On your machine, set the sidebar's **API base
URL** to `http://localhost:8000`.

## Verify it works

With the API running, in a third terminal:

```bash
source .venv/bin/activate
python scripts/smoke_test.py                       # defaults to http://localhost:8000
python scripts/smoke_test.py --base-url http://localhost:8030   # e.g. the Docker port
```

It checks the whole flow — health, docset listing, upload, duplicate suppression, grounded answers
with citations, the don't-know path, threshold resolution and the error cases — then deletes the
docset it created:

```
service
  PASS  GET /health — {"status":"ok"}
  PASS  GET /docsets lists docsets — {"docsets":["medset"]}

ingest
  PASS  first upload stores chunks — {"docset_id":"smoketest","count":1}
  PASS  re-upload adds nothing (dedupe) — {"docset_id":"smoketest","count":0}
  PASS  same content, new filename (dedupe) — {"docset_id":"smoketest","count":0}
  PASS  partially new file stores only new text — {"docset_id":"smoketest","count":1}
  PASS  unsupported file type rejected — status 400

ask
  PASS  grounded answer returns — Based on the retrieved documents [1] [2]: Hypertension manag
  PASS  answer carries citations — 2 citation(s)
  PASS  response reports the threshold in force — 0.75 (global)
  PASS  out-of-scope question says don't know — I don't know based on the provided documents.
  PASS  don't-know has no citations
  PASS  unknown docset falls back to global threshold
  PASS  empty question rejected — status 422

thresholds
  PASS  unknown docset reports global fallback

19 passed, 0 failed
```

Exit code is 0 on success, 1 on any failure, so it works in CI too. Safe to run repeatedly.

## Try it end to end with curl

No UI needed. Create a demo docset:

```bash
cat > /tmp/bp.txt <<'EOF'
Hypertension management requires regular blood pressure monitoring and a low sodium diet.
ACE inhibitors are first-line pharmacologic therapy for high blood pressure.
Patients should be rechecked every three months and counseled on medication adherence.
Diabetes mellitus type 2 is managed with metformin as first-line therapy.
HbA1c should be measured every three months to assess glycemic control.
Asthma is treated with inhaled corticosteroids as controller therapy.
Rescue inhalers such as albuterol relieve acute bronchospasm within minutes.
EOF

curl -s -X POST http://localhost:8000/ingest \
  -F "files=@/tmp/bp.txt" -F "docset_id=medset"
# {"docset_id":"medset","count":1}

curl -s -X POST http://localhost:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the first-line drug for high blood pressure?","docset_id":"medset"}'
```

```json
{
  "docset_id": "medset",
  "answer": "Based on the retrieved documents [1]: Hypertension management requires ...",
  "citations": [{"id": 1, "source": "bp.txt", "page": null, "chunk_index": 0}],
  "threshold": 0.75,
  "threshold_source": "global"
}
```

Upload the same file again and you get `"count":0` — duplicates are skipped per docset. Ask about
something unrelated and you get the don't-know answer with no citations.

[`evals/medset.json`](evals/medset.json) is a ready-made eval set written against exactly this demo
docset, so the calibration section below works straight after these commands.

## The web UI

`streamlit run ui/streamlit_app.py`

- **Upload tab** — drop `.pdf` / `.txt` / `.md`, press Ingest. It targets whichever docset is selected
  in the Chat tab unless you type a different one, and switches the selection to a newly created docset
- **Chat tab** — a dropdown of docsets that already exist (plus `＋ new docset…`), the active relevance
  threshold underneath, and the question box above the conversation so it stays put as history grows
- Citations show source and page. `chunk_index` is still in the API response, just not rendered here

Docsets come from whichever `CHROMA_PERSIST_DIR` the API is serving, so two instances started from
different directories show different dropdowns.

## Calibrating the threshold

The relevance cut-off is a squared-L2 distance on MiniLM embeddings, measured rather than guessed.
Each docset can carry its own value in its Chroma collection metadata; `ASK_MAX_DISTANCE` is the shared
fallback. `/ask` reports which it used in `threshold_source`.

Write `evals/<docset_id>.json` with labelled questions — see [`evals/README.md`](evals/README.md) for
the format and how to write good cases — then:

```bash
python scripts/calibrate.py medset          # per-case distances + a suggested threshold
python scripts/calibrate.py --all          # every eval set
python scripts/calibrate.py medset --apply  # store it as that docset's override
python scripts/calibrate.py medset --clear  # drop the override, fall back to global
```

```
=== medset (10 cases, threshold=0.75 from global)
  ok  answerable   best=0.4245  What is the first-line drug for high blood pressure?
  ok  answerable   best=0.7065  How is sugar control tracked over time?
  ok  unanswerable best=0.9468  What is the capital city of Portugal?
  ...
  accuracy at current threshold: 100%
  suggested threshold: 0.837 (separable) | answerable_max=0.7272 unanswerable_min=0.9468
```

The suggestion is the midpoint between the worst answerable and the best unanswerable distance, the
most robust point when the two classes separate; when they overlap it reports the best-accuracy
threshold instead and says so. `--apply` takes effect immediately, no restart. `--apply-global` edits
`.env` and refuses when docsets disagree.

Recalibrate after changing `EMBEDDING_MODEL`, the chunker, or re-ingesting a corpus — the distance
scale shifts and stored overrides go stale.

## Run it in Docker

```bash
# 1. build
docker build -t rag-generator .

# 2. one network so the UI can reach the API by name
docker network create rag-net

# 3. the API, named rag-test to match the UI's default URL
docker run -d --name rag-test --network rag-net -p 8000:8000 \
  -v $(pwd)/data:/app/data --env-file .env rag-generator

# 4. the UI
docker run -d --name rag-ui --network rag-net -p 8501:8501 rag-generator \
  streamlit run ui/streamlit_app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true

# 5. check both
curl -s http://localhost:8000/health          # {"status":"ok"}
open http://localhost:8501

# 6. verify the deployment
python scripts/smoke_test.py --base-url http://localhost:8000

# 7. tear down
docker rm -f rag-test rag-ui && docker network rm rag-net
```

The UI defaults to `http://rag-test:8000`, so with the network and container name above it needs no
configuration. If you name the API container something else, either name it `rag-test` or change the
sidebar field.

The image ships `app`, `ui`, `evals` and `scripts` but not `.env` or `data/` (see `.dockerignore`), so
configuration comes from `--env-file` and documents live in the mounted volume. Chroma state and
threshold overrides survive restarts.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `rag-generator` | service name in `/` and the OpenAPI title |
| `APP_ENV` | `dev` | free-form environment label |
| `APP_PORT` | `8000` | port the app expects to be served on |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | where documents and thresholds are stored |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | sentence-transformers model; changing it invalidates thresholds |
| `CHUNK_MAX_TOKENS` | `500` | target chunk size in tokens |
| `CHUNK_OVERLAP_TOKENS` | `50` | overlap carried between chunks |
| `ASK_TOP_K` | `5` | passages retrieved per question |
| `ASK_MAX_DISTANCE` | `0.75` | global fallback threshold; per-docset overrides win |
| `LLM_MODEL` | *(empty)* | any litellm model name; empty = extractive cited fallback |
| `LLM_TEMPERATURE` | `0.0` | generation temperature |
| `EVAL_DIR` | `./evals` | where eval sets live |

API keys are read from the environment by litellm (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …), not from
`.env` settings. Copy `.env.example` to `.env` to start.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | `{"status":"ok"}` |
| `GET /` | service info |
| `POST /ingest` | multipart `files`, optional `docset_id` → `{"docset_id","count"}`; duplicates skipped |
| `POST /ask` | `{"question","docset_id"}` → answer, citations, threshold in force |
| `GET /docsets` | `{"docsets":[...]}` |
| `GET /docsets/{id}/threshold` | `{"docset_id","threshold","source"}` (`docset` or `global`) |
| `GET /docs` | interactive OpenAPI browser |

Errors: unsupported file type or no extractable text → 400; missing/empty fields → 422.

## Layout

```
app/
  main.py              FastAPI entrypoint
  core/config.py       env-based settings
  api/routes/          health.py, ingest.py, ask.py, docsets.py
  services/            loaders, chunker, dedupe, vectorstore, retrieval, qa, evaluation
  models/schemas.py    request/response models
ui/streamlit_app.py    upload + chat UI (HTTP client, shares no code with the API)
scripts/
  smoke_test.py        end-to-end check against a running instance
  calibrate.py         threshold calibration from eval sets
evals/<docset>.json    labelled questions per docset
data/chroma/           persistent Chroma dir (gitignored, mount as a volume)
```

## Gotchas

- **Use a venv.** `requirements.txt` pins `transformers<5` (v5 will not load torch below 2.5 and
  silently disables the backend) and `numpy<2` (torch 2.2.2 is built against numpy 1 and raises
  `Numpy is not available` on `encode()` under numpy 2). Installing into a system or conda base
  environment is how both bite.
- **Don't downgrade protobuf.** `streamlit==1.64.0` and `chromadb` both need protobuf 6+. Older
  streamlit releases cap it below that, which breaks chromadb.
- **First ingest is slow** — it downloads the embedding model. Later calls are fast.
- **Only create Chroma collections through this code.** They must carry the project's embedding
  function, otherwise the distance scale differs and the calibrated threshold silently rejects
  everything. Use `vectorstore.get_collection()` rather than touching the Chroma client directly.
- **Data location decides what you see.** Two instances with different `CHROMA_PERSIST_DIR` hold
  different docsets, and the UI dropdown only lists the ones the API it talks to can see.
- **There is no delete endpoint.** Removing a docset means deleting its collection from
  `./data/chroma`, or starting with an empty `data/` directory.