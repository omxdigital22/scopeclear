"""Turn every upload into small, citable chunks with stable IDs.

Chunk IDs are what makes citations checkable:
  D1-P2  -> document 1, page 2
  V1-03  -> voice note 1, segment 3 (label shows the timestamp)
  I1-02  -> image 1, item 2
  T1-05  -> text message 1, line 5
"""
import io
from pathlib import Path

from pypdf import PdfReader

from . import gemini, mock
from .schemas import ImageOut, PdfPagesOut, TranscriptOut

PREFIX = {"pdf": "D", "audio": "V", "image": "I", "text": "T"}

AUDIO_EXT = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
             ".opus": "audio/ogg", ".aac": "audio/aac", ".webm": "audio/webm", ".flac": "audio/flac"}
IMAGE_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

TRANSCRIBE_SYSTEM = (
    "You transcribe client voice notes for a software team. Transcribe verbatim in the "
    "original language (Hindi, English or Hinglish as spoken; write Hindi words in Latin script). "
    "Split into segments of one or two sentences, each with its start time as m:ss. "
    "Do not summarise, correct, translate or add anything. Mark unclear words as [unclear]."
)
IMAGE_SYSTEM = (
    "You read screenshots a client sent to a software team. Copy every visible line of text "
    "verbatim, one item per line or bullet, in reading order. If the image shows a visual request "
    "with no text (for example a circled area), add one item in square brackets describing only "
    "what is visibly marked. Do not interpret, infer or add anything not visible."
)
PDF_OCR_SYSTEM = "Transcribe the text of every page of this PDF verbatim. Do not summarise."


def detect_kind(filename: str, content_type: str | None) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return "pdf", "application/pdf"
    if ext in AUDIO_EXT:
        return "audio", AUDIO_EXT[ext]
    if ext in IMAGE_EXT:
        return "image", IMAGE_EXT[ext]
    if ext in (".txt", ".md"):
        return "text", "text/plain"
    if content_type:
        if content_type.startswith("audio/"):
            return "audio", content_type
        if content_type.startswith("image/"):
            return "image", content_type
    raise ValueError(f"Unsupported file type: {filename}. Use PDF, audio, image or .txt.")


def _chunk(cid: str, label: str, text: str) -> dict:
    return {"id": cid, "label": label, "text": text.strip()}


def ingest_pdf(data: bytes, short: str, name: str) -> list[dict]:
    reader = PdfReader(io.BytesIO(data))
    chunks = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            chunks.append(_chunk(f"{short}-P{i}", f"{name}, page {i}", text))
    if chunks:
        return chunks
    # Scanned PDF with no text layer: let Gemini read it page by page.
    if gemini.MOCK:
        raise ValueError("Scanned PDFs need Gemini; mock mode can only read text PDFs.")
    out = gemini.generate([gemini.part_bytes(data, "application/pdf"), "Transcribe each page."],
                          PdfPagesOut, PDF_OCR_SYSTEM)
    return [_chunk(f"{short}-P{p.page}", f"{name}, page {p.page}", p.text) for p in out.pages if p.text.strip()]


def ingest_audio(data: bytes, mime: str, short: str, name: str) -> list[dict]:
    if gemini.MOCK:
        lines = mock.script_for(name)
        segs = [(f"0:{i * 6:02d}", t) for i, t in enumerate(lines)]
    else:
        out = gemini.generate([gemini.part_bytes(data, mime), "Transcribe this voice note."],
                              TranscriptOut, TRANSCRIBE_SYSTEM, temperature=0.0)
        segs = [(s.start, s.text) for s in out.segments]
    return [_chunk(f"{short}-{n:02d}", f"{name} at {start}", text)
            for n, (start, text) in enumerate(segs, start=1) if text.strip()]


def ingest_image(data: bytes, mime: str, short: str, name: str) -> list[dict]:
    if gemini.MOCK:
        items = mock.script_for(name)
    else:
        out = gemini.generate([gemini.part_bytes(data, mime), "Read this screenshot."],
                              ImageOut, IMAGE_SYSTEM, temperature=0.0)
        items = [i.text for i in out.items]
    return [_chunk(f"{short}-{n:02d}", f"{name}, item {n}", t)
            for n, t in enumerate(items, start=1) if t.strip()]


def ingest_text(text: str, short: str, name: str) -> list[dict]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return [_chunk(f"{short}-{n:02d}", f"{name}, line {n}", ln) for n, ln in enumerate(lines, start=1)]


def ingest(kind: str, data: bytes, mime: str, short: str, name: str) -> list[dict]:
    if kind == "pdf":
        return ingest_pdf(data, short, name)
    if kind == "audio":
        return ingest_audio(data, mime, short, name)
    if kind == "image":
        return ingest_image(data, mime, short, name)
    return ingest_text(data.decode("utf-8", errors="replace"), short, name)
