#!/usr/bin/env bash
# One-time GCP bootstrap for the GitHub Actions CI/CD pipeline. Safe to re-run.
#
# Creates:
#   - Artifact Registry Docker repo for images
#   - simpleagent-runtime SA   (Cloud Run identity: calls Vertex AI)
#   - github-ci SA             (CI eval job: calls Vertex AI)
#   - github-deployer SA       (CD job: pushes images, deploys Cloud Run; main branch only)
#   - Workload Identity Federation pool/provider so GitHub needs no JSON keys
#
# Usage:
#   PROJECT_ID=my-project REGION=us-central1 ./scripts/setup_gcp.sh [--apply-gh]
#   --apply-gh  also writes the repository variables with the gh CLI
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
GITHUB_REPO="${GITHUB_REPO:-$(git remote get-url origin | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')}"
SERVICE="${SERVICE:-simpleagent}"
AR_REPO="${AR_REPO:-simpleagent}"
POOL="${POOL:-github}"
PROVIDER="${PROVIDER:-github-oidc}"

[[ -n "$PROJECT_ID" ]] || { echo "Set PROJECT_ID" >&2; exit 1; }
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="simpleagent-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
CI_SA="github-ci@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}"

echo "Project: $PROJECT_ID ($PROJECT_NUMBER)  Region: $REGION  GitHub repo: $GITHUB_REPO"

echo "==> Enabling APIs"
gcloud services enable --project "$PROJECT_ID" \
  run.googleapis.com artifactregistry.googleapis.com aiplatform.googleapis.com \
  iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  cloudresourcemanager.googleapis.com cloudtrace.googleapis.com

echo "==> Artifact Registry repo"
gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$AR_REPO" --repository-format docker \
    --location "$REGION" --project "$PROJECT_ID" --description "simpleagent images"

echo "==> Service accounts"
for sa in simpleagent-runtime github-ci github-deployer; do
  gcloud iam service-accounts describe "${sa}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project "$PROJECT_ID" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$sa" --project "$PROJECT_ID" --display-name "$sa"
done

bind_project() {
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:$1" \
    --role "$2" --condition None --quiet >/dev/null
}

echo "==> IAM roles"
bind_project "$RUNTIME_SA" roles/aiplatform.user
bind_project "$RUNTIME_SA" roles/logging.logWriter
bind_project "$RUNTIME_SA" roles/cloudtrace.agent
bind_project "$CI_SA" roles/aiplatform.user
bind_project "$DEPLOY_SA" roles/run.admin
gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" --location "$REGION" \
  --project "$PROJECT_ID" --member "serviceAccount:$DEPLOY_SA" \
  --role roles/artifactregistry.writer --quiet >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT_ID" \
  --member "serviceAccount:$DEPLOY_SA" --role roles/iam.serviceAccountUser --quiet >/dev/null

echo "==> Workload Identity Federation"
gcloud iam workload-identity-pools describe "$POOL" --location global --project "$PROJECT_ID" >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create "$POOL" --location global --project "$PROJECT_ID" \
    --display-name "GitHub Actions"
gcloud iam workload-identity-pools providers describe "$PROVIDER" --workload-identity-pool "$POOL" \
  --location global --project "$PROJECT_ID" >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --workload-identity-pool "$POOL" --location global --project "$PROJECT_ID" \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository == '${GITHUB_REPO}'"

# Any workflow run in this repo may use the CI SA; only runs on main may deploy.
gcloud iam service-accounts add-iam-policy-binding "$CI_SA" --project "$PROJECT_ID" \
  --role roles/iam.workloadIdentityUser --quiet \
  --member "principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_REPO}" >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" --project "$PROJECT_ID" \
  --role roles/iam.workloadIdentityUser --quiet \
  --member "principalSet://iam.googleapis.com/${POOL_ID}/attribute.ref/refs/heads/main" >/dev/null

WIF_PROVIDER="${POOL_ID}/providers/${PROVIDER}"
declare -a VARS=(
  "GCP_PROJECT_ID=$PROJECT_ID"
  "GCP_REGION=$REGION"
  "GCP_WIF_PROVIDER=$WIF_PROVIDER"
  "GCP_CI_SA=$CI_SA"
  "GCP_DEPLOY_SA=$DEPLOY_SA"
  "GCP_RUNTIME_SA=$RUNTIME_SA"
  "GCP_AR_REPO=$AR_REPO"
  "CLOUD_RUN_SERVICE=$SERVICE"
)

echo
echo "==> GitHub repository variables (Settings → Secrets and variables → Actions → Variables)"
for kv in "${VARS[@]}"; do
  if [[ "${1:-}" == "--apply-gh" ]]; then
    gh variable set "${kv%%=*}" --repo "$GITHUB_REPO" --body "${kv#*=}"
  else
    echo "gh variable set ${kv%%=*} --repo $GITHUB_REPO --body '${kv#*=}'"
  fi
done
echo "Done."
