import os
from fastapi import FastAPI, HTTPException, WebSocket
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Saarthi AI Core", version="2.0.0")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = "You are Saarthi, a highly advanced, intelligent personal AI assistant."

class ChatResponse(BaseModel):
    reply: str

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI Server is Online and Running on Render!"}

@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.message}
            ],
            model="llama3-70b-8192",
            temperature=0.7,
            max_tokens=1024,
        )
        return {"reply": chat_completion.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Groq API Error: {str(e)}")

@app.websocket("/ws/avatar")
async def avatar_websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text("Avatar Core Connected.")
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"[Processing Animation for: {data}]")
    except Exception as e:
        print(f"WebSocket Error: {e}")
