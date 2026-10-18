"""Run: python -m pytest tests -q   (no Gemini, no network)"""
from app import verify

CHUNKS = {
    "D1-P2": {"id": "D1-P2", "label": "Proposal, page 2", "text": "- Record customer payments in cash only.\n- All payments are recorded in a single collections account."},
    "V1-05": {"id": "V1-05", "label": "Voice note 1 at 0:24", "text": "So the system should handle partial payments across multiple accounts."},
}
BASE = {"D1-P2"}


def item(**kw):
    base = {"type": "modification", "title": "Partial payments", "previously_agreed": "Cash only.",
            "new_request": "Partial payments across accounts.",
            "evidence": [{"role": "requested", "source_id": "V1-05", "quote": "handle partial payments across multiple accounts"},
                         {"role": "agreed", "source_id": "D1-P2", "quote": "Record customer payments in cash only."}],
            "questions": []}
    base.update(kw)
    return base


def test_real_quotes_pass():
    assert verify.verify_item(item(), CHUNKS, BASE)["verified"]


def test_invented_quote_is_caught():
    it = item(evidence=[{"role": "requested", "source_id": "V1-05", "quote": "customers will pay in three instalments"}])
    out = verify.verify_item(it, CHUNKS, BASE)
    assert not out["verified"] and not out["evidence"][0]["verified"]


def test_wrong_source_id_is_caught():
    it = item(evidence=[{"role": "requested", "source_id": "V9-99", "quote": "partial payments"}])
    assert not verify.verify_item(it, CHUNKS, BASE)["verified"]


def test_agreed_quote_from_request_is_caught():
    it = item(evidence=[{"role": "agreed", "source_id": "V1-05", "quote": "handle partial payments across multiple accounts"},
                        {"role": "requested", "source_id": "V1-05", "quote": "handle partial payments across multiple accounts"}])
    assert not verify.verify_item(it, CHUNKS, BASE)["verified"]


def test_invented_number_is_flagged():
    it = item(new_request="Allow partial payments with a 2% late fee across 3 accounts.")
    out = verify.verify_item(it, CHUNKS, BASE)
    assert not out["verified"]
    assert any("2%" in i for i in out["issues"]) and any("3" in i for i in out["issues"])


def test_small_transcription_differences_still_match():
    assert verify.quote_match("So the system should handle partial payment across multiple accounts", CHUNKS["V1-05"]["text"]) >= 0.9
