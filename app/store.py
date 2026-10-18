"""Storage. Firestore in production; in-memory for local development.

Layout in Firestore:
  scopeclear_projects/{project_id}                 -> sources, changes, checklist (current state)
  scopeclear_projects/{project_id}/history/{auto}  -> append-only approval log
  scopeclear_projects/{project_id}/versions/{n}    -> every checklist version, never overwritten
"""
import os
import uuid
from datetime import datetime, timezone

COLLECTION = os.getenv("FIRESTORE_COLLECTION", "scopeclear_projects")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MemoryStore:
    kind = "memory"

    def __init__(self):
        self.docs, self.history, self.versions = {}, {}, {}

    def create(self, doc: dict) -> str:
        pid = uuid.uuid4().hex[:10]
        self.docs[pid] = {**doc, "id": pid}
        self.history[pid], self.versions[pid] = [], {}
        return pid

    def get(self, pid: str) -> dict | None:
        return self.docs.get(pid)

    def save(self, pid: str, doc: dict):
        self.docs[pid] = doc

    def log(self, pid: str, event: dict):
        self.history[pid].append({**event, "at": now()})

    def events(self, pid: str) -> list[dict]:
        return list(self.history.get(pid, []))

    def save_version(self, pid: str, n: int, data: dict):
        self.versions[pid][str(n)] = data

    def get_versions(self, pid: str) -> list[dict]:
        return [self.versions[pid][k] for k in sorted(self.versions.get(pid, {}), key=int)]


class FirestoreStore:
    kind = "firestore"

    def __init__(self):
        from google.cloud import firestore
        self.db = firestore.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT") or None,
                                   database=os.getenv("FIRESTORE_DATABASE", "(default)"))

    def _ref(self, pid):
        return self.db.collection(COLLECTION).document(pid)

    def create(self, doc: dict) -> str:
        ref = self.db.collection(COLLECTION).document()
        ref.set({**doc, "id": ref.id})
        return ref.id

    def get(self, pid: str) -> dict | None:
        snap = self._ref(pid).get()
        return snap.to_dict() if snap.exists else None

    def save(self, pid: str, doc: dict):
        self._ref(pid).set(doc)

    def log(self, pid: str, event: dict):
        self._ref(pid).collection("history").add({**event, "at": now()})

    def events(self, pid: str) -> list[dict]:
        snaps = self._ref(pid).collection("history").order_by("seq").stream()
        return [s.to_dict() for s in snaps]

    def save_version(self, pid: str, n: int, data: dict):
        self._ref(pid).collection("versions").document(str(n)).set(data)

    def get_versions(self, pid: str) -> list[dict]:
        snaps = self._ref(pid).collection("versions").stream()
        return sorted((s.to_dict() for s in snaps), key=lambda v: v["version"])


def get_store():
    if os.getenv("STORE", "firestore") == "memory":
        return MemoryStore()
    return FirestoreStore()
