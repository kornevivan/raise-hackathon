"""Provision a Vultr Cloud Compute instance and deploy Covenant Sentinel via
cloud-init (clone the public GitHub repo + docker compose up). Uses only the
Vultr HTTPS API — no SSH needed.

    export VULTR_API_KEY=<account key>            # from .env
    export VULTR_INFERENCE_API_KEY=<inference key>
    python deploy/provision_vultr.py https://github.com/<you>/<repo>.git [region] [plan]

Prints the public URL when the instance is up. cloud-init then builds the image
(~3-5 min) before the site answers on :80.
"""
import base64
import os
import sys
import time

import httpx

REPO = sys.argv[1] if len(sys.argv) > 1 else os.getenv("REPO_URL", "")
REGION = sys.argv[2] if len(sys.argv) > 2 else os.getenv("REGION", "")
PLAN = sys.argv[3] if len(sys.argv) > 3 else os.getenv("PLAN", "vc2-2c-4gb")

ACCOUNT = os.getenv("VULTR_API_KEY", "").strip()
INFER = os.getenv("VULTR_INFERENCE_API_KEY", "").strip()
if not REPO or not ACCOUNT or not INFER:
    sys.exit("need repo URL arg + VULTR_API_KEY + VULTR_INFERENCE_API_KEY in env")

API = "https://api.vultr.com/v2"
H = {"Authorization": f"Bearer {ACCOUNT}", "Content-Type": "application/json"}
c = httpx.Client(base_url=API, headers=H, timeout=60)

ENV = f"""VULTR_INFERENCE_API_KEY={INFER}
VULTR_MODEL_PRIME=deepseek-ai/DeepSeek-V4-Flash
VULTR_MODEL_CORE=deepseek-ai/DeepSeek-V4-Flash
VULTR_MODEL_FLASH=deepseek-ai/DeepSeek-V4-Flash
VULTR_RETRIEVER_PRIME=vultr/VultronRetrieverPrime-Qwen3.5-8B
VULTR_RETRIEVER_CORE=vultr/VultronRetrieverCore-Qwen3.5-4.5B
VULTR_RETRIEVER_FLASH=vultr/VultronRetrieverFlash-Qwen3.5-0.8B
DEMO_PACE_MS=420
"""

CLOUD_INIT = f"""#cloud-config
write_files:
  - path: /root/app.env
    permissions: '0600'
    content: |
{os.linesep.join('      ' + l for l in ENV.splitlines())}
runcmd:
  - [ bash, -lc, "curl -fsSL https://get.docker.com | sh" ]
  - [ bash, -lc, "git clone {REPO} /opt/cs && cp /root/app.env /opt/cs/.env" ]
  - [ bash, -lc, "cd /opt/cs && docker compose up -d --build > /var/log/cs-deploy.log 2>&1" ]
"""


def find_os():
    for o in c.get("/os", params={"per_page": 500}).json()["os"]:
        if "Ubuntu 24.04" in o["name"] and o["arch"] == "x64":
            return o["id"]
    return 2284  # Ubuntu 24.04 x64 fallback


def pick_region():
    if REGION:
        return REGION
    # choose a region that actually offers the plan
    for p in c.get("/plans", params={"per_page": 500}).json().get("plans", []):
        if p["id"] == PLAN and p.get("locations"):
            for pref in ("ewr", "fra", "ams", "lhr"):
                if pref in p["locations"]:
                    return pref
            return p["locations"][0]
    return "ewr"


def main():
    os_id = find_os()
    region = pick_region()
    print(f"region={region} plan={PLAN} os_id={os_id}")
    body = {
        "region": region, "plan": PLAN, "os_id": os_id,
        "label": "covenant-sentinel", "hostname": "covenant-sentinel",
        "user_data": base64.b64encode(CLOUD_INIT.encode()).decode(),
        "backups": "disabled",
    }
    r = c.post("/instances", json=body)
    r.raise_for_status()
    inst = r.json()["instance"]
    iid = inst["id"]
    print("instance created:", iid, "— waiting for IP…")
    ip = ""
    for _ in range(60):
        time.sleep(10)
        d = c.get(f"/instances/{iid}").json()["instance"]
        ip = d.get("main_ip", "")
        if ip and ip != "0.0.0.0" and d.get("status") == "active":
            break
        print(f"  status={d.get('status')} power={d.get('power_status')} ip={ip}")
    print("\n==============================================")
    print(f"  Instance up at IP: {ip}")
    print(f"  Public demo URL (once cloud-init finishes the build, ~3-5 min):")
    print(f"      http://{ip}")
    print(f"  Health check:  curl http://{ip}/api/health")
    print("==============================================")


if __name__ == "__main__":
    main()
