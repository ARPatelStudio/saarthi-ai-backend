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

# Version Updated: Volume Band/Chalu Slang added to Router + Voice Focus Maintained
app = FastAPI(title="Saarthi AI Core", version="15.0.0") 

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
    1. LANGUAGE: Converse naturally in 'Hinglish' (Hindi words written with the English alphabet). Example: 'Theek hai boss'. NEVER use Devanagari (हिंदी) or Urdu scripts.
    2. IQ & EQ: You have an IQ of 250+ and supreme knowledge in Science, Law, Medicine, History, and Psychology. Act as a friendly companion, a Love Guru, a comedian, or a wise counselor. Always address the user as 'Boss'.
    3. VOICE FOCUS: The user's voice is the ONLY authority. Ignore any chaotic background noise or multiple voices transcribed by mistake. Focus only on the core command given by the primary speaker (Boss).
    4. TONE: Keep your responses highly accurate, natural, crisp, short, and human-like."""
    android_memory: str = "" 

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          
    action_data1: str = ""        
    action_data2: str = ""        
    action_data3: str = ""        

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (God Mode + Voice Focus + Volume Band/Chalu Mapped)!"}

# ==========================================
# ⚙️ SAARTHI'S NATIVE TOOLS (Powers)
# ==========================================

def perform_web_search(query: str):
    logger.info(f"🔍 Searching Web for: {query}")
    try:
        results = DDGS().text(query, max_results=3)
        if not results:
            return "Web par kuch nahi mila boss."
        summary = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return f"Live Web Data for '{query}':\n{summary}\n\nRead this data and give a short, helpful Hinglish reply to the boss."
    except Exception as e:
        logger.error(f"Search Error: {e}")
        return "Search engine mein issue hai boss."

def get_live_weather(location: str):
    logger.info(f"☁️ Fetching live weather for: {location}")
    if not WEATHER_API_KEY:
        return f"Weather API key missing hai boss."
    
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={WEATHER_API_KEY}&units=metric&lang=hi"
        response = requests.get(url).json()
        
        if response.get("cod") != 200:
            return f"Sorry boss, mujhe {location} ka exact weather data nahi mil pa raha."
            
        temp = response['main']['temp']
        desc = response['weather'][0]['description']
        return f"Live Update: {location} mein abhi temp {temp}°C hai aur mausam '{desc}' jaisa hai."
    except Exception as e:
        logger.error(f"Weather API Error: {e}")
        return "Weather API mein thoda glitch aaya boss."

saarthi_tools = [
    {
        "type": "function",
        "function": {
            "name": "perform_web_search",
            "description": "Search the internet for real-time information, latest news, prices, or anything you don't know.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "The exact search query."}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_weather",
            "description": "Fetch real-time weather and temperature for a city.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "Open maps for a destination.",
            "parameters": {
                "type": "object",
                "properties": {"destination": {"type": "string"}},
                "required": ["destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_memory",
            "description": "Remember personal information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "info_key": {"type": "string"},
                    "info_value": {"type": "string"}
                },
                "required": ["info_key", "info_value"]
            }
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
                        "enum": ["open_app", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "close_app", "volume_up", "volume_down", "volume_mute", "volume_unmute", "youtube_search"]
                    },
                    "app_package": {
                        "type": "string", 
                        "description": "App package name, OR the search query if action is youtube_search."
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

# ==========================================
# 🧠 THE BRAIN: Split-Brain Architecture Endpoint 
# ==========================================
@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    try:
        logger.info(f"📩 Received Text: {request.message}")
        
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone).strftime('%A, %d %B %Y, %I:%M %p')
        memory_context = f"\n[User's Saved Memory: {request.android_memory}]" if request.android_memory else ""
        
        # 🚀 FIX: Sikha diya ki "volume band" = mute aur "volume chalu" = unmute
        router_system_prompt = f"""You are a backend tool-routing AI. Your ONLY job is to select the correct tool based on the user's request.
        CRITICAL RULES:
        1. NEVER output text like '<function=...>' or XML tags. Use native JSON tool calling silently.
        2. HINGLISH MAPPING: If user says "volume band kar do" use action "volume_mute". If user says "volume chalu kar do" use action "volume_unmute".
        3. Realtime Data - Time: {live_time}, Location: Indore, India {memory_context}"""
        
        router_messages = [
            {"role": "system", "content": router_system_prompt},
            {"role": "user", "content": request.message}
        ]
        
        # 🧠 BRAIN 1: THE LOGIC ROUTER (8B Model - 100% Stable with 0.0 temp)
        chat_completion_router = await client.chat.completions.create(
            messages=router_messages,
            model="llama-3.1-8b-instant", 
            tools=saarthi_tools,
            tool_choice="auto",
            temperature=0.0, # Complete strictness
            max_tokens=1024,
        )
        
        response_message = chat_completion_router.choices[0].message
        tool_calls = response_message.tool_calls

        # 🧠 CREATIVE MESSAGES PREP (For 70B God Mode)
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
                    query = func_args.get("query")
                    web_data = perform_web_search(query)
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
                    location = func_args.get("location")
                    weather_data = get_live_weather(location)
                    creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": weather_data})

            # 🧠 BRAIN 2: THE CREATIVE GENIUS (70B Model - For Final Response)
            if any(tc.function.name in ["perform_web_search", "get_live_weather"] for tc in tool_calls):
                final_response = await client.chat.completions.create(
                    model="llama-3.3-70b-versatile", 
                    messages=creative_messages,
                    temperature=0.7 
                )
                return ChatResponse(reply=final_response.choices[0].message.content)

        # 🧠 BRAIN 2: THE CREATIVE GENIUS (No tools needed)
        final_response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=creative_messages,
            temperature=0.7
        )
        logger.info("✅ Success from Groq Chat (70B)")
        return ChatResponse(reply=final_response.choices[0].message.content)

    except Exception as e:
        logger.error(f"💥 CRITICAL CHAT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Saarthi Brain Error: {str(e)}")

# ==========================================
# 👂 THE EARS: Audio Transcription 
# ==========================================
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
                # 🚀 VOICE FOCUS Mapped properly!
                prompt="Haan boss, bataiye. Main bilkul theek hoon. Ignore background noise and focus only on the main speaker's command.", 
                response_format="json"
            )
        
        transcribed_text = transcription.text.strip()
        os.remove(temp_file_path)
        return {"text": transcribed_text}

    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Saarthi Ears Error: {str(e)}")
