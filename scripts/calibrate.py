import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402
from app.services.evaluation import (  # noqa: E402
    accuracy,
    available_docsets,
    run_eval,
    suggest_threshold,
)
from app.services.vectorstore import (  # noqa: E402
    clear_docset_threshold,
    get_docset_threshold,
    set_docset_threshold,
)


def report(docset_id: str) -> dict | None:
    rows = run_eval(docset_id)
    if not rows:
        print(f"{docset_id}: eval set is empty, skipping")
        return None
    threshold, source = get_docset_threshold(docset_id)
    print(f"\n=== {docset_id} ({len(rows)} cases, threshold={threshold} from {source})")
    for r in rows:
        flag = "ok " if r["correct"] else "BAD"
        kind = "answerable  " if r["answerable"] else "unanswerable"
        d = f"{r['best_distance']:.4f}" if r["best_distance"] is not None else "   n/a"
        note = f"  ({r['note']})" if r["note"] else ""
        print(f"  {flag} {kind} best={d}  {r['question'][:52]}{note}")

    s = suggest_threshold(rows)
    print(f"  accuracy at current threshold: {accuracy(rows):.0%}")
    if s["suggested"] is None:
        print(f"  suggested threshold: none — {s['reason']}")
    else:
        sep = "separable" if s["separable"] else "OVERLAPPING"
        detail = (
            f" | answerable_max={s['answerable_max']} unanswerable_min={s['unanswerable_min']}"
            if s["separable"]
            else f" | {s['reason']}"
        )
        print(f"  suggested threshold: {s['suggested']} ({sep}){detail}")
    return {"docset_id": docset_id, "suggested": s["suggested"], "accuracy": accuracy(rows)}


def write_global(value: float, env_file: Path = Path(".env")) -> None:
    key = "ASK_MAX_DISTANCE"
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    out, replaced = [], False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    env_file.write_text("\n".join(out) + "\n")
    print(f"updated {env_file}: {key}={value} (fallback for docsets with no override)")


def main() -> None:
    p = argparse.ArgumentParser(description="Recalibrate the retrieval threshold from a docset eval set")
    p.add_argument("docset_id", nargs="?", help="docset id (defaults to --all)")
    p.add_argument("--all", action="store_true", help="run every eval set in EVAL_DIR")
    p.add_argument("--apply", action="store_true", help="store the suggestion as this docset's override")
    p.add_argument("--apply-global", action="store_true", help="write the shared fallback into .env")
    p.add_argument("--clear", action="store_true", help="remove a docset override, falling back to global")
    args = p.parse_args()

    docsets = available_docsets() if (args.all or not args.docset_id) else [args.docset_id]
    if not docsets:
        print(f"no eval sets found in {settings.eval_dir}")
        return

    if args.clear:
        for docset_id in docsets:
            try:
                clear_docset_threshold(docset_id)
                print(f"{docset_id}: override cleared, using global {settings.ask_max_distance}")
            except ValueError as e:
                print(f"{docset_id}: {e}")
        return

    results = [r for r in (report(d) for d in docsets) if r]

    if args.apply:
        for r in results:
            if r["suggested"] is None:
                print(f"{r['docset_id']}: no suggestion, override left unchanged")
                continue
            previous, _ = get_docset_threshold(r["docset_id"])
            try:
                set_docset_threshold(r["docset_id"], r["suggested"])
                print(f"{r['docset_id']}: override {previous} -> {r['suggested']}")
            except ValueError as e:
                print(f"{r['docset_id']}: {e}")

    if args.apply_global:
        values = {r["suggested"] for r in results if r["suggested"] is not None}
        if len(values) != 1:
            print(f"\nskipping --apply-global: {len(values)} distinct suggestions ({sorted(values)})")
            return
        write_global(values.pop())


if __name__ == "__main__":
    main()