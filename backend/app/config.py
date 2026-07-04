"""Central configuration. All model ids, budgets and endpoints live here."""
from __future__ import annotations

import os


def _load_dotenv():
    """Minimal .env loader (repo root or backend/). Does not override existing
    environment (so docker-compose / shell exports win). Tolerates 'K = V' spacing."""
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.path.join(here, "..", ".env"), os.path.join(here, "..", "..", ".env")):
        if not os.path.exists(path):
            continue
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# --- Vultr Serverless Inference (OpenAI-compatible) ---------------------------
# The inference key is issued when you create a Serverless Inference subscription
# in the Vultr portal (requires a verified account email). It is DIFFERENT from
# the account API key used to manage resources.
# bump on every deploy-relevant change so /api/health confirms what's running
APP_VERSION = "3.0.0-derived-pipeline"

VULTR_BASE_URL = os.getenv("VULTR_BASE_URL", "https://api.vultrinference.com/v1")
VULTR_INFERENCE_KEY = os.getenv("VULTR_INFERENCE_API_KEY", "").strip()

# Reasoning models (Vultr Serverless Inference chat LLMs). Three cognitive tiers.
# Chosen from the live `/v1/models` for reliable JSON + low latency (see probe).
MODEL_PRIME = os.getenv("VULTR_MODEL_PRIME", "deepseek-ai/DeepSeek-V4-Flash")
MODEL_CORE = os.getenv("VULTR_MODEL_CORE", "deepseek-ai/DeepSeek-V4-Flash")
MODEL_FLASH = os.getenv("VULTR_MODEL_FLASH", "deepseek-ai/DeepSeek-V4-Flash")

# VultronRetriever — the layout-aware page retriever (three flavors, escalated by
# difficulty). Fronted by the Vultr Vector Store; exact ids from `/v1/models`.
RETRIEVER_FLASH = os.getenv("VULTR_RETRIEVER_FLASH", "vultr/VultronRetrieverFlash-Qwen3.5-0.8B")
RETRIEVER_CORE = os.getenv("VULTR_RETRIEVER_CORE", "vultr/VultronRetrieverCore-Qwen3.5-4.5B")
RETRIEVER_PRIME = os.getenv("VULTR_RETRIEVER_PRIME", "vultr/VultronRetrieverPrime-Qwen3.5-8B")

# When true, reasoning + retrieval run through Vultr. When the inference key is
# absent we fall back to a deterministic, offline engine so the demo never fails
# and development can proceed before email verification. The trace always states
# which backend produced each step.
LIVE = bool(VULTR_INFERENCE_KEY)

# --- Hard budgets (enforced in code) -----------------------------------------
MAX_EVIDENCE_ITERS = 3       # per check
MAX_LLM_CALLS = 14           # per full run
LLM_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT_S", "90"))   # Vultr serverless can cold-start
RUN_WATCHDOG_S = 240
TEMPERATURE = 0.1

# --- Paths -------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(HERE)
DATA_DIR = os.path.join(BACKEND_DIR, "data")
CORPUS_DIR = os.path.join(DATA_DIR, "corpus")
INDEX_PATH = os.path.join(CORPUS_DIR, "index.json")
FINANCIALS_PATH = os.path.join(DATA_DIR, "financials.json")
DB_PATH = os.path.join(DATA_DIR, "covenant.sqlite")
SCENARIOS_PATH = os.path.join(DATA_DIR, "scenarios.json")
CACHE_DIR = os.path.join(BACKEND_DIR, ".llm_cache")
