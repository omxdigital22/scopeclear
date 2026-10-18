"""ScopeClear API. One flow:
upload -> analyse (cited) -> compare -> questions -> human approval -> checklist + history.
"""
import copy
import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analyze, gemini, ingest, verify
from .store import get_store, now

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo" / "inputs"
MAX_BYTES = 25 * 1024 * 1024  # Cloud Run caps requests at 32 MB

app = FastAPI(title="ScopeClear")
store = get_store()


# ---------------- helpers ----------------
def _load(pid: str) -> dict:
    doc = store.get(pid)
    if not doc:
        raise HTTPException(404, "Project not found. Start a new one or load the demo case.")
    return doc


def _log(pid: str, doc: dict, event: dict):
    doc["seq"] = doc.get("seq", 0) + 1
    store.log(pid, {**event, "seq": doc["seq"]})


def _state(pid: str) -> dict:
    doc = _load(pid)
    return {**doc, "history": store.events(pid), "versions": store.get_versions(pid)}


def _all_chunks(doc: dict, role: str | None = None) -> list[dict]:
    return [c for s in doc["sources"] if role is None or s["role"] == role for c in s["chunks"]]


def _snapshot(pid: str, doc: dict, reason: str, change_id: str | None):
    doc["checklist_version"] = doc.get("checklist_version", 0) + 1
    store.save_version(pid, doc["checklist_version"], {
        "version": doc["checklist_version"], "at": now(), "reason": reason,
        "change_id": change_id, "tasks": copy.deepcopy(doc["checklist"])})


def _new_project(name: str, is_demo: bool = False) -> str:
    return store.create({
        "name": name.strip() or "Untitled project", "created_at": now(), "is_demo": is_demo,
        "sources": [], "counters": {}, "changes": [], "change_seq": 0,
        "checklist": [], "checklist_version": 0, "task_seq": 0, "seq": 0, "last_analysis": None})


def _add_source(pid: str, doc: dict, role: str, name: str, kind: str, data: bytes, mime: str):
    if role not in ("baseline", "request"):
        raise HTTPException(400, "Role must be 'baseline' or 'request'.")
    prefix = ingest.PREFIX[kind]
    n = doc["counters"].get(prefix, 0) + 1
    short = f"{prefix}{n}"
    try:
        chunks = ingest.ingest(kind, data, mime, short, name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, f"Could not read {name}: {e}")
    if not chunks:
        raise HTTPException(400, f"No readable content found in {name}.")
    doc["counters"][prefix] = n
    doc["sources"].append({"id": short, "kind": kind, "name": name, "role": role,
                           "added_at": now(), "chunks": chunks})
    _log(pid, doc, {"type": "source_added", "source_id": short, "name": name, "role": role,
                    "chunks": len(chunks)})


# ---------------- routes ----------------
@app.get("/api/health")
def health():
    return {"ok": True, "mock": gemini.MOCK, "model": gemini.MODEL, "store": store.kind}


class NewProject(BaseModel):
    name: str


@app.post("/api/projects")
def create_project(body: NewProject):
    return _state(_new_project(body.name))


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    return _state(pid)


@app.post("/api/projects/{pid}/sources")
async def upload_sources(pid: str, role: str = Form(...), files: list[UploadFile] = File(default=[]),
                         text: str = Form(default=""), text_name: str = Form(default="")):
    doc = _load(pid)
    if not files and not text.strip():
        raise HTTPException(400, "Add a file or paste a message.")
    for f in files:
        data = await f.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(400, f"{f.filename} is over 25 MB.")
        try:
            kind, mime = ingest.detect_kind(f.filename or "file", f.content_type)
        except ValueError as e:
            raise HTTPException(400, str(e))
        _add_source(pid, doc, role, f.filename or "file", kind, data, mime)
    if text.strip():
        _add_source(pid, doc, role, text_name.strip() or "Pasted message", "text",
                    text.encode("utf-8"), "text/plain")
    store.save(pid, doc)
    return _state(pid)


@app.delete("/api/projects/{pid}/sources/{sid}")
def delete_source(pid: str, sid: str):
    doc = _load(pid)
    if any(c["status"] != "pending" for c in doc["changes"]):
        raise HTTPException(400, "Sources are locked once a change has been decided, to keep the record intact.")
    before = len(doc["sources"])
    doc["sources"] = [s for s in doc["sources"] if s["id"] != sid]
    if len(doc["sources"]) == before:
        raise HTTPException(404, "Source not found.")
    _log(pid, doc, {"type": "source_removed", "source_id": sid})
    store.save(pid, doc)
    return _state(pid)


@app.post("/api/projects/{pid}/analyze")
def run_analysis(pid: str):
    doc = _load(pid)
    base, req = _all_chunks(doc, "baseline"), _all_chunks(doc, "request")
    if not base:
        raise HTTPException(400, "Upload the original proposal first.")
    if not req:
        raise HTTPException(400, "Add at least one new request to compare.")
    chunk_map = {c["id"]: c for c in base + req}
    base_ids = {c["id"] for c in base}

    try:
        if not doc["checklist"]:
            tasks = analyze.baseline_tasks(base)
            for t in tasks:
                doc["task_seq"] += 1
                verify.verify_task(t, chunk_map)
                doc["checklist"].append({**t, "id": f"T{doc['task_seq']}", "status": "active",
                                         "origin": "original scope", "changes": []})
            _snapshot(pid, doc, "Checklist created from the original scope", None)
            _log(pid, doc, {"type": "baseline_checklist", "version": doc["checklist_version"],
                            "tasks": len(tasks)})

        decided = [c for c in doc["changes"] if c["status"] != "pending"]
        items = analyze.find_changes(base, req, decided)
    except RuntimeError as e:
        raise HTTPException(502, f"The AI step failed: {e}. Try again.")

    new_changes = []
    for item in items:
        verify.verify_item(item, chunk_map, base_ids)
        doc["change_seq"] += 1
        cid = f"C{doc['change_seq']}"
        for qn, q in enumerate(item["questions"], start=1):
            q["id"] = f"{cid}-Q{qn}"
        new_changes.append({**item, "id": cid, "status": "pending", "decision": None, "found_at": now()})
    doc["changes"] = decided + new_changes

    evid = [e for c in new_changes for e in c["evidence"]]
    doc["last_analysis"] = {
        "at": now(), "model": "mock" if gemini.MOCK else gemini.MODEL,
        "changes": len(new_changes),
        "questions": sum(len(c["questions"]) for c in new_changes),
        "quotes": len(evid), "quotes_verified": sum(1 for e in evid if e.get("verified")),
        "flagged": sum(1 for c in new_changes if not c["verified"]),
    }
    _log(pid, doc, {"type": "analysis_run", **doc["last_analysis"]})
    store.save(pid, doc)
    return _state(pid)


class Decision(BaseModel):
    decision: str            # "approve" | "reject"
    decided_by: str
    answers: dict[str, str] = {}
    note: str = ""


def _apply_ops(doc: dict, ops: list[dict], cid: str) -> list[dict]:
    applied = []
    by_id = {t["id"]: t for t in doc["checklist"]}
    for op in ops:
        kind, tid, title = op["op"], op.get("task_id", ""), op.get("title", "").strip()
        if kind == "add" and title:
            doc["task_seq"] += 1
            t = {"id": f"T{doc['task_seq']}", "title": title, "status": "active", "origin": cid,
                 "source_id": "", "quote": "", "label": f"Approved change {cid}", "verified": True,
                 "changes": [{"change_id": cid, "op": "add", "reason": op["reason"]}]}
            doc["checklist"].append(t)
            applied.append({"op": "add", "task_id": t["id"], "title": title, "reason": op["reason"]})
        elif kind == "update" and tid in by_id and by_id[tid]["status"] != "removed" and title:
            t = by_id[tid]
            t["changes"].append({"change_id": cid, "op": "update", "before": t["title"], "reason": op["reason"]})
            applied.append({"op": "update", "task_id": tid, "before": t["title"], "title": title,
                            "reason": op["reason"]})
            t["title"], t["status"] = title, "updated"
        elif kind == "remove" and tid in by_id and by_id[tid]["status"] != "removed":
            t = by_id[tid]
            t["status"] = "removed"
            t["changes"].append({"change_id": cid, "op": "remove", "reason": op["reason"]})
            applied.append({"op": "remove", "task_id": tid, "title": t["title"], "reason": op["reason"]})
    return applied


@app.post("/api/projects/{pid}/changes/{cid}/decision")
def decide(pid: str, cid: str, body: Decision):
    doc = _load(pid)
    change = next((c for c in doc["changes"] if c["id"] == cid), None)
    if not change:
        raise HTTPException(404, "Change not found.")
    if change["status"] != "pending":
        raise HTTPException(400, f"{cid} was already {change['status']}.")
    if not body.decided_by.strip():
        raise HTTPException(400, "Enter your name so the decision is traceable.")
    answers = {k: v.strip() for k, v in body.answers.items() if v.strip()}

    if body.decision == "reject":
        change["status"] = "rejected"
        change["decision"] = {"by": body.decided_by.strip(), "at": now(), "note": body.note.strip(),
                              "answers": answers}
        _log(pid, doc, {"type": "change_rejected", "change_id": cid, "title": change["title"],
                        "by": body.decided_by.strip(), "note": body.note.strip()})
        store.save(pid, doc)
        return _state(pid)

    if body.decision != "approve":
        raise HTTPException(400, "Decision must be 'approve' or 'reject'.")
    missing = [q["question"] for q in change["questions"] if q["blocking"] and not answers.get(q["id"])]
    if missing:
        raise HTTPException(400, "Answer these before approving: " + " | ".join(missing))
    if not change["verified"] and not body.note.strip():
        raise HTTPException(400, "This change has unverified evidence. Add a note explaining why you are approving it.")

    try:
        ops = analyze.checklist_ops(doc["checklist"], change, answers)
    except RuntimeError as e:
        raise HTTPException(502, f"Could not update the checklist: {e}. Nothing was approved; try again.")

    before_version = doc["checklist_version"]
    applied = _apply_ops(doc, ops, cid)
    change["status"] = "approved"
    change["decision"] = {"by": body.decided_by.strip(), "at": now(), "note": body.note.strip(),
                          "answers": answers, "checklist_ops": applied}
    _snapshot(pid, doc, f"Approved {cid}: {change['title']}", cid)
    _log(pid, doc, {
        "type": "change_approved", "change_id": cid, "title": change["title"],
        "change_type": change["type"], "by": body.decided_by.strip(), "note": body.note.strip(),
        "answers": [{"question": q["question"], "answer": answers.get(q["id"], "")} for q in change["questions"]],
        "evidence": [{"role": e["role"], "label": e["label"], "quote": e["quote"], "verified": e["verified"]}
                     for e in change["evidence"]],
        "checklist_from": before_version, "checklist_to": doc["checklist_version"], "ops": applied})
    store.save(pid, doc)
    return _state(pid)


@app.post("/api/demo")
def load_demo():
    manifest = json.loads((DEMO_DIR / "manifest.json").read_text())
    pid = _new_project("Kestrel Hardware billing system (fictional demo)", is_demo=True)
    doc = store.get(pid)
    for entry in manifest:
        path = DEMO_DIR / entry["file"]
        if not path.exists():
            continue
        kind, mime = ingest.detect_kind(path.name, None)
        _add_source(pid, doc, entry["role"], entry["name"], kind, path.read_bytes(), mime)
    store.save(pid, doc)
    return _state(pid)


# ---------------- frontend ----------------
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")
