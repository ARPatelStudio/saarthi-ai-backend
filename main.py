import os
import logging
import tempfile
import json
import datetime
import pytz
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from groq import AsyncGroq
from dotenv import load_dotenv
from duckduckgo_search import DDGS 

# Logs Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Version Updated: Translator Mode, Auto-Correction AI & Close All Apps Added
app = FastAPI(title="Saarthi AI Core", version="22.0.0") 

# API Keys
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")

client = AsyncGroq(api_key=api_key)

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = """You are Saarthi (Jarvis), an ultra-intelligent, highly empathetic AI assistant.
    CRITICAL RULES:
    1. LANGUAGE & TRANSLATOR: Converse naturally in 'Hinglish' (Hindi words in English alphabet). NEVER use Devanagari or Urdu. IF the user asks you to translate something (e.g., English to Hindi, or any language), act as a Real-Time Translator and provide the exact translation in Hinglish.
    2. AUTO-CORRECT: The voice-to-text might send you misspelled or broken words. Use your High IQ to auto-correct the user's intent internally before responding.
    3. IQ & EQ: You have an IQ of 250+. Act as a friendly companion, a Love Guru, or a wise counselor. Address the user as 'Boss'.
    4. VOICE FOCUS: The user's voice is the ONLY authority. Ignore background noise. Focus ONLY on the primary speaker.
    5. TONE: Keep your responses highly accurate, natural, crisp, short, and human-like."""
    android_memory: str = "" 

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          
    action_data1: str = ""        
    action_data2: str = ""        
    action_data3: str = ""        

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (V22: Translator + Auto-Correct + Close All Apps Active)!"}

# ==========================================
# ⚙️ SAARTHI'S NATIVE TOOLS (Powers)
# ==========================================

def perform_web_search(query: str):
    logger.info(f"🔍 Searching Web for: {query}")
    try:
        results = DDGS().text(query, max_results=3)
        if not results: return "Web par kuch nahi mila boss."
        summary = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return f"Live Web Data for '{query}':\n{summary}\n\nRead this data and give a short, helpful Hinglish reply to the boss."
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
            "description": "Search the internet for real-time information, latest news, prices, or anything you don't know.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_weather",
            "description": "Fetch real-time weather and temperature for a city.",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "Open maps for a destination.",
            "parameters": {"type": "object", "properties": {"destination": {"type": "string"}}, "required": ["destination"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_memory",
            "description": "Remember personal information.",
            "parameters": {"type": "object", "properties": {"info_key": {"type": "string"}, "info_value": {"type": "string"}}, "required": ["info_key", "info_value"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_device",
            "description": "Control the Android phone's hardware, media, or applications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string", 
                        "enum": ["open_app", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "close_app", "volume_up", "volume_down", "volume_mute", "volume_unmute", "youtube_search", "brightness_up", "brightness_down", "bluetooth_settings", "volume_silent", "volume_ring", "auto_rotate_on", "auto_rotate_off", "open_calculator"]
                    },
                    "app_package": {
                        "type": "string", 
                        "description": "If action is 'open_app', provide ONLY the COMMON NAME of the app. DO NOT send package names."
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
            "description": "Make a phone call or send a WhatsApp message.",
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
    try:
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone).strftime('%A, %d %B %Y, %I:%M %p')
        memory_context = f"\n[User's Saved Memory: {request.android_memory}]" if request.android_memory else ""
        
        # 🚀 FIX: Added "sabhi app band karo" -> close_app mapping explicitly.
        router_system_prompt = f"""You are a smart, silent tool-routing AI. Users may speak in casual/broken Hinglish. AUTO-CORRECT their spelling internally and map to the correct tool. NEVER use XML tags.
        INTENT GUIDE:
        1. App Opening: "khol", "open", "chalao" + [App Name] -> 'control_device' -> 'open_app' with app name.
        2. Toggles: "band/off/mute" -> '_off' or '_mute'. "chalu/on/badhao" -> '_on' or '_up'.
        3. YouTube: "song", "gaana", "movie", "video" -> ALWAYS use 'youtube_search'. Include "song" if requested.
        4. Close All / Go Home: "sabhi app band karo", "sabhi app close karo", "close all apps", "clear screen" -> ALWAYS use 'control_device' -> 'close_app'.
        5. Translation: If user asks to translate, DO NOT invoke any tools. Just let the main AI translate it normally.
        6. Realtime Data - Time: {live_time}, Location: Indore, India {memory_context}"""
        
        router_messages = [{"role": "system", "content": router_system_prompt}, {"role": "user", "content": request.message}]
        
        chat_completion_router = await client.chat.completions.create(
            messages=router_messages, model="llama-3.1-8b-instant", tools=saarthi_tools, tool_choice="auto", temperature=0.0, max_tokens=1024,
        )
        
        response_message = chat_completion_router.choices[0].message
        tool_calls = response_message.tool_calls

        creative_messages = [
            {"role": "system", "content": f"{request.system_prompt}\nREALTIME DATA:\n- Time: {live_time}\n- Location: Indore, India {memory_context}"},
            {"role": "user", "content": request.message}
        ]

        if tool_calls:
            creative_messages.append(response_message)
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                if func_name == "perform_web_search":
                    web_data = perform_web_search(func_args.get("query"))
                    creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": web_data})
                elif func_name == "navigate_to":
                    return ChatResponse(reply="Processing request, boss.", action="OPEN_MAPS", action_data1=func_args.get("destination"))
                elif func_name == "save_to_memory":
                    return ChatResponse(reply="Processing request, boss.", action="SAVE_MEMORY", action_data1=func_args.get("info_key"), action_data2=func_args.get("info_value"))
                elif func_name == "control_device":
                    return ChatResponse(reply="Processing request, boss.", action="CONTROL_DEVICE", action_data1=func_args.get("action"), action_data2=func_args.get("app_package", ""))
                elif func_name == "communicate":
                    return ChatResponse(reply="Processing request, boss.", action="COMMUNICATE", action_data1=func_args.get("method"), action_data2=func_args.get("contact_name"), action_data3=func_args.get("message_text", ""))
                elif func_name == "get_live_weather":
                    weather_data = get_live_weather(func_args.get("location"))
                    creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": weather_data})

            if any(tc.function.name in ["perform_web_search", "get_live_weather"] for tc in tool_calls):
                final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
                return ChatResponse(reply=final_response.choices[0].message.content)

        final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
        logger.info("✅ Success from Groq Chat (70B)")
        return ChatResponse(reply=final_response.choices[0].message.content)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Saarthi Brain Error: {str(e)}")

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
                prompt="Haan boss, bataiye. Main bilkul theek hoon. Ignore ALL background noise, TV sounds, or secondary voices. Transcribe strictly the primary speaker's command.", 
                response_format="json"
            )
        
        os.remove(temp_file_path)
        return {"text": transcription.text.strip()}
    except Exception as e:
        if os.path.exists(temp_file_path): os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Saarthi Ears Error: {str(e)}")
