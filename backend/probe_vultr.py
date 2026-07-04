"""Phase-0 probe. Run this AFTER you verify your Vultr account email and create a
Serverless Inference subscription, so you can lock the exact model ids.

    export VULTR_INFERENCE_API_KEY=...     # the inference subscription key
    python probe_vultr.py

It lists the chat + retriever models the endpoint actually serves and does a tiny
JSON-adherence test, then prints the VULTR_MODEL_* / VULTR_RETRIEVER_* lines to
paste into your .env.
"""
import json
import os
import sys

BASE = os.getenv("VULTR_BASE_URL", "https://api.vultrinference.com/v1")
KEY = os.getenv("VULTR_INFERENCE_API_KEY", "").strip()

if not KEY:
    sys.exit("Set VULTR_INFERENCE_API_KEY first (from your Serverless Inference subscription).")

try:
    from openai import OpenAI
except ImportError:
    sys.exit("pip install openai")

client = OpenAI(base_url=BASE, api_key=KEY, timeout=60)

print(f"== GET {BASE}/models ==")
try:
    models = client.models.list()
    ids = [m.id for m in models.data]
except Exception as e:
    sys.exit(f"models.list failed: {e}")

for i in ids:
    print("  ", i)

chat = [i for i in ids if not i.lower().startswith("vultronretriever")
        and "retriever" not in i.lower()]
retr = [i for i in ids if "retriever" in i.lower() or "vultron" in i.lower()]

print("\n== chat/reasoning candidates ==", chat)
print("== retriever candidates ==", retr)

# tiny JSON-adherence smoke test on the first chat model
if chat:
    m = chat[0]
    print(f"\n== JSON smoke test on {m} ==")
    try:
        r = client.chat.completions.create(
            model=m, temperature=0,
            messages=[{"role": "system", "content": "Reply with ONLY a JSON object."},
                      {"role": "user", "content": 'Return {"ok": true, "n": 42}.'}],
        )
        print("  ", r.choices[0].message.content)
    except Exception as e:
        print("   smoke test error:", e)

print("\n# --- paste into backend/.env (edit tiers to taste) ---")
def pick(lst, i, default):
    return lst[i] if i < len(lst) else (lst[-1] if lst else default)
print(f"VULTR_MODEL_PRIME={pick(chat, 0, 'CHANGE_ME')}")
print(f"VULTR_MODEL_CORE={pick(chat, min(1, len(chat)-1), 'CHANGE_ME')}")
print(f"VULTR_MODEL_FLASH={pick(chat, len(chat)-1, 'CHANGE_ME')}")
if retr:
    print(f"VULTR_RETRIEVER_PRIME={pick(retr, 0, 'CHANGE_ME')}")
    print(f"VULTR_RETRIEVER_CORE={pick(retr, min(1, len(retr)-1), 'CHANGE_ME')}")
    print(f"VULTR_RETRIEVER_FLASH={pick(retr, len(retr)-1, 'CHANGE_ME')}")
