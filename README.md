# ScopeClear

Turns scattered client requests into clear, approved work.

A client shares a proposal, then sends voice notes, screenshots and chats that change it. ScopeClear compares everything against the agreed scope. It shows what changed, quotes the exact page or message each finding comes from, asks about anything missing instead of guessing, and updates the build checklist only after a person approves. Every decision is kept in an append-only history.

Theme: Future of Work & Enterprise Productivity. All demo data is fictional.

## The flow

1. Upload the original proposal (agreed scope) and new requests (PDF, voice notes, screenshots, pasted chats).
2. Gemini finds additions, changes, contradictions and missing details, each citing a reference such as `D1-P2` (document 1, page 2) or `V1-05` (voice note 1, segment 5).
3. Each change is shown as **Previously agreed → New request**.
4. Questions are generated where information is missing. Questions marked "needed before approval" block the Approve button.
5. A named person approves or rejects. Approval updates the checklist to a new version and writes the decision, answers and evidence to the history.

## What makes the output trustworthy

Gemini's output is checked by plain code before anyone sees it (`app/verify.py`):

- Every quote must exist in the chunk it cites, as an exact match or at least a 90% close match.
- A quote marked "agreed" must come from the original scope, not a new request.
- Any number in the AI's summary (amount, percentage, count or date) that is missing from the cited evidence is flagged.
- If evidence is not verified, approval needs a written note.
- The checklist changes only through approved changes, and every version is kept.

`tests/test_verify.py` proves these checks catch invented quotes, wrong sources and invented numbers.

## Stack

- **Gemini** (through Vertex AI): reads PDFs, transcribes voice notes, reads screenshots, finds changes and proposes checklist updates. All output uses strict JSON schemas.
- **Cloud Run**: hosts the single service (FastAPI backend and one HTML page).
- **Firestore**: stores project state, the `history` subcollection (approval log) and the `versions` subcollection (every checklist version).

No API keys are used in production. Cloud Run calls Gemini with its service account.

## Run locally

```bash
pip install -r requirements.txt
gcloud auth application-default login          # or set GEMINI_API_KEY in .env
cp .env.example .env                            # edit values
set -a; source .env; set +a
STORE=memory uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080 and choose **Load the demo case**.

`MOCK_GEMINI=1` runs the flow with a scripted AI step for UI work. The page shows a yellow banner in this mode. Never deploy with it.

## Deploy to Cloud Run

```bash
PROJECT=your-gcp-project-id ./deploy.sh
```

This enables the APIs, creates Firestore, creates a service account with only `aiplatform.user` and `datastore.user`, and deploys. It uses `--min-instances 1` so judges never hit a cold start. Check billing for that setting.

If your Gemini model is not available in `us-central1`, set `GEMINI_LOCATION`. Set `GEMINI_MODEL` to the model you tested with.

## Access for judges

- Live app: `https://<your-cloud-run-url>` (fill in after deploy)
- No login. Choose **Load the demo case**, then **Find changes**.
- Type a name in "Deciding as" to approve or reject.
- Demo files are in `demo/inputs/` if you want to upload them yourself.

## Measure before you report

```bash
GOOGLE_CLOUD_PROJECT=your-project STORE=memory python -m eval.run_eval --runs 3
```

This runs the real model on the demo case and scores it against `eval/ground_truth.json`, which lists 7 planted changes. It reports detection, type accuracy, questions asked where information is missing, and quotes verified. Results are saved to `eval/results.json`. Report only these numbers. A mock-mode run proves only that the script works.

Add more cases (vague requests, unchanged items, Hinglish voice notes) to `ground_truth.json` before quoting results.

## Demo case (fictional)

| Source | Planted change |
|---|---|
| WhatsApp chat, 12 Oct | WhatsApp reminders (contradicts "out of scope"), Excel report, 3 users instead of 5 |
| Voice note 1, 13 Oct | Partial payments across cash and UPI into a second account (balance rule missing) |
| Voice note 2, 14 Oct | Withdraws the Excel request; discounts with no customers or amounts given |
| Screenshot, 15 Oct | Customer GSTIN and "Delivered by" on the invoice |

The voice notes in `demo/inputs` are synthetic speech. Re-record them in a real voice, ideally in Hinglish, from the scripts in `demo/scripts/`, and keep the same file names. `demo/make_demo.py` rebuilds the PDF, chat and screenshot.

## Layout

```
app/main.py       API and the approval gate
app/ingest.py     sources -> citable chunks
app/analyze.py    prompts for the three AI steps
app/verify.py     quote and number checks (no AI)
app/store.py      Firestore / in-memory
app/schemas.py    JSON schemas Gemini must follow
app/mock.py       scripted AI for local UI work
static/index.html the whole frontend
eval/             measured evaluation
tests/            safeguard tests
```

## Not in this version

Live WhatsApp integration, automatic pricing, user accounts and multiple projects per user.
