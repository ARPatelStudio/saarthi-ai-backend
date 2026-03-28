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
from duckduckgo_search import DDGS # 🚀 NAYA: Web Search Engine

# Logs Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

load_dotenv()

# Version Updated for God Mode, High IQ 70B, Error 400 COMPLETE FIX
app = FastAPI(title="Saarthi AI Core", version="8.3.0") 

# API Keys
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")

client = AsyncGroq(api_key=api_key)

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

class ChatRequest(BaseModel):
    message: str
    # 🚀 THE MAGIC FIX: Removed all mentions of tools and <function> tags. 
    # Let the Groq API handle the tool routing naturally!
    system_prompt: str = """You are Saarthi (Jarvis), an ultra-intelligent, highly empathetic, and omniscient AI assistant. 
    CRITICAL RULES: 
    1. SCRIPT: You MUST write your text responses ONLY using the English/Latin alphabet (A-Z). Speak in 'Hinglish' (Hindi words written in English letters). NEVER output Devanagari (हिंदी) or Urdu. Example: Write 'Theek hai boss' instead of 'ठीक है बॉस'.
    2. IQ & EQ: You have an IQ of 250+ and supreme knowledge in all domains (Science, Law, Medicine, Love Guru, Kids psychology, etc.). 
    3. PERSONA: Act as a friendly companion and ALWAYS address the user as 'Boss'. Keep your conversational responses natural, crisp, short, and human-like."""
    android_memory: str = "" 

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          
    action_data1: str = ""        
    action_data2: str = ""        
    action_data3: str = ""        

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (God Mode 70B + Error 400 Bulletproof Fix)!"}

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
        return f"Weather API key missing hai boss, check kar lijiye."
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
        return "Weather API mein thoda glitch aaya hai boss."

saarthi_tools = [
    {
        "type": "function",
        "function": {
            "name": "perform_web_search",
            "description": "Use this tool immediately if the user asks for real-time information, latest news, current prices (e.g., iPhone 15 price), or anything that requires internet access.",
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
                "properties": {"location": {"type": "string", "description": "City name, e.g., Indore"}},
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "Trigger this when the user wants to go somewhere, needs directions, or asks to open maps.",
            "parameters": {
                "type": "object",
                "properties": {"destination": {"type": "string", "description": "The exact place or city."}},
                "required": ["destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_memory",
            "description": "Use this to REMEMBER personal information the user tells you.",
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
            "description": "Control the Android phone's hardware, media, volume, or search youtube.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string", 
                        "enum": ["open_app", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "close_app", "volume_up", "volume_down", "youtube_search"],
                    },
                    "app_package": {
                        "type": "string", 
                        "description": "If opening an app, guess the exact Android package name. If action is 'youtube_search', put the song/video query here."
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
            "description": "Make a phone call or send a WhatsApp message to a specific contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["call", "whatsapp"]},
                    "contact_name": {"type": "string"},
                    "message_text": {"type": "string", "description": "Leave completely empty if making a phone call."}
                },
                "required": ["method", "contact_name"]
            }
        }
    }
]

# ==========================================
# 🧠 THE BRAIN: Text Chat Endpoint (With Routing)
# ==========================================
@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    try:
        logger.info(f"📩 Received Text: {request.message}")
        
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone).strftime('%A, %d %B %Y, %I:%M %p')
        memory_context = f"\n[User's Saved Memory: {request.android_memory}]" if request.android_memory else ""
        
        dynamic_system_prompt = f"""
        {request.system_prompt}
        REALTIME DATA:
        - Current Time & Date: {live_time}
        - User's Location: Indore, Madhya Pradesh, India {memory_context}
        """
        
        messages = [
            {"role": "system", "content": dynamic_system_prompt},
            {"role": "user", "content": request.message}
        ]
        
        # 🚀 HIGH IQ MODEL (70B)
        chat_completion = await client.chat.completions.create(
            messages=messages,
            model="llama-3.3-70b-versatile", 
            tools=saarthi_tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1024,
        )
        
        response_message = chat_completion.choices[0].message
        tool_calls = response_message.tool_calls

        if tool_calls:
            messages.append(response_message)
            
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                if func_name == "perform_web_search":
                    query = func_args.get("query")
                    web_data = perform_web_search(query)
                    messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": web_data})

                elif func_name == "navigate_to":
                    destination = func_args.get("destination")
                    return ChatResponse(reply="Processing request, boss.", action="OPEN_MAPS", action_data1=destination)
                
                elif func_name == "save_to_memory":
                    key = func_args.get("info_key")
                    val = func_args.get("info_value")
                    return ChatResponse(reply="Processing request, boss.", action="SAVE_MEMORY", action_data1=key, action_data2=val)
                    
                elif func_name == "control_device":
                    action_type = func_args.get("action")
                    app_pkg = func_args.get("app_package", "")
                    return ChatResponse(reply="Processing request, boss.", action="CONTROL_DEVICE", action_data1=action_type, action_data2=app_pkg)
                
                elif func_name == "communicate":
                    method = func_args.get("method")
                    name = func_args.get("contact_name")
                    msg = func_args.get("message_text", "")
                    return ChatResponse(reply="Processing request, boss.", action="COMMUNICATE", action_data1=method, action_data2=name, action_data3=msg)
                    
                elif func_name == "get_live_weather":
                    location = func_args.get("location")
                    weather_data = get_live_weather(location)
                    messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": weather_data})

            # Agar Web Search ya Weather hua hai, toh LLM se final answer maango
            if any(tc.function.name in ["perform_web_search", "get_live_weather"] for tc in tool_calls):
                second_response = await client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages
                )
                reply_text = second_response.choices[0].message.content
                return ChatResponse(reply=reply_text)

        reply_text = response_message.content
        logger.info("✅ Success from Groq Chat")
        return ChatResponse(reply=reply_text)

    except Exception as e:
        logger.error(f"💥 CRITICAL CHAT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Saarthi Brain Error: {str(e)}")

# ==========================================
# 👂 THE EARS: Audio Transcription Endpoint
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
                prompt="Haan boss, bataiye. Main bilkul theek hoon. Youtube open kar do.", 
                response_format="json"
            )
        
        transcribed_text = transcription.text.strip()
        os.remove(temp_file_path)
        return {"text": transcribed_text}

    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Saarthi Ears Error: {str(e)}")
