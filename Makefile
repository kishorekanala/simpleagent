.PHONY: install lint format test eval report run docker-build docker-run smoke setup-gcp

PY ?= .venv/bin/python
AGENT_DIR := agents/simpleagent
EVALSET := tests/eval/simpleagent_core.evalset.json
EVAL_CONFIG := tests/eval/test_config.json
EVAL_HISTORY := $(AGENT_DIR)/.adk/eval_history
IMAGE ?= simpleagent:local

install:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -r requirements-dev.txt

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

test:
	$(PY) -m pytest

# Runs the LLM evaluation against Vertex AI (needs GCP credentials), then
# writes reports/evaluation_report.md and fails if the pass rate is too low.
eval:
	rm -rf $(EVAL_HISTORY)
	$(PY) -m google.adk.cli eval $(AGENT_DIR) $(EVALSET) --config_file_path $(EVAL_CONFIG)
	$(MAKE) report

report:
	$(PY) scripts/eval_report.py --history-dir $(EVAL_HISTORY) --evalset $(EVALSET) \
		--config $(EVAL_CONFIG) --out-dir reports

run:
	$(PY) -m app.main

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm -p 8080:8080 --env-file $(AGENT_DIR)/.env \
		-v $$HOME/.config/gcloud:/home/appuser/.config/gcloud:ro $(IMAGE)

smoke:
	$(PY) scripts/smoke_test.py $${URL:-http://localhost:8080}

setup-gcp:
	./scripts/setup_gcp.sh
