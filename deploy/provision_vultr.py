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

# auto-load keys from the repo-root .env so a single command works
_envp = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(_envp):
    for _l in open(_envp):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

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


def read_pubkey():
    """Public SSH key from SSH_PUBKEY env, or any *.pub in ~/.ssh (preferring the
    usual names). Set SSH_PUBKEY=/path/to/key.pub to force a specific one."""
    v = os.getenv("SSH_PUBKEY", "").strip()
    if v:
        return open(os.path.expanduser(v)).read().strip() if os.path.exists(os.path.expanduser(v)) else v
    ssh = os.path.expanduser("~/.ssh")
    prefer = ["id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub"]
    found = [f for f in prefer if os.path.exists(os.path.join(ssh, f))]
    if not found and os.path.isdir(ssh):
        found = sorted(f for f in os.listdir(ssh) if f.endswith(".pub"))
    if found:
        p = os.path.join(ssh, found[0])
        print(f"using SSH public key {p}")
        return open(p).read().strip()
    return ""


def ssh_key_id():
    pub = read_pubkey()
    if not pub:
        print("no SSH public key found (SSH_PUBKEY env or ~/.ssh/*.pub) — creating without SSH key")
        return None
    # reuse an already-registered identical key, else register it
    for k in c.get("/ssh-keys", params={"per_page": 500}).json().get("ssh_keys", []):
        if k["ssh_key"].split()[:2] == pub.split()[:2]:
            return k["id"]
    r = c.post("/ssh-keys", json={"name": "covenant-sentinel", "ssh_key": pub})
    r.raise_for_status()
    print("registered your SSH public key with Vultr")
    return r.json()["ssh_key"]["id"]

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
ssh_pwauth: true
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
    kid = ssh_key_id()
    print(f"region={region} plan={PLAN} os_id={os_id} ssh_key={'yes' if kid else 'no'}")
    body = {
        "region": region, "plan": PLAN, "os_id": os_id,
        "label": "covenant-sentinel", "hostname": "covenant-sentinel",
        **({"sshkey_id": [kid]} if kid else {}),
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
        try:
            d = c.get(f"/instances/{iid}").json().get("instance") or {}
        except Exception as e:
            print(f"  (poll retry: {str(e)[:50]})")
            continue
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
