import os
import logging
import tempfile
import json
import datetime
import pytz
import requests
import re
import base64
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from groq import AsyncGroq
from dotenv import load_dotenv
from duckduckgo_search import DDGS 
from pymongo import MongoClient
import certifi

# Logs Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Version Updated: Precise Volume Controls (Percentage & Full Volume) Added
app = FastAPI(title="Saarthi AI Core", version="28.2.0") 

# API Keys
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")

client = AsyncGroq(api_key=api_key)
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

MONGO_URI = "mongodb+srv://favouritegamer192_db_user:pjt6UStm6rB3ekEv@saarthi.sfsuxij.mongodb.net/?appName=Saarthi"
try:
    mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = mongo_client["saarthi_db"]
    memory_col = db["permanent_memory"]
    mongo_client.admin.command('ping') 
    logger.info("🟢 MongoDB Cloud Brain Connected Successfully!")
except Exception as e:
    logger.error(f"🔴 MongoDB Connection Error: {e}")

def get_cloud_memory():
    try:
        memories = memory_col.find({})
        mem_list = [f"- {m['key']}: {m['value']}" for m in memories]
        return "\n".join(mem_list) if mem_list else "Abhi tak koi memory save nahi hui hai."
    except Exception as e:
        return "Database error."

global_chat_history = []
last_bot_reply = "" 

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = """You are Saarthi (Jarvis), an ultra-intelligent, highly empathetic AI assistant. Converse in Hinglish."""
    android_memory: str = "" 

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          
    action_data1: str = ""        
    action_data2: str = ""        
    action_data3: str = ""        

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (V28.2.0: Precise Volume Mode Active)!"}

def perform_web_search(query: str):
    try:
        results = DDGS().text(query, max_results=3)
        if not results: return "Web par kuch nahi mila boss."
        summary = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return f"Live Web Data for '{query}':\n{summary}"
    except Exception as e: return "Search engine mein issue hai boss."

def get_live_weather(location: str):
    if not WEATHER_API_KEY: return "Weather API key missing hai boss."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={WEATHER_API_KEY}&units=metric&lang=hi"
        response = requests.get(url).json()
        if response.get("cod") != 200: return f"Sorry boss, mujhe {location} ka exact weather data nahi mil pa raha."
        return f"Live Update: {location} mein abhi temp {response['main']['temp']}°C hai aur mausam '{response['weather'][0]['description']}' jaisa hai."
    except Exception as e: return "Weather API mein thoda glitch aaya boss."

saarthi_tools = [
    {
        "type": "function",
        "function": {
            "name": "perform_web_search",
            "description": "Search the internet.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_weather",
            "description": "Fetch real-time weather.",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_device",
            "description": "Control hardware, apps, UI, Media, Volume, and Vision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string", 
                        # 🚀 FIX: 'volume_set' yahan add kiya gaya hai percent control ke liye
                        "enum": ["open_app", "close_app", "youtube_search", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "open_camera", "open_scanner", "set_alarm", "set_timer", "bluetooth_settings", "gps_settings", "quick_share", "vision_scanning", "scan_vision", "volume_up", "volume_down", "volume_mute", "volume_unmute", "volume_set"]
                    },
                    "app_package": {
                        "type": "string", 
                        # 🚀 FIX: Ab app_package volume ka percentage (number) bhi receive karega
                        "description": "App name, search query, OR volume percentage (e.g., '50', '100')."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "communicate",
            "description": "Make a phone call or send a WhatsApp message smartly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["call", "whatsapp"]},
                    "contact_name": {"type": "string"},
                    "message_text": {"type": "string"}
                },
                "required": ["method", "contact_name"]
            }
        }
    }
]

@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    global global_chat_history
    global last_bot_reply
    
    if last_bot_reply and last_bot_reply.lower() in request.message.lower() and len(request.message) > 10:
        return ChatResponse(reply="...", action="NONE") 
        
    try:
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone).strftime('%A, %d %B %Y, %I:%M %p')
        memory_context = f"\n[Android GPS/Memory: {request.android_memory}]"
        
        # 🚀 FIX: AI ko Percentage Volume aur Full Volume ki training di gayi hai
        router_system_prompt = f"""You are a smart tool-routing AI. Choose ONE tool.
        INTENT GUIDE:
        1. Volume Percentage: "volume 50% kar do", "full volume" -> 'volume_set' with app_package="50" (or "100" for full).
        2. General Volume: "volume mute kar do", "volume up" -> 'volume_mute', 'volume_up'. "volume kam karo" -> 'volume_down'. "volume unmute karo" -> 'volume_unmute'.
        3. Bluetooth: "bluetooth on/off karo" -> 'bluetooth_settings'.
        4. GPS/Location: "location chalu karo" -> 'gps_settings'.
        5. Quick Share/File Share: "quick share kholo" -> 'quick_share'.
        6. Hidden Vision (Ghost Eyes): "samne dekho", "chup chap photo lo", "eyes open" -> 'open_camera'.
        7. Visible Vision (Scanner UI): "scanner kholo", "camera khol kar scan karo", "scanner chalu karo" -> 'open_scanner'.
        8. YouTube: "baaghi 4 lagao" -> 'youtube_search'.
        9. Media: "roko", "play karo" -> 'media_pause', 'media_play'.
        """
        
        router_messages = [{"role": "system", "content": router_system_prompt}, {"role": "user", "content": request.message}]
        
        chat_completion_router = await client.chat.completions.create(
            messages=router_messages, model="llama-3.3-70b-versatile", tools=saarthi_tools, tool_choice="auto", temperature=0.0, max_tokens=1024, parallel_tool_calls=False
        )
        
        response_message = chat_completion_router.choices[0].message
        tool_calls = response_message.tool_calls

        creative_messages = [
            {"role": "system", "content": f"{request.system_prompt}\nREALTIME DATA:\n- Time: {live_time} {memory_context}"},
            {"role": "user", "content": request.message}
        ]

        if tool_calls:
            tool_call = tool_calls[0]
            func_name = tool_call.function.name
            try: func_args = json.loads(tool_call.function.arguments)
            except: func_args = {}

            if func_name == "perform_web_search":
                web_data = perform_web_search(func_args.get("query", request.message))
                creative_messages.append(response_message)
                creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": web_data})
                final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
                return ChatResponse(reply=final_response.choices[0].message.content)
            
            elif func_name == "get_live_weather":
                weather_data = get_live_weather(func_args.get("location", "India"))
                creative_messages.append(response_message)
                creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": weather_data})
                final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
                return ChatResponse(reply=final_response.choices[0].message.content)
            
            elif func_name == "control_device":
                action = func_args.get("action")
                if action in ["vision_scanning", "scan_vision"]:
                    action = "open_scanner"
                return ChatResponse(reply="Processing request, boss.", action="CONTROL_DEVICE", action_data1=action, action_data2=func_args.get("app_package", ""))
            
            elif func_name == "communicate":
                return ChatResponse(reply="Processing request, boss.", action="COMMUNICATE", action_data1=func_args.get("method", "call"), action_data2=func_args.get("contact_name", ""))

        final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
        reply_text = final_response.choices[0].message.content
        last_bot_reply = reply_text
        return ChatResponse(reply=reply_text)

    except Exception as e:
        return ChatResponse(reply="Boss, server mein thodi technical dikkat aayi.", action="NONE")

# ==========================================
# 👁️ VISION AI ENDPOINT
# ==========================================
@app.post("/api/vision")
async def vision_analysis(file: UploadFile = File(...), prompt: str = Form("Is photo mein kya hai? Detail mein Hindi/Hinglish mein batao.")):
    try:
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
        
        chat_completion = await client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt + " Answer in short 2 lines. Start with 'Boss, mujhe dikh raha hai ki...'"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            temperature=0.5,
            max_tokens=300,
        )
        return {"reply": chat_completion.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    temp_file_path = ""
    try:
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".m4a") as temp_audio:
            temp_audio.write(contents)
            temp_file_path = temp_audio.name

        with open(temp_file_path, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                file=(file.filename, audio_file.read()),
                model="whisper-large-v3",
                language="hi",
                prompt="Haan boss, bataiye. Main bilkul theek hoon. Ignore ALL background noise.", 
                response_format="json"
            )
        
        os.remove(temp_file_path)
        raw_text = transcription.text.strip()
        
        hallucinations = ["Thank you for watching.", "Thanks for watching", "Thank you.", "Subscribe", "watching.", "didn't catch that", "Can you repeat"]
        for bad_word in hallucinations:
            raw_text = re.sub(re.escape(bad_word), "", raw_text, flags=re.IGNORECASE).strip()
            
        if not raw_text or len(raw_text) < 3:
            return {"text": "[error]"}
            
        return {"text": raw_text}
        
    except Exception as e:
        if os.path.exists(temp_file_path): os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=str(e))
