"""Central configuration. All model ids, budgets and endpoints live here."""
from __future__ import annotations

import os

# --- Vultr Serverless Inference (OpenAI-compatible) ---------------------------
# The inference key is issued when you create a Serverless Inference subscription
# in the Vultr portal (requires a verified account email). It is DIFFERENT from
# the account API key used to manage resources.
VULTR_BASE_URL = os.getenv("VULTR_BASE_URL", "https://api.vultrinference.com/v1")
VULTR_INFERENCE_KEY = os.getenv("VULTR_INFERENCE_API_KEY", "").strip()

# Reasoning models (Vultr Serverless Inference chat LLMs). Three cognitive tiers.
# Set these from `GET /v1/models` once your inference subscription is live.
MODEL_PRIME = os.getenv("VULTR_MODEL_PRIME", "qwen2.5-72b-instruct")
MODEL_CORE = os.getenv("VULTR_MODEL_CORE", "qwen2.5-32b-instruct")
MODEL_FLASH = os.getenv("VULTR_MODEL_FLASH", "qwen2.5-7b-instruct")

# VultronRetriever — the layout-aware visual page retriever (three flavors,
# escalated by difficulty). Used through the Vultr Vector Store / retrieval API.
RETRIEVER_FLASH = os.getenv("VULTR_RETRIEVER_FLASH", "VultronRetrieverFlash-Qwen3.5-0.8B")
RETRIEVER_CORE = os.getenv("VULTR_RETRIEVER_CORE", "VultronRetrieverCore-Qwen3.5-4.5B")
RETRIEVER_PRIME = os.getenv("VULTR_RETRIEVER_PRIME", "VultronRetrieverPrime-Qwen3.5-8B")

# When true, reasoning + retrieval run through Vultr. When the inference key is
# absent we fall back to a deterministic, offline engine so the demo never fails
# and development can proceed before email verification. The trace always states
# which backend produced each step.
LIVE = bool(VULTR_INFERENCE_KEY)

# --- Hard budgets (enforced in code) -----------------------------------------
MAX_EVIDENCE_ITERS = 3       # per check
MAX_LLM_CALLS = 14           # per full run
LLM_TIMEOUT_S = 60
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
