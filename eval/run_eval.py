"""Measure ScopeClear against the planted changes. Uses real Gemini.

  GOOGLE_CLOUD_PROJECT=your-project STORE=memory python -m eval.run_eval --runs 3

Prints detection, type accuracy, quote verification and question coverage,
and writes eval/results.json. These are the only numbers to report.
"""
import argparse
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

GT = json.loads((Path(__file__).parent / "ground_truth.json").read_text())


def score(state):
    found = state["changes"]
    text = lambda c: (c["title"] + " " + c["new_request"]).lower()
    rows = []
    for g in GT["changes"]:
        hit = next((c for c in found if any(k in text(c) for k in g["match_any"])), None)
        rows.append({"key": g["key"], "detected": bool(hit), "type_ok": bool(hit and hit["type"] == g["type"]),
                     "asked": bool(hit and hit["questions"]) if g["must_ask"] else None,
                     "flag_issues": hit["issues"] if hit else None})
    a = state["last_analysis"]
    matched = {id(c) for g in GT["changes"] for c in found if any(k in text(c) for k in g["match_any"])}
    return {"rows": rows, "detected": sum(r["detected"] for r in rows), "planted": len(rows),
            "type_ok": sum(r["type_ok"] for r in rows),
            "must_ask_ok": sum(1 for r in rows if r["asked"]), "must_ask_total": sum(1 for g in GT["changes"] if g["must_ask"]),
            "quotes_verified": a["quotes_verified"], "quotes": a["quotes"],
            "extra_items": len([c for c in found if id(c) not in matched]), "model": a["model"]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", type=int, default=3); args = ap.parse_args()
    c = TestClient(app); results = []
    for r in range(args.runs):
        pid = c.post("/api/demo").json()["id"]
        res = c.post(f"/api/projects/{pid}/analyze")
        res.raise_for_status()
        s = score(res.json()); results.append(s)
        print(f"Run {r + 1}: detected {s['detected']}/{s['planted']}, type correct {s['type_ok']}/{s['planted']}, "
              f"asked when info missing {s['must_ask_ok']}/{s['must_ask_total']}, quotes verified {s['quotes_verified']}/{s['quotes']}, "
              f"extra items {s['extra_items']}")
    (Path(__file__).parent / "results.json").write_text(json.dumps(results, indent=2))
    tot = lambda k: sum(x[k] for x in results)
    print(f"\nTotal over {args.runs} runs: detected {tot('detected')}/{tot('planted')}, "
          f"type correct {tot('type_ok')}/{tot('planted')}, quotes verified {tot('quotes_verified')}/{tot('quotes')}")


if __name__ == "__main__":
    main()
