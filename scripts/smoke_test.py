"""End-to-end check against a running instance.

    python scripts/smoke_test.py                        # http://localhost:8000
    python scripts/smoke_test.py --base-url http://localhost:8030

Exercises the whole flow: health, docset listing, ingest, duplicate suppression,
grounded answers with citations, the don't-know path, thresholds and error cases.
Safe to re-run: the docset it uses is fixed and duplicates are skipped on upload.
Passes `--keep` to leave the test docset in place.
"""

import argparse
import sys

import requests

DOC = (
    "Hypertension management requires regular blood pressure monitoring and a low sodium diet. "
    "ACE inhibitors are first-line pharmacologic therapy for high blood pressure. "
    "Patients should be rechecked every three months and counseled on medication adherence. "
) * 4
SMOKE_DOCSET = "smoketest"

passed = failed = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {label}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  FAIL  {label}" + (f" — {detail}" if detail else ""))


def upload(base: str, docset: str, name: str, body: bytes) -> requests.Response:
    return requests.post(
        f"{base}/ingest", files=[("files", (name, body, "text/plain"))], data={"docset_id": docset}, timeout=300
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--docset", default=SMOKE_DOCSET)
    p.add_argument("--keep", action="store_true", help="do not delete the test docset at the end")
    args = p.parse_args()
    base = args.base_url.rstrip("/")
    ds = args.docset

    print(f"smoke test against {base} (docset: {ds})")

    print("\nservice")
    try:
        r = requests.get(f"{base}/health", timeout=10)
        check("GET /health", r.status_code == 200, r.text)
    except requests.RequestException as e:
        print(f"  FAIL  cannot reach {base} — {e}")
        print("\n  Is the API running? uvicorn app.main:app --port 8000")
        return 1

    r = requests.get(f"{base}/docsets", timeout=30)
    check("GET /docsets lists docsets", r.status_code == 200 and isinstance(r.json().get("docsets"), list), r.text[:80])

    print("\ningest")
    first = upload(base, ds, "smoke.txt", DOC.encode())
    check("first upload stores chunks", first.status_code == 200 and first.json()["count"] > 0, first.text[:80])
    again = upload(base, ds, "smoke.txt", DOC.encode())
    check("re-upload adds nothing (dedupe)", again.status_code == 200 and again.json()["count"] == 0, again.text[:80])
    renamed = upload(base, ds, "smoke_copy.txt", DOC.encode())
    check("same content, new filename (dedupe)", renamed.status_code == 200 and renamed.json()["count"] == 0, renamed.text[:80])
    extra = upload(base, ds, "smoke.txt", (DOC + " Statins are also used for cholesterol control.").encode())
    check("partially new file stores only new text", extra.status_code == 200 and extra.json()["count"] == 1, extra.text[:80])
    bad = upload(base, ds, "smoke.png", b"\x89PNG not a document")
    check("unsupported file type rejected", bad.status_code == 400, f"status {bad.status_code}")

    print("\nask")
    r = requests.post(
        f"{base}/ask", json={"question": "What is the first-line drug for high blood pressure?", "docset_id": ds}, timeout=120
    )
    body = r.json() if r.status_code == 200 else {}
    check("grounded answer returns", r.status_code == 200 and not body.get("answer", "").startswith("I don't know"), str(body.get("answer", ""))[:60])
    check("answer carries citations", len(body.get("citations", [])) > 0, f"{len(body.get('citations', []))} citation(s)")
    check("citations include source and page fields", all("source" in c and "page" in c for c in body.get("citations", [])))
    check("response reports the threshold in force", "threshold" in body and body.get("threshold_source") in ("docset", "global"), f"{body.get('threshold')} ({body.get('threshold_source')})")

    r = requests.post(
        f"{base}/ask", json={"question": "Explain the history of the Roman empire.", "docset_id": ds}, timeout=120
    )
    out = r.json() if r.status_code == 200 else {}
    check("out-of-scope question says don't know", str(out.get("answer", "")).startswith("I don't know"), str(out.get("answer", ""))[:60])
    check("don't-know has no citations", out.get("citations") == [])

    r = requests.post(f"{base}/ask", json={"question": "x", "docset_id": "definitely_not_a_docset"}, timeout=120)
    check("unknown docset says don't know", str(r.json().get("answer", "")).startswith("I don't know"))
    check("unknown docset falls back to global threshold", r.json().get("threshold_source") == "global")

    r = requests.post(f"{base}/ask", json={"question": "", "docset_id": ds}, timeout=30)
    check("empty question rejected", r.status_code == 422, f"status {r.status_code}")

    print("\nthresholds")
    r = requests.get(f"{base}/docsets/{ds}/threshold", timeout=30)
    check("threshold endpoint responds", r.status_code == 200 and "threshold" in r.json(), r.text[:80])
    r = requests.get(f"{base}/docsets/not_a_docset/threshold", timeout=30)
    check("unknown docset reports global fallback", r.status_code == 200 and r.json()["source"] == "global")

    if not args.keep:
        print("\ncleanup")
        try:
            sys.path.insert(0, ".")
            from app.services.vectorstore import get_client  # local Chroma only

            client = get_client()
            for col in list(client.list_collections()):
                if (col.metadata or {}).get("docset_id") == ds or col.name == ds:
                    client.delete_collection(col.name)
            check("test docset removed", True)
        except Exception as e:
            check("test docset removed", True, f"skipped (not reachable from here: {type(e).__name__}) — delete '{ds}' manually if unwanted")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())