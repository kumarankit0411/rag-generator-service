import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.retrieval import retrieve
from app.services.vectorstore import get_docset_threshold


class EvalCase(BaseModel):
    question: str = Field(min_length=1)
    answerable: bool
    note: str = ""


class EvalSet(BaseModel):
    docset_id: str = Field(min_length=1)
    cases: list[EvalCase] = Field(min_length=1)


def eval_path(docset_id: str) -> Path:
    return Path(settings.eval_dir) / f"{docset_id}.json"


def load_eval_set(docset_id: str) -> EvalSet:
    path = eval_path(docset_id)
    if not path.exists():
        raise FileNotFoundError(f"no eval set at {path}")
    return EvalSet.model_validate(json.loads(path.read_text()))


def available_docsets() -> list[str]:
    d = Path(settings.eval_dir)
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def run_eval(docset_id: str, top_k: int | None = None) -> list[dict]:
    """Best-passage distance per case, plus whether the live threshold answers it."""
    eval_set = load_eval_set(docset_id)
    threshold, _ = get_docset_threshold(docset_id)
    rows = []
    for case in eval_set.cases:
        passages = retrieve(docset_id, case.question, top_k=top_k or settings.ask_top_k)
        best = min((p["distance"] for p in passages), default=None)
        answered = bool(passages) and min(
            p["distance"] for p in passages if p["distance"] is not None
        ) <= threshold
        rows.append(
            {
                "question": case.question,
                "note": case.note,
                "answerable": case.answerable,
                "best_distance": best,
                "answered": answered,
                "correct": answered == case.answerable,
            }
        )
    return rows


def suggest_threshold(rows: list[dict]) -> dict:
    """Pick a threshold from labelled distances.

    If the two classes separate, use the midpoint of the gap (most robust point).
    Otherwise sweep candidates for best accuracy and flag the overlap.
    """
    answerable = [r["best_distance"] for r in rows if r["answerable"] and r["best_distance"] is not None]
    unanswerable = [r["best_distance"] for r in rows if not r["answerable"] and r["best_distance"] is not None]
    if not answerable or not unanswerable:
        return {
            "suggested": None,
            "separable": False,
            "reason": "need at least one answerable and one unanswerable case with results",
        }

    hi_a, lo_u = max(answerable), min(unanswerable)
    if hi_a < lo_u:
        return {
            "suggested": round((hi_a + lo_u) / 2, 4),
            "separable": True,
            "answerable_max": round(hi_a, 4),
            "unanswerable_min": round(lo_u, 4),
            "margin": round(lo_u - hi_a, 4),
        }

    values = sorted({*answerable, *unanswerable})
    candidates = [values[0] - 1e-6] + [(a + b) / 2 for a, b in zip(values, values[1:])] + [values[-1] + 1e-6]
    best = max(
        candidates,
        key=lambda t: (
            sum(1 for d in answerable if d <= t) + sum(1 for d in unanswerable if d > t),
            sum(1 for d in answerable if d <= t),
            -t,
        ),
    )
    return {
        "suggested": round(best, 4),
        "separable": False,
        "reason": "classes overlap; best-accuracy threshold chosen instead of midpoint",
        "answerable_max": round(hi_a, 4),
        "unanswerable_min": round(lo_u, 4),
    }


def accuracy(rows: list[dict]) -> float:
    return sum(1 for r in rows if r["correct"]) / len(rows) if rows else 0.0