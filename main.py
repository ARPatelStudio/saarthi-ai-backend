import os
import logging
import tempfile
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from groq import AsyncGroq
from dotenv import load_dotenv

# Logs Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Saarthi AI Core", version="2.2.0") # Version updated

# API Key check
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")

client = AsyncGroq(api_key=api_key)

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = "You are Saarthi, a smart AI assistant. Response should be in Hinglish."

class ChatResponse(BaseModel):
    reply: str

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (Chat + Audio Ready)!"}

# ==========================================
# 🧠 THE BRAIN: Text Chat Endpoint
# ==========================================
@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    try:
        logger.info(f"📩 Received Text: {request.message}")
        
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
        logger.info("✅ Success from Groq Chat")
        return {"reply": reply_text}

    except Exception as e:
        logger.error(f"💥 CRITICAL CHAT ERROR: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Saarthi Brain Error: {str(e)}"
        )

# ==========================================
# 👂 THE EARS: Audio Transcription Endpoint
# ==========================================
@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    temp_file_path = ""
    try:
        logger.info(f"🎤 Received Audio File: {file.filename}")
        
        # 1. Android se aayi file ko server par temporarily save karo
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".m4a") as temp_audio:
            temp_audio.write(contents)
            temp_file_path = temp_audio.name

        # 2. Audio ko Groq Whisper API par bhejo
        logger.info("🚀 Sending audio to Groq Whisper...")
        with open(temp_file_path, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                file=(file.filename, audio_file.read()),
                model="whisper-large-v3", # 2026 ka sabse fast aur smart audio model
                response_format="json"
            )
        
        transcribed_text = transcription.text.strip()
        logger.info(f"✅ Transcription Success: {transcribed_text}")
        
        # 3. Server se kachra (temp file) saaf karo
        os.remove(temp_file_path)

        # 4. Android ko text wapas bhejo (Android isko JSON { "text": "..." } format mein expect kar raha hai)
        return {"text": transcribed_text}

    except Exception as e:
        logger.error(f"💥 CRITICAL AUDIO ERROR: {str(e)}")
        # Agar error aaye, toh bhi temp file delete kar do taaki server ki memory na bhare
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(
            status_code=500, 
            detail=f"Saarthi Ears Error: {str(e)}"
        )
