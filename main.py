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

# Logs Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

load_dotenv()

# Version Updated for Phase 2: Communication Hub
app = FastAPI(title="Saarthi AI Core", version="5.0.0") 

# API Keys
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")

client = AsyncGroq(api_key=api_key)

# ⚠️ Render par 'Environment Variables' mein WEATHER_API_KEY ke naam se apni OpenWeather key daal dena
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = "You are Saarthi, a smart AI assistant. Response should be in Hinglish."
    android_memory: str = "" # Android apni memory bhejne ke liye use karega

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          # Signal for Android
    action_data1: str = ""        # Extra data 1 (Method: call/whatsapp)
    action_data2: str = ""        # Extra data 2 (Contact Name)
    action_data3: str = ""        # 🚀 NAYA: WhatsApp message text ke liye

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (Audio + Weather + Maps + Device Control + Comm Hub Ready)!"}

# ==========================================
# ⚙️ SAARTHI'S NATIVE TOOLS (Powers)
# ==========================================

# 1. WEATHER API TOOL
def get_live_weather(location: str):
    logger.info(f"☁️ Fetching live weather for: {location}")
    if not WEATHER_API_KEY:
        return f"{location} ka live mausam abhi nahi bata sakta, API key missing hai."
    
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={WEATHER_API_KEY}&units=metric&lang=hi"
        response = requests.get(url).json()
        
        if response.get("cod") != 200:
            return f"Maaf karna, mujhe {location} ka mausam nahi mil paya."
            
        temp = response['main']['temp']
        desc = response['weather'][0]['description']
        return f"Live Data: {location} ka temperature {temp}°C hai aur mausam '{desc}' hai."
    except Exception as e:
        logger.error(f"Weather API Error: {e}")
        return "Weather API me kuch issue aaya hai."

# Tool Descriptions for Groq
saarthi_tools = [
    {
        "type": "function",
        "function": {
            "name": "get_live_weather",
            "description": "Fetch real-time weather and temperature for a city. Use this if the user asks for weather, OR to proactively check weather before the user travels to a destination.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string", "description": "City name, e.g., Indore, Bhopal"}},
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "Trigger this when the user wants to go somewhere, needs directions, or asks to open maps for a destination.",
            "parameters": {
                "type": "object",
                "properties": {"destination": {"type": "string", "description": "The exact place or city the user wants to go to."}},
                "required": ["destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_memory",
            "description": "Use this to REMEMBER personal information the user tells you (e.g., where they kept their keys, their friend's birthday).",
            "parameters": {
                "type": "object",
                "properties": {
                    "info_key": {"type": "string", "description": "What to remember (e.g., bike keys, anniversary)"},
                    "info_value": {"type": "string", "description": "The detail (e.g., in the upper drawer, 15th August)"}
                },
                "required": ["info_key", "info_value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_device",
            "description": "Control the Android phone's hardware, media, or open/close applications.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string", 
                        "enum": ["open_app", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "close_app"],
                        "description": "What to do: open/close an app, turn flashlight on/off, or control media playback."
                    },
                    "app_package": {
                        "type": "string", 
                        "description": "If opening an app, guess the exact Android package name (e.g., com.whatsapp, com.google.android.youtube, com.instagram.android). Leave empty for others."
                    }
                },
                "required": ["action"]
            }
        }
    },
    # 🚀 NAYA TOOL: COMMUNICATION HUB (Call & WhatsApp)
    {
        "type": "function",
        "function": {
            "name": "communicate",
            "description": "Make a phone call or send a WhatsApp message to a specific contact.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string", 
                        "enum": ["call", "whatsapp"],
                        "description": "Whether to make a phone call or send a WhatsApp message."
                    },
                    "contact_name": {
                        "type": "string", 
                        "description": "Name of the person to contact (e.g., Rahul, Mummy, Papa)."
                    },
                    "message_text": {
                        "type": "string", 
                        "description": "The content of the message to send. Leave completely empty if making a phone call."
                    }
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
        
        # 1. Live Time aur Android Memory nikalo
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone).strftime('%A, %d %B %Y, %I:%M %p')
        memory_context = f"\n[User's Saved Memory: {request.android_memory}]" if request.android_memory else ""
        
        dynamic_system_prompt = f"""
        {request.system_prompt}
        REALTIME DATA:
        - Current Time & Date: {live_time}
        - User's Location: Indore, Madhya Pradesh, India {memory_context}
        RULE: If the user is travelling to a new city, briefly mention the weather there using the weather tool, then trigger navigation.
        """
        
        messages = [
            {"role": "system", "content": dynamic_system_prompt},
            {"role": "user", "content": request.message}
        ]
        
        # 2. Ask Groq if it needs to use any tools
        chat_completion = await client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant", 
            tools=saarthi_tools,
            tool_choice="auto",
            temperature=0.7,
            max_tokens=1024,
        )
        
        response_message = chat_completion.choices[0].message
        tool_calls = response_message.tool_calls

        # 3. IF GROQ DECIDES TO USE TOOLS
        if tool_calls:
            messages.append(response_message)
            
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                # ACTION: OPEN GOOGLE MAPS
                if func_name == "navigate_to":
                    destination = func_args.get("destination")
                    logger.info(f"🗺️ Sending Maps Signal for: {destination}")
                    return ChatResponse(
                        reply=f"Chaliye boss, main Google Maps par {destination} ka rasta laga raha hoon.",
                        action="OPEN_MAPS",
                        action_data1=destination
                    )
                
                # ACTION: SAVE MEMORY
                elif func_name == "save_to_memory":
                    key = func_args.get("info_key")
                    val = func_args.get("info_value")
                    logger.info(f"🧠 Sending Memory Signal: {key} -> {val}")
                    return ChatResponse(
                        reply=f"Done boss, maine dhyan mein rakh liya hai ki {key} {val}.",
                        action="SAVE_MEMORY",
                        action_data1=key,
                        action_data2=val
                    )
                    
                # ACTION: CONTROL DEVICE (Flashlight / Apps / Media)
                elif func_name == "control_device":
                    action_type = func_args.get("action")
                    app_pkg = func_args.get("app_package", "")
                    
                    logger.info(f"📱 Device Control Signal: {action_type} -> {app_pkg}")
                    
                    if action_type == "flashlight_on":
                        reply_msg = "Theek hai boss, light on kar di hai."
                    elif action_type == "flashlight_off":
                        reply_msg = "Theek hai boss, light band kar di."
                    elif action_type == "open_app":
                        reply_msg = "Lijiye boss, app khol raha hoon."
                    elif action_type in ["media_play", "media_pause", "media_stop"]:
                        reply_msg = "Theek hai boss."
                    elif action_type == "close_app":
                        reply_msg = "App hata di hai boss."
                    else:
                        reply_msg = "Kaam ho gaya boss."

                    return ChatResponse(
                        reply=reply_msg,
                        action="CONTROL_DEVICE",
                        action_data1=action_type,
                        action_data2=app_pkg
                    )
                
                # 🚀 ACTION: COMMUNICATE (Calls & WhatsApp)
                elif func_name == "communicate":
                    method = func_args.get("method")
                    name = func_args.get("contact_name")
                    msg = func_args.get("message_text", "")
                    
                    logger.info(f"📞 Comm Signal: {method} to {name} | Msg: {msg}")
                    return ChatResponse(
                        reply="Process kar raha hoon boss.", # Note: UI handles final 'Kam ho gaya' audio.
                        action="COMMUNICATE", 
                        action_data1=method, 
                        action_data2=name,
                        action_data3=msg
                    )
                    
                # ACTION: FETCH WEATHER (Background process)
                elif func_name == "get_live_weather":
                    location = func_args.get("location")
                    weather_data = get_live_weather(location)
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": func_name,
                        "content": weather_data,
                    })

            # Agar Weather tool call hua tha, toh Groq ko dubara bulakar final answer banwao
            if any(tc.function.name == "get_live_weather" for tc in tool_calls):
                second_response = await client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=messages
                )
                reply_text = second_response.choices[0].message.content
                return ChatResponse(reply=reply_text)

        # 4. NORMAL CHAT (No Tools Needed)
        reply_text = response_message.content
        logger.info("✅ Success from Groq Chat")
        return ChatResponse(reply=reply_text)

    except Exception as e:
        logger.error(f"💥 CRITICAL CHAT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Saarthi Brain Error: {str(e)}")

# ==========================================
# 👂 THE EARS: Audio Transcription Endpoint (Unchanged & Safe)
# ==========================================
@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    temp_file_path = ""
    try:
        logger.info(f"🎤 Received Audio File: {file.filename}")
        contents = await file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".m4a") as temp_audio:
            temp_audio.write(contents)
            temp_file_path = temp_audio.name

        with open(temp_file_path, "rb") as audio_file:
            transcription = await client.audio.transcriptions.create(
                file=(file.filename, audio_file.read()),
                model="whisper-large-v3", 
                response_format="json"
            )
        
        transcribed_text = transcription.text.strip()
        os.remove(temp_file_path)
        return {"text": transcribed_text}

    except Exception as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Saarthi Ears Error: {str(e)}")
