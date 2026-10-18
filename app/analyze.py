"""The three AI steps. Each returns plain dicts; verify.py checks them after."""
from . import gemini, mock
from .schemas import AnalysisOut, BaselineOut, ChecklistOpsOut

ANALYSIS_SYSTEM = """You help a software team control scope. You compare a client's ORIGINAL AGREED SCOPE with their NEW REQUESTS and list only what is new, changed, conflicting or unclear.

Rules you must follow:
1. Cite evidence using the chunk IDs exactly as given in square brackets, e.g. D1-P2. Copy each quote verbatim from that chunk, max 30 words. Never paraphrase inside a quote.
2. Evidence roles: "agreed" quotes come only from the ORIGINAL AGREED SCOPE. "requested" quotes come only from NEW REQUESTS. "conflicting" is any other quote the request clashes with.
3. Types:
   - addition: the original scope does not cover it.
   - modification: it changes something the original scope explicitly states.
   - contradiction: it conflicts with something the original scope explicitly excludes, or two new requests conflict with each other. When a later request reverses an earlier one, cite both and mark the earlier one "conflicting".
   - unclear: the client asks for something but leaves out what is needed to build it.
4. previously_agreed: state what the original scope says on this point, or write exactly "Not covered in the original scope."
5. NEVER invent prices, amounts, percentages, dates, deadlines, quantities, account names, rules or business logic. If the work needs a fact the sources do not state, ask a question instead. Do not suggest likely answers.
6. Questions: specific, one fact each, answerable by the client. blocking = true if the change cannot be built without the answer. If nothing is missing, return an empty list.
7. Requests are listed in the order received. Treat a later message as overriding an earlier one only when the client clearly says so; still report it as a contradiction so a person confirms it.
8. Ignore greetings and small talk. Do not list unchanged items. Do not repeat items listed under ALREADY DECIDED.
9. One item per distinct change. Do not merge unrelated requests."""

BASELINE_SYSTEM = """Turn the ORIGINAL AGREED SCOPE into a short task checklist for the build team.
One task per concrete deliverable that the scope explicitly commits to. Skip anything listed as out of scope, assumptions and commercials.
Each task cites the chunk ID it comes from and quotes the supporting words verbatim. Do not add tasks the scope does not state."""

CHECKLIST_SYSTEM = """You update a build checklist after a person approved one scope change.
Use only the approved change, its evidence and the answers the person gave. Do not add details beyond them.
Return the smallest set of operations:
- add: a new task the change requires (task_id = "").
- update: rewrite an existing task the change alters (use its task_id).
- remove: an existing task the change cancels (use its task_id, title = "").
If an answer says something is still unknown, add a task to confirm it rather than guessing."""


def _fmt(chunks: list[dict]) -> str:
    return "\n\n".join(f"[{c['id']}] ({c['label']})\n{c['text']}" for c in chunks)


def baseline_tasks(base_chunks: list[dict]) -> list[dict]:
    if gemini.MOCK:
        return mock.baseline(base_chunks)
    prompt = f"ORIGINAL AGREED SCOPE:\n\n{_fmt(base_chunks)}"
    out = gemini.generate([prompt], BaselineOut, BASELINE_SYSTEM)
    return [t.model_dump(mode="json") for t in out.tasks]


def find_changes(base_chunks: list[dict], req_chunks: list[dict], decided: list[dict]) -> list[dict]:
    if gemini.MOCK:
        return mock.analysis(base_chunks, req_chunks)
    decided_txt = "\n".join(f"- {d['title']} ({d['status']})" for d in decided) or "None"
    prompt = (f"ORIGINAL AGREED SCOPE:\n\n{_fmt(base_chunks)}\n\n"
              f"NEW REQUESTS (in order received):\n\n{_fmt(req_chunks)}\n\n"
              f"ALREADY DECIDED:\n{decided_txt}")
    out = gemini.generate([prompt], AnalysisOut, ANALYSIS_SYSTEM)
    return [i.model_dump(mode="json") for i in out.items]


def checklist_ops(tasks: list[dict], change: dict, answers: dict) -> list[dict]:
    if gemini.MOCK:
        return mock.ops(tasks, change, answers)
    active = [t for t in tasks if t["status"] != "removed"]
    task_txt = "\n".join(f"{t['id']}: {t['title']}" for t in active)
    qa = "\n".join(f"Q: {q['question']}\nA: {answers.get(q['id'], '(not answered)')}"
                   for q in change.get("questions", [])) or "No questions."
    ev = "\n".join(f"{e['role']} [{e['source_id']}]: \"{e['quote']}\"" for e in change["evidence"])
    prompt = (f"CURRENT CHECKLIST:\n{task_txt}\n\nAPPROVED CHANGE ({change['type']}): {change['title']}\n"
              f"Previously agreed: {change['previously_agreed']}\nNew request: {change['new_request']}\n"
              f"Evidence:\n{ev}\n\nANSWERS:\n{qa}")
    out = gemini.generate([prompt], ChecklistOpsOut, CHECKLIST_SYSTEM)
    return [o.model_dump(mode="json") for o in out.ops]
