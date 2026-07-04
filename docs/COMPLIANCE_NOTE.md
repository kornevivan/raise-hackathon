# Track compliance — VultronRetriever usage (P0-A)

**Finding (verified, reproducible):** the three VultronRetriever models are **retrieval-only**
on Vultr Serverless Inference. Their `/v1/chat/completions` and `/v1/completions` endpoints
return **HTTP 404** — they cannot generate text and therefore cannot run planner / gap-check /
verifier / memo reasoning. Evidence is produced by `python backend/probe_vultr.py`
(section "P0-A"):

```
vultr/VultronRetrieverPrime-Qwen3.5-8B   NOT CHAT-CAPABLE → 404 Not Found
vultr/VultronRetrieverCore-Qwen3.5-4.5B  NOT CHAT-CAPABLE → 404 Not Found
vultr/VultronRetrieverFlash-Qwen3.5-0.8B NOT CHAT-CAPABLE → 404 Not Found
```

This matches their model cards: VultronRetriever is a ColPali-style **visual page retriever**
(multi-vector embeddings + MaxSim), not a chat model.

**What this means for the rework's P0-A instruction.** "Route planner/verifier/memo onto
VultronRetriever-as-chat and remove every other model from the core path" is not achievable on
the current API — there is no VultronRetriever chat endpoint, and every text-generating model on
Vultr Serverless Inference is a *different* open-source model.

**Our compliant implementation (both requirements satisfied via Vultr Serverless Inference):**
- **Document retrieval → VultronRetriever, genuinely.** All three flavors (Flash/Core/Prime),
  tiered by difficulty, via the Vultr Vector Store. This is the brief's explicit requirement
  ("Use of the VultronRetriever Models for document retrieval").
- **Core reasoning → a Vultr-hosted open-source chat model** (`deepseek-ai/DeepSeek-V4-Flash`,
  selected by the probe for JSON reliability + latency). The brief permits "Open source LLMs
  served over an OpenAI compatible API"; this runs entirely on **Vultr Serverless Inference**,
  which is the platform requirement.

The three-tier badges in the UI show the real model per step: VultronRetriever ids on retrieval
steps, the Vultr chat model on reasoning steps, each labeled Vultr vs deterministic.

**If the judges require reasoning literally on VultronRetriever ids:** that is impossible until
Vultr exposes a chat endpoint for those models. We will switch the moment it exists — the router
is one config change (`backend/app/config.py` MODEL_PRIME/CORE/FLASH). This note + the probe are
our due-diligence record.
