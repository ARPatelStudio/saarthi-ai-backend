import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from groq import AsyncGroq # 2026 Standard: Using Async client
from dotenv import load_dotenv

# Logs enable karein taki Render mein asli wajah dikhe
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Saarthi AI Core", version="2.1.0")

# API Key check
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("❌ GROQ_API_KEY is missing in Environment Variables!")

# Async Client Initialize
client = AsyncGroq(api_key=api_key)

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = "You are Saarthi, a smart AI assistant. Response should be in Hinglish."

class ChatResponse(BaseModel):
    reply: str

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online!"}

@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    try:
        logger.info(f"📩 Received message: {request.message}")
        
        # Async call for 2026 performance
        chat_completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.message}
            ],
            model="llama3-8b-8192", # Stable model ID
            temperature=0.7,
            max_tokens=1024,
        )
        
        reply_text = chat_completion.choices[0].message.content
        logger.info("✅ Groq responded successfully")
        return {"reply": reply_text}

    except Exception as e:
        # 🚨 Yeh line Render ke Logs mein asli error dikhayegi
        logger.error(f"💥 CRITICAL ERROR: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Saarthi Brain Error: {str(e)}"
        )
