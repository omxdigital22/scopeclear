"""MOCK MODE: for building the UI without Gemini. Never use it for judging.

It reads real lines from the demo files, so citations and verification still
work for real. Only the "understanding" step is scripted. The UI shows a
banner whenever this mode is on.
"""
import json
import re
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo"


def script_for(name: str) -> list[str]:
    stem = Path(name).stem
    try:
        for e in json.loads((DEMO / "inputs" / "manifest.json").read_text()):
            if e["name"] == name:
                stem = Path(e["file"]).stem
    except FileNotFoundError:
        pass
    path = DEMO / "scripts" / f"{stem}.txt"
    if not path.exists():
        return ["[Mock mode has no transcript for this file. Turn mock mode off to use Gemini.]"]
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]


def _line(chunks: list[dict], keyword: str) -> tuple[str, str] | None:
    for c in chunks:
        for ln in c["text"].splitlines():
            if keyword.lower() in ln.lower():
                ln = re.sub(r"^\[[^\]]+\]\s*[^:]+:\s*", "", ln.strip())  # strip WhatsApp prefix
                return c["id"], ln.lstrip("- ").strip()
    return None


def baseline(base_chunks: list[dict]) -> list[dict]:
    tasks, out_of_scope = [], False
    for c in base_chunks:
        for ln in c["text"].splitlines():
            s = ln.strip()
            if "out of scope" in s.lower():
                out_of_scope = True
            if out_of_scope or "FICTIONAL" in s:
                continue
            if s.startswith("- ") or "will support" in s:
                q = s.lstrip("- ").strip()
                tasks.append({"title": q.rstrip("."), "source_id": c["id"], "quote": q})
    return tasks


RULES = [
    {"key": "partial", "type": "modification", "title": "Partial payments across multiple accounts",
     "req": ["partial payments", "second bank account"], "agreed": ["cash only", "single collections account"],
     "prev": "Customers pay in cash only, each invoice is paid in full, and all money goes to one collections account.",
     "new": "Customers can pay part in cash and the rest later by UPI, and UPI money goes to a second bank account.",
     "qs": [("Should the balance be tracked per invoice, or as one running balance per customer?",
             "Decides how payments are matched and what the outstanding report shows.", True),
            ("Which bank accounts should staff be able to choose when recording a payment?",
             "The account list cannot be guessed.", True),
            ("If a customer pays more than the invoice amount, what should happen to the extra?",
             "Overpayments need a rule before collections can be recorded.", False)]},
    {"key": "whatsapp", "type": "contradiction", "title": "WhatsApp payment reminders",
     "req": ["reminders to customers on WhatsApp"], "agreed": ["WhatsApp or SMS messages"],
     "prev": "WhatsApp or SMS messages to customers are out of scope for this phase.",
     "new": "Send payment reminders to customers on WhatsApp.",
     "qs": [("When should a reminder be sent, and how often?", "Reminder timing is not stated.", True),
            ("Is this change accepted into this phase, given the proposal lists WhatsApp as out of scope?",
             "It reverses an explicit exclusion.", True)]},
    {"key": "excel", "type": "contradiction", "title": "Excel report requested, then withdrawn",
     "req": ["forget it, PDF is fine"], "conflict": ["Excel also"], "agreed": ["downloadable as PDF"],
     "prev": "The daily collections report is downloadable as PDF.",
     "new": "The client first asked for Excel as well, then said PDF is fine.",
     "qs": [("Please confirm: is the PDF report enough, with no Excel export?",
             "Two messages disagree.", False)]},
    {"key": "users", "type": "modification", "title": "Fewer staff users",
     "req": ["only 3 users"], "agreed": ["5 staff users"],
     "prev": "5 staff users: 1 owner, 2 billing staff and 2 delivery staff.",
     "new": "Only 3 users are needed now.",
     "qs": [("Which 3 roles should the users have?", "The role split for 3 users is not stated.", True)]},
    {"key": "discount", "type": "unclear", "title": "Customer-specific discounts",
     "req": ["discount on every invoice"], "agreed": [],
     "prev": "Not covered in the original scope.",
     "new": "Some regular customers get a discount on every invoice; details will come from the client's brother.",
     "qs": [("Which customers get a discount?", "The customer list is not given.", True),
            ("Is the discount a percentage or a fixed amount, and how much for each customer?",
             "No value is stated.", True),
            ("Is the discount applied before or after GST?", "Changes the invoice total.", True)]},
    {"key": "gstin", "type": "addition", "title": "Show customer GSTIN on invoice",
     "req": ["GSTIN"], "agreed": [], "prev": "Not covered in the original scope.",
     "new": "Show the customer's GSTIN on every invoice.",
     "qs": [("What should the invoice show for customers without a GSTIN?",
             "Some retail shops may not be registered.", False)]},
    {"key": "delivered", "type": "addition", "title": "Delivered-by name on invoice",
     "req": ["Delivered by"], "agreed": [], "prev": "Not covered in the original scope.",
     "new": "Add the name of the person who delivered to every invoice.",
     "qs": []},
]


def analysis(base_chunks: list[dict], req_chunks: list[dict]) -> list[dict]:
    items = []
    for r in RULES:
        ev = []
        for kw in r["req"]:
            hit = _line(req_chunks, kw)
            if hit:
                ev.append({"role": "requested", "source_id": hit[0], "quote": hit[1]})
        if not ev:
            continue
        for kw in r.get("conflict", []):
            hit = _line(req_chunks, kw)
            if hit:
                ev.append({"role": "conflicting", "source_id": hit[0], "quote": hit[1]})
        for kw in r["agreed"]:
            hit = _line(base_chunks, kw)
            if hit:
                ev.append({"role": "agreed", "source_id": hit[0], "quote": hit[1]})
        items.append({"type": r["type"], "title": r["title"], "previously_agreed": r["prev"],
                      "new_request": r["new"], "evidence": ev, "_mock": r["key"],
                      "questions": [{"question": q, "why_needed": w, "blocking": b} for q, w, b in r["qs"]]})
    return items


def ops(tasks: list[dict], change: dict, answers: dict) -> list[dict]:
    active = [t for t in tasks if t["status"] != "removed"]

    def find(word):
        return next((t["id"] for t in active if word.lower() in t["title"].lower()), "")

    vals = [v for v in answers.values() if v]
    a = vals[0] if vals else ""
    key = change.get("_mock", "")
    out = []
    if key == "partial":
        out += [{"op": "update", "task_id": find("cash only"), "title": "Record payments in cash or UPI, including part payments",
                 "reason": "Approved: customers may pay part in cash and the rest by UPI."},
                {"op": "update", "task_id": find("Paid in full"), "title": f"Track balances {a.split('.')[0].lower() or 'as answered'}; mark Paid when the balance is zero",
                 "reason": "Approved: invoices can now be partly paid."},
                {"op": "update", "task_id": find("single collections account"), "title": "Record which bank account each payment goes to",
                 "reason": "Approved: UPI goes to a second account."}]
    elif key == "users":
        out.append({"op": "update", "task_id": find("5 staff users"), "title": f"Set up 3 staff users: {a or 'roles as answered'}",
                    "reason": "Approved: user count reduced to 3."})
    elif key == "excel":
        out.append({"op": "add", "task_id": "", "title": "Keep the daily report as PDF only (Excel withdrawn by client)",
                    "reason": "Approved: client withdrew the Excel request."})
    else:
        out.append({"op": "add", "task_id": "", "title": change["new_request"].rstrip(".") + (f" ({a})" if a else ""),
                    "reason": f"Approved change: {change['title']}."})
    return [o for o in out if o["op"] == "add" or o["task_id"]]
