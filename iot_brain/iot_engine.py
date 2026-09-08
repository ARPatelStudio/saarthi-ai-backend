import logging

logger = logging.getLogger(__name__)

def trigger_iot_webhook(device_name: str, action: str):
    """Base structure to trigger Local Network / IoT devices via Macrodroid or n8n local"""
    return f"Boss, Maine '{device_name}' par '{action}' command bhej di hai (IoT Webhook triggered)."
