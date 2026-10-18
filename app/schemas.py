"""Schemas Gemini must return. No defaults on purpose: some Gemini schema
converters reject default values, and we want every field filled explicitly."""
from enum import Enum
from pydantic import BaseModel, Field


# ---------- Ingestion ----------
class TranscriptSegment(BaseModel):
    start: str = Field(description="Start time of the segment as m:ss, e.g. 0:07")
    text: str = Field(description="Verbatim words spoken, in the original language")


class TranscriptOut(BaseModel):
    segments: list[TranscriptSegment]


class ImageItem(BaseModel):
    text: str = Field(description="One visible line or request, copied verbatim")


class ImageOut(BaseModel):
    items: list[ImageItem]


class PdfPage(BaseModel):
    page: int
    text: str


class PdfPagesOut(BaseModel):
    pages: list[PdfPage]


# ---------- Analysis ----------
class ChangeType(str, Enum):
    addition = "addition"            # not in the original scope at all
    modification = "modification"    # changes something already agreed
    contradiction = "contradiction"  # conflicts with agreed scope or with another request
    unclear = "unclear"              # too vague to act on


class EvidenceRole(str, Enum):
    agreed = "agreed"            # from the original proposal
    requested = "requested"      # the new request
    conflicting = "conflicting"  # an earlier/other statement it clashes with


class Evidence(BaseModel):
    role: EvidenceRole
    source_id: str = Field(description="Chunk ID exactly as given, e.g. D1-P2 or V1-03")
    quote: str = Field(description="Words copied verbatim from that chunk. Never paraphrase.")


class Question(BaseModel):
    question: str = Field(description="One specific question the client can answer")
    why_needed: str = Field(description="What cannot be built correctly without the answer")
    blocking: bool = Field(description="True if work on this change cannot start without it")


class ChangeItem(BaseModel):
    type: ChangeType
    title: str = Field(description="Short title, max 8 words")
    previously_agreed: str = Field(
        description="What the original scope says, or exactly 'Not covered in the original scope.'")
    new_request: str = Field(description="What the client now asks for, in plain words")
    evidence: list[Evidence]
    questions: list[Question]


class AnalysisOut(BaseModel):
    items: list[ChangeItem]


# ---------- Checklist ----------
class BaselineTask(BaseModel):
    title: str = Field(description="One buildable task, imperative, max 12 words")
    source_id: str
    quote: str = Field(description="Verbatim words from the source that this task comes from")


class BaselineOut(BaseModel):
    tasks: list[BaselineTask]


class TaskOpType(str, Enum):
    add = "add"
    update = "update"
    remove = "remove"


class TaskOp(BaseModel):
    op: TaskOpType
    task_id: str = Field(description="Existing task ID for update/remove; empty string for add")
    title: str = Field(description="New or updated task title; empty string for remove")
    reason: str = Field(description="Why, referring only to the approved change and answers")


class ChecklistOpsOut(BaseModel):
    ops: list[TaskOp]
