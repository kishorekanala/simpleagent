# simpleagent — Evaluation Report

**Date:** 2026-10-10 · **Agent:** `root_agent` on `gemini-2.5-flash` (Vertex AI) · **ADK:** 1.28.0
**Verdict:** ✅ Passes the quality gate (10/10 cases, two independent runs). The agent is
fit for a low-risk general Q&A deployment. Before it serves real users, it needs a
persistent session store, and the eval set should be made harder.

The full per-case scores and transcripts of the latest run are in
[`reports/evaluation_report.md`](../reports/evaluation_report.md). CI regenerates that
file on every run and uploads it as the `evaluation-report-<sha>` artifact.

## 1. What was evaluated

| Area | Eval case(s) | What a pass means |
|---|---|---|
| Factual recall | `factual_capital` | Correct fact (Canberra, a common trap) |
| Reasoning | `arithmetic`, `unit_conversion` | Correct numeric answer |
| Explanation | `concept_explanation` | Accurate, within the requested length |
| Format following | `format_constraint` | Single-word answer when asked |
| Code | `code_snippet` | Correct idiom (`s[::-1]`) |
| Honesty | `false_premise`, `unknowable_future` | Corrects false premise; refuses to fabricate a prediction |
| Conversation memory | `multi_turn_memory` | Recalls a detail from an earlier turn |
| Safety | `unsafe_request_refusal` | Refuses a weapons request |

### Metrics and thresholds (`tests/eval/test_config.json`)

| Metric | Type | Threshold | Purpose |
|---|---|---|---|
| `tool_trajectory_avg_score` | deterministic | 1.0 | Agent makes no unexpected tool calls |
| `final_response_match_v2` | LLM judge (3 samples) | 0.8 | Answer is semantically equivalent to the reference |
| `rubric_based_final_response_quality_v1` | LLM judge (3 samples) | 0.8 | Relevance, honesty, instruction following, safety |

**Gate:** each case must meet every threshold, and at least **90 %** of cases must pass
(`EVAL_MIN_PASS_RATE`). The gate tolerates one failing case so that a single noisy
judge sample cannot block a deploy, while a real regression still fails CI.

## 2. Results

| Metric | Run 1 | Run 2 |
|---|---|---|
| Cases passed | 10 / 10 | 10 / 10 |
| `tool_trajectory_avg_score` | 1.00 | 1.00 |
| `final_response_match_v2` | 1.00 | 1.00 |
| `rubric_based_final_response_quality_v1` | 0.99 | 0.99 |
| ↳ relevance / honesty / instruction following / safety | 1.00 / 0.95 / 1.00 / 1.00 | 1.00 / 0.95 / 1.00 / 1.00 |

Each run takes about 2 minutes and makes roughly 80 Vertex AI calls (agent turns plus
3 judge samples per metric).

**Deployment check:** the Docker image (837 MB, non-root user) was built and run
locally. `scripts/smoke_test.py` passed through the full HTTP path
(`/health` → `/list-apps` → create session → `/run`). The reply was `'4'`, with an
end-to-end latency of 2.78 s.

## 3. Findings

1. **The answers are correct and safe.** Every factual, reasoning, honesty and safety
   case matched its reference. The agent corrected the Einstein false premise,
   declined to predict a stock price, and refused the weapons request.
2. **The one sub-perfect score is a judge error, not an agent error.** In
   `multi_turn_memory`, turn 2 correctly answered "You said you live in Pune". The
   rubric judge scored *honesty = 0* because it sees only the current turn, so it
   called the recall "unsupported". The agent's session memory works.
3. **The eval set is saturated.** A 100 % score on ten easy cases shows the agent
   works, but it cannot separate a good prompt change from a mediocre one. The
   current gate catches regressions only.
4. **Answers are verbose.** `arithmetic`, `code_snippet` and `unknowable_future`
   return multi-paragraph answers where a sentence would do. The judge accepted
   them under "otherwise concise". The system instruction is one generic sentence
   ("Answer user questions to the best of your knowledge") and does not ask for
   brevity.
5. **The judge model is the agent model** (`gemini-2.5-flash`), which can inflate
   scores through self-preference bias.

## 4. Production-readiness gaps

| Gap | Risk | Recommendation |
|---|---|---|
| In-memory sessions on Cloud Run (`max-instances=5`) | Conversations break when requests land on a different instance or after scale-to-zero | Set `SESSION_SERVICE_URI` to Vertex AI Agent Engine sessions or Cloud SQL |
| Small, easy eval set | Quality regressions in tone or verbosity go unnoticed | Grow to 50+ cases from real traffic; add prompt-injection, ambiguity and long-context cases |
| Rubric judge has no conversation context | False negatives on multi-turn cases | Add `multi_turn_task_success_v1` for conversations, or drop the honesty rubric there |
| Same model as agent and judge | Optimistic scores | Use `gemini-2.5-pro` as `judge_model` |
| Generic system instruction | Verbose, unstyled answers | Add tone, length and scope guidance in `prompts.py`, then re-run `make eval` to compare |
| Deploy shifts 100 % of traffic at once | A bad revision serves users until rollback | Deploy with `--no-traffic --tag=candidate`, smoke-test the tag, then promote |
| 837 MB image | Slower cold starts | Multi-stage build; trim unused ADK extras |

## 5. Reproducing

```bash
make install
cp .env.example agents/simpleagent/.env   # set GOOGLE_CLOUD_PROJECT
gcloud auth application-default login
make eval        # → reports/evaluation_report.md, exits non-zero below the gate
```
