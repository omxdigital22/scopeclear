#!/usr/bin/env bash
# One-time setup + deploy to Cloud Run. Run from the project folder.
set -euo pipefail
PROJECT="${PROJECT:?set PROJECT=your-gcp-project-id}"
REGION="${REGION:-asia-south1}"
SA="scopeclear-run@${PROJECT}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com aiplatform.googleapis.com firestore.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
gcloud firestore databases describe --database="(default)" >/dev/null 2>&1 || gcloud firestore databases create --location="$REGION"
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || gcloud iam service-accounts create scopeclear-run --display-name="ScopeClear Cloud Run"
for ROLE in roles/aiplatform.user roles/datastore.user; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA" --role="$ROLE" --condition=None >/dev/null
done

gcloud run deploy scopeclear --source . --region "$REGION" --service-account "$SA" \
  --allow-unauthenticated --memory 1Gi --timeout 300 --min-instances 1 --max-instances 3 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=${GEMINI_LOCATION:-us-central1},GEMINI_MODEL=${GEMINI_MODEL:-gemini-2.5-flash}"
