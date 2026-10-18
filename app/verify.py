"""Deterministic checks on everything the AI claims. Nothing here calls Gemini.

1. Every quote must exist in the chunk it cites (exact, or >= 90% fuzzy match
   to tolerate whitespace / punctuation / transcription differences).
2. A quote marked "agreed" must come from the original scope, not a new request.
3. Any number in the AI's summary (amounts, %, counts, dates) must also appear
   in the cited evidence. Otherwise it is flagged as possibly invented.
"""
import difflib
import re

FUZZY_THRESHOLD = 0.90
NUM_RE = re.compile(r"₹\s?\d[\d,]*(?:\.\d+)?|\d+(?:[.,]\d+)?\s?%|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b|\b\d+(?:\.\d+)?\b")
WORD_NUMS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
             "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^\w₹%]+", " ", s)
    return " ".join(s.split())


def quote_match(quote: str, text: str) -> float:
    q, t = norm(quote), norm(text)
    if not q:
        return 0.0
    if q in t:
        return 1.0
    qw, tw = q.split(), t.split()
    n = len(qw)
    best = 0.0
    for size in (n - 1, n, n + 1):
        if size <= 0:
            continue
        for i in range(max(1, len(tw) - size + 1)):
            window = " ".join(tw[i:i + size])
            best = max(best, difflib.SequenceMatcher(None, q, window).ratio())
    return best


def _numbers(text: str) -> set[str]:
    found = {norm(m).replace(" ", "") for m in NUM_RE.findall(text)}
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in WORD_NUMS:
            found.add(WORD_NUMS[w])
    return {f for f in found if f}


def verify_evidence(ev: dict, chunks: dict, baseline_ids: set) -> dict:
    ch = chunks.get(ev.get("source_id", ""))
    if not ch:
        ev.update(verified=False, check="Cited source does not exist", label=ev.get("source_id", "?"))
        return ev
    score = quote_match(ev.get("quote", ""), ch["text"])
    ev["label"] = ch["label"]
    ev["score"] = round(score, 3)
    if score < FUZZY_THRESHOLD:
        ev.update(verified=False, check="Quote not found in the cited source")
    elif ev.get("role") == "agreed" and ev["source_id"] not in baseline_ids:
        ev.update(verified=False, check="Marked as agreed, but the source is a new request")
    else:
        ev.update(verified=True, check="Exact match" if score == 1.0 else f"Close match ({score:.0%})")
    return ev


def verify_item(item: dict, chunks: dict, baseline_ids: set) -> dict:
    for ev in item.get("evidence", []):
        verify_evidence(ev, chunks, baseline_ids)

    issues = []
    evidence_nums = set()
    for ev in item.get("evidence", []):
        evidence_nums |= _numbers(ev.get("quote", ""))
        if ev.get("verified") and ev["source_id"] in chunks:
            evidence_nums |= _numbers(chunks[ev["source_id"]]["text"])
    for field in ("title", "previously_agreed", "new_request"):
        for num in sorted(_numbers(item.get(field, "")) - evidence_nums):
            issues.append(f"The number “{num}” is not in the cited evidence. Confirm it with the client.")

    if not any(e.get("role") == "requested" and e.get("verified") for e in item.get("evidence", [])):
        issues.append("No verified quote supports the new request.")
    claims_agreed = not item.get("previously_agreed", "").strip().lower().startswith("not covered")
    if claims_agreed:
        if not any(e.get("role") == "agreed" and e.get("verified") for e in item.get("evidence", [])):
            issues.append("No verified quote from the original scope supports “previously agreed”.")

    item["issues"] = issues
    item["verified"] = not issues and all(e.get("verified") for e in item.get("evidence", []))
    return item


def verify_task(task: dict, chunks: dict) -> dict:
    ch = chunks.get(task.get("source_id", ""))
    score = quote_match(task.get("quote", ""), ch["text"]) if ch else 0.0
    task["verified"] = score >= FUZZY_THRESHOLD
    task["label"] = ch["label"] if ch else task.get("source_id", "?")
    return task
