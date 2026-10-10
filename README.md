# simpleagent

A question-answering agent built with [Google ADK](https://google.github.io/adk-docs/) on
Gemini 2.5 Flash (Vertex AI), served as a FastAPI app on **Cloud Run**, with a GitHub
Actions pipeline that lints, tests, **evaluates** the agent and deploys it.

## Layout

```
.
├── agents/simpleagent/        # ADK agent package (one folder per agent)
│   ├── agent.py               #   root_agent definition
│   ├── prompts.py             #   description + instruction text
│   ├── config.py              #   env-driven settings (AGENT_MODEL)
│   └── .env                   #   local-only Vertex AI settings (git-ignored)
├── app/main.py                # HTTP entrypoint (ADK FastAPI server) used by Cloud Run
├── tests/
│   ├── unit/                  # offline tests: agent config + HTTP server
│   └── eval/                  # ADK eval set + metric thresholds (LLM-judged)
├── scripts/
│   ├── eval_report.py         # builds reports/evaluation_report.md + CI quality gate
│   ├── smoke_test.py          # post-deploy end-to-end check
│   └── setup_gcp.sh           # one-time GCP + Workload Identity Federation bootstrap
├── reports/                   # latest evaluation report (CI uploads one per run)
├── docs/EVALUATION.md         # evaluation methodology, findings and recommendations
├── .github/workflows/ci-cd.yml
├── Dockerfile
├── Makefile
└── requirements.txt / requirements-dev.txt / pyproject.toml
```

## Local development

```bash
make install                         # .venv with ADK (+eval extras), pytest, ruff
cp .env.example agents/simpleagent/.env   # set GOOGLE_CLOUD_PROJECT
gcloud auth application-default login

make lint test                       # offline checks
make eval                            # LLM evaluation → reports/evaluation_report.md
make run                             # API server on :8080
adk web agents                       # ADK dev UI
make docker-build docker-run smoke   # build image, run it, smoke-test it
```

## CI/CD pipeline

`.github/workflows/ci-cd.yml`:

| Job | Runs on | What it does |
|---|---|---|
| **Lint & unit tests** | every PR and push | `ruff check`, `ruff format --check`, `pytest` |
| **Agent evaluation** | PRs from this repo, pushes | `adk eval` against Vertex AI; fails if < 90 % of cases pass; uploads the report as an artifact and to the job summary |
| **Deploy to Cloud Run** | push to `main` after eval passes | builds the image, pushes to Artifact Registry (tagged with the commit SHA), deploys a private Cloud Run service, runs `smoke_test.py` with an identity token |

Authentication uses **Workload Identity Federation** — no service-account keys are
stored in GitHub. Only runs on `refs/heads/main` can impersonate the deployer account.

### One-time setup

```bash
PROJECT_ID=<your-project> REGION=us-central1 ./scripts/setup_gcp.sh --apply-gh
```

This enables the APIs, creates the Artifact Registry repo, three service accounts
(`simpleagent-runtime`, `github-ci`, `github-deployer`) with least-privilege roles, the
WIF pool/provider restricted to this repository, and sets these GitHub repository
variables: `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WIF_PROVIDER`, `GCP_CI_SA`,
`GCP_DEPLOY_SA`, `GCP_RUNTIME_SA`, `GCP_AR_REPO`, `CLOUD_RUN_SERVICE`. Drop
`--apply-gh` to print the `gh variable set` commands instead.

Optionally add required reviewers to the `production` environment in GitHub
(Settings → Environments) to require approval before each deploy.

### Calling the deployed service

The service is private (`--no-allow-unauthenticated`), so a plain browser visit returns
403. Callers need `roles/run.invoker`. To use the ADK chat UI in a browser, open a local
authenticated proxy and visit http://localhost:8080:

```bash
gcloud run services proxy simpleagent --region us-central1 --port 8080
```

From scripts, send an identity token:

```bash
URL=$(gcloud run services describe simpleagent --region us-central1 --format 'value(status.url)')
ID_TOKEN=$(gcloud auth print-identity-token) python scripts/smoke_test.py "$URL"
```

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | — | `TRUE` to use Vertex AI |
| `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` | — | Vertex AI project / region |
| `AGENT_MODEL` | `gemini-2.5-flash` | Model used by the agent |
| `SESSION_SERVICE_URI` | in-memory | Persistent session store (e.g. Cloud SQL, Agent Engine) |
| `ALLOW_ORIGINS` | none | Comma-separated CORS origins |
| `SERVE_WEB_UI` | `false` | Serve the ADK dev UI from the container |
| `TRACE_TO_CLOUD` | `false` | Export traces to Cloud Trace |
| `EVAL_MIN_PASS_RATE` | `0.9` | Evaluation quality-gate threshold |
