import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from groq import AsyncGroq
from dotenv import load_dotenv

# Logs Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Saarthi AI Core", version="2.1.2")

# API Key check
api_key = os.getenv("GROQ_API_KEY")
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
        logger.info(f"📩 Received: {request.message}")
        
        # ✅ UPDATED MODEL ID: llama-3.1-8b-instant is the current replacement
        chat_completion = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.message}
            ],
            model="llama-3.1-8b-instant", 
            temperature=0.7,
            max_tokens=1024,
        )
        
        reply_text = chat_completion.choices[0].message.content
        logger.info("✅ Success from Groq")
        return {"reply": reply_text}

    except Exception as e:
        logger.error(f"💥 CRITICAL ERROR: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Saarthi Brain Error: {str(e)}"
        )
