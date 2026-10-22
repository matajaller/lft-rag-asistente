import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rag"))

from questions import QUESTIONS                                              # noqa: E402
from search import keyword_search, semantic_search, hybrid_search, unique_articles  # noqa: E402

K = 6   # same number of articles the assistant sends to the model
RESULTS_FILE = ROOT / "evals" / "results.json"


def check_labels():
    """Prints the start of every expected article, so the labels can be reviewed by eye."""
    conn = sqlite3.connect(ROOT / "data" / "lft.db")
    for c in QUESTIONS:
        if c["type"] == "out_of_scope":
            continue
        print(c["q"])
        for aid in sorted(c["expected"]):
            row = conn.execute("SELECT text, derogado FROM articles WHERE id = ?", (aid,)).fetchone()
            if row is None:
                print(f"   {aid}: NOT FOUND IN DATABASE")
            elif row[1]:
                print(f"   {aid}: REPEALED")
            else:
                print(f"   {aid}: {row[0][:130].replace(chr(10), ' ')}")
    conn.close()


def first_rank(found, expected):
    for i, aid in enumerate(found, start=1):
        if aid in expected:
            return i
    return None


def eval_retrieval(cases):
    """hit@K and MRR@K for each search method on the same questions."""
    methods = {
        "keyword": keyword_search,
        "semantic": semantic_search,
        # Hybrid always includes the direct lookup; only the keyword weight changes
        "hybrid kw=1.0": lambda q, k: hybrid_search(q, k, keyword_weight=1.0),
        "hybrid kw=0.5": lambda q, k: hybrid_search(q, k, keyword_weight=0.5),
        "hybrid kw=0.25": lambda q, k: hybrid_search(q, k, keyword_weight=0.25),
        "hybrid kw=0": lambda q, k: hybrid_search(q, k, keyword_weight=0.0),
        "kw=0 + rewrite": lambda q, k: hybrid_search(q, k, rewrite=True),
    }
    summary, misses = {}, {}
    for name, fn in methods.items():
        hits, reciprocal, missed = 0, 0.0, []
        for c in cases:
            found = unique_articles(fn(c["q"], 20), k=K)
            rank = first_rank(found, c["expected"])
            if rank:
                hits += 1
                reciprocal += 1 / rank
            else:
                missed.append({"q": c["q"], "expected": sorted(c["expected"]), "found": found})
        summary[name] = {"hit_at_k": hits, "total": len(cases), "mrr": round(reciprocal / len(cases), 3)}
        misses[name] = missed
    return summary, misses


# Phrases that show the answer acknowledged the question is outside the LFT
LIMITATION_MARKERS = ["no encontr", "otra ley", "otras leyes", "ley del", "no regula",
                      "no cubre", "no establece", "no responde", "fuera de"]


def eval_answers(cases):
    """Calls the full assistant; each check is a rule, so results are repeatable."""
    from answer import answer   # imported here so retrieval-only runs don't need the API key

    results = []
    for c in cases:
        r = answer(c["q"])
        text = r["answer"].lower()
        failures = []
        if r.get("truncated"):
            failures.append("answer was cut off (ran out of tokens)")
        if "no sustituye la asesor" not in text:
            failures.append("missing disclaimer")
        if r["unsupported"]:
            failures.append(f"cited articles that were not retrieved: {r['unsupported']}")
        if c["type"] == "out_of_scope":
            # Citing related LFT articles is fine, as long as the answer says the question isn't covered
            if r["cited"] and not any(m in text for m in LIMITATION_MARKERS):
                failures.append(f"cited {r['cited']} without saying the question is outside the LFT")
        else:
            cited = {x.lower() for x in r["cited"]}
            if not cited & {e.lower() for e in c["expected"]}:
                failures.append(f"did not cite any of {sorted(c['expected'])} (cited {r['cited']})")
        results.append({"q": c["q"], "type": c["type"], "passed": not failures,
                        "failures": failures, "cited": r["cited"], "answer": r["answer"]})
        print(f"  {'PASS' if not failures else 'FAIL'}  {c['q'][:70]}")
        for f in failures:
            print(f"        - {f}")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-labels", action="store_true", help="print expected articles for review")
    parser.add_argument("--answers", action="store_true", help="also evaluate full answers (uses the API)")
    args = parser.parse_args()

    if args.check_labels:
        check_labels()
        return

    t0 = time.time()
    in_scope = [c for c in QUESTIONS if c["type"] != "out_of_scope"]
    summary, misses = eval_retrieval(in_scope)

    print(f"=== Retrieval: {len(in_scope)} questions, top {K} articles ===")
    for name, s in summary.items():
        print(f"  {name:<15} hit@{K}: {s['hit_at_k']}/{s['total']}   MRR: {s['mrr']}")
    print("\nMisses with the default (semantic + lookup + rewrite):")
    for m in misses["kw=0 + rewrite"]:
        print(f"  {m['q']}\n     expected {m['expected']}, found {m['found']}")

    output = {"retrieval": summary, "retrieval_misses": misses}

    if args.answers:
        print(f"\n=== Answers: {len(QUESTIONS)} questions ===")
        answers = eval_answers(QUESTIONS)
        passed = sum(a["passed"] for a in answers)
        print(f"\nAnswers passed: {passed}/{len(answers)}")
        output["answers"] = {"passed": passed, "total": len(answers), "cases": answers}

    RESULTS_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone in {time.time() - t0:.0f}s. Results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()