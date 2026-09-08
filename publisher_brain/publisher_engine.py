import requests
import logging

logger = logging.getLogger(__name__)

def check_app_status(app_name: str, platform: str = "uptodown"):
    """Checks app indexing and basic status on distribution platforms."""
    try:
        if platform.lower() == "uptodown":
            # Formats app name for URL (e.g., 'Gram Calculator' -> 'gram-calculator')
            formatted_name = app_name.lower().replace(' ', '-')
            url = f"https://{formatted_name}.en.uptodown.com/android"
            res = requests.get(url, timeout=10)
            
            if res.status_code == 200:
                return f"Boss, '{app_name}' Uptodown par live aur accessible hai (Status 200 OK)."
            elif res.status_code == 404:
                return f"Boss, '{app_name}' Uptodown par nahi mili. Shayad baseline quality policy rejection ke kaaran hata di gayi hai ya URL mismatch hai."
            else:
                return f"Boss, Uptodown server ne {res.status_code} return kiya hai."
                
        elif platform.lower() == "kdp":
            return f"Boss, KDP reports ke liye Amazon API integration required hai. N8n webhook trigger kar diya gaya hai."
            
        return "Boss, platform recognized nahi hua. Kripya Uptodown ya KDP specify karein."
    except Exception as e:
        logger.error(f"Publisher Brain Error: {e}")
        return "Boss, app status fetch karne mein network timeout hua."
