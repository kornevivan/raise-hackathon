# Deploying Covenant Sentinel on Vultr

Backend + UI ship as one Docker image; Caddy fronts it with automatic HTTPS.
Everything runs on a small **Vultr Cloud Compute** instance (the $200 hackathon
credit covers it many times over). Vultr GPUs are not used — all LLM work is on
**Vultr Serverless Inference**.

## 0. One‑time Vultr account setup
1. **Verify your account email** (Portal → Account). Vultr blocks new
   subscriptions until the email is verified.
2. **Create a Serverless Inference subscription** (Portal → Serverless Inference
   → Add). Copy its **API key** — this is `VULTR_INFERENCE_API_KEY` (different
   from your account API key).
3. Lock the exact model ids:
   ```bash
   export VULTR_INFERENCE_API_KEY=...    # inference subscription key
   python backend/probe_vultr.py         # prints VULTR_MODEL_* / VULTR_RETRIEVER_* lines
   ```

## 1. Provision the instance
- Vultr Cloud Compute, **Ubuntu 24.04**, a 2 vCPU / 4 GB plan is plenty (the app
  is I/O bound — the heavy lifting is on Serverless Inference).
- Open ports **80** and **443** in the instance firewall.

## 2. Deploy
```bash
ssh root@YOUR_INSTANCE_IP
apt-get update && apt-get install -y docker.io docker-compose-plugin git
git clone https://github.com/<you>/covenant-sentinel.git
cd covenant-sentinel
cp .env.example .env && nano .env          # paste VULTR_INFERENCE_API_KEY + model ids

# HTTPS with a domain (point an A record at the instance first):
SITE_ADDRESS=covenant.yourdomain.com docker compose up -d --build
# …or plain HTTP by IP (no domain needed):
docker compose up -d --build
```

- With a domain → `https://covenant.yourdomain.com`
- By IP → `http://YOUR_INSTANCE_IP`  ← paste this as the **public demo URL**

## 3. Verify
```bash
curl -s http://YOUR_INSTANCE_IP/api/health | jq
#   "live_inference": true   → reasoning + retrieval on Vultr
```
Open the URL, run **S1 — The Amendment Twist**, and confirm the ratio flips
3.55× → 3.42×. Record the 1‑minute video against this deployed URL.

## Notes
- The demo works even before the inference key is set (deterministic offline
  mode) — but for judging, set the key so `live_inference` is `true`.
- The corpus is committed and deterministic; no data step is needed on the server.
- Logs: `docker compose logs -f app`.
