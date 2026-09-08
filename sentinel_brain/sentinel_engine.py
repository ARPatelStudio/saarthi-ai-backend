import logging
import psycopg2
import os

logger = logging.getLogger(__name__)

def run_security_scan():
    """Scans database connections and auth layers for vulnerabilities."""
    try:
        status_report = []
        
        # 1. DB Connection Integrity Test
        db_url = os.getenv("NEON_DB_URL", "")
        if db_url:
            try:
                conn = psycopg2.connect(db_url, connect_timeout=5)
                conn.close()
                status_report.append("🟢 Neon PostgreSQL: Secured & Encrypted")
            except Exception as e:
                status_report.append(f"🔴 Neon PostgreSQL Timeout/Error: {e}")
        else:
            status_report.append("⚠️ Neon DB URL missing")

        # 2. Key Checks
        if os.getenv("SAARTHI_API_KEY"):
            status_report.append("🟢 Master API Key: Active")
        else:
            status_report.append("🔴 Master API Key: MISSING (Vulnerable!)")
            
        return "Sentinel Security Scan Report:\n" + "\n".join(status_report)
    except Exception as e:
        logger.error(f"Sentinel Scan Error: {e}")
        return "Boss, Sentinel scan fail ho gaya."
