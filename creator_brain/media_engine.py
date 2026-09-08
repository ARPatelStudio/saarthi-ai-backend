import requests
import logging
import os
import base64
import cloudinary.uploader

logger = logging.getLogger(__name__)

def generate_image_hf(prompt: str):
    """Generates AI image via HuggingFace API and uploads to Cloudinary"""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        return "Boss, Hugging Face token (HF_TOKEN) set nahi hai."

    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {hf_token}"}

    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=60)
        if response.status_code == 200:
            b64_img = base64.b64encode(response.content).decode('utf-8')
            upload_result = cloudinary.uploader.upload(f"data:image/jpeg;base64,{b64_img}", folder="saarthi_creator")
            return f"Boss, image generate ho gayi hai! URL: {upload_result.get('secure_url')}"
        else:
            return f"Boss, image generation fail ho gaya. Error Code: {response.status_code}"
    except Exception as e:
        logger.error(f"Image Gen Error: {e}")
        return "Boss, AI media pipeline mein error aa gaya."
