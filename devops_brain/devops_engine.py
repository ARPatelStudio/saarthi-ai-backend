import requests
import logging
import os

logger = logging.getLogger(__name__)

def check_server_health():
    """Pings core infrastructure to check health"""
    results = []
    
    # 1. Vector Brain (Render 2)
    vector_url = os.getenv("VECTOR_SERVER_URL")
    if vector_url:
        try:
            res = requests.get(f"{vector_url}/", timeout=5)
            results.append("✅ Vector Brain (Render 2): ONLINE" if res.status_code == 200 else f"⚠️ Vector Brain: HTTP {res.status_code}")
        except Exception:
            results.append("🔴 Vector Brain: OFFLINE / UNREACHABLE")

    # 2. n8n Server
    n8n_url = os.getenv("N8N_WEBHOOK_URL")
    if n8n_url:
        base_n8n = n8n_url.split("/webhook")[0]
        try:
            requests.get(base_n8n, timeout=5)
            results.append("✅ n8n Server: ONLINE")
        except Exception:
            results.append("🔴 n8n Server: OFFLINE / UNREACHABLE")

    return "Server Status Report:\n" + "\n".join(results) if results else "Boss, external server URLs configured nahi hain."
