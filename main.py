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

# Version Updated: YouTube Strict Search Fix added
app = FastAPI(title="Saarthi AI Core", version="27.1.0") 

# API Keys
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")

client = AsyncGroq(api_key=api_key)
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# ==========================================
# 🧠 MONGODB CLOUD BRAIN SETUP
# ==========================================
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

# 🚀 CONTINUOUS CHAT MEMORY
global_chat_history = []
last_bot_reply = "" 

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = """You are Saarthi (Jarvis), an ultra-intelligent, highly empathetic AI assistant.
    CRITICAL RULES:
    1. LANGUAGE & TRANSLATOR: Converse naturally in 'Hinglish'. NEVER use Devanagari.
    2. AUTO-CORRECT: Use High IQ to auto-correct broken voice-to-text.
    3. IQ & EQ: IQ of 250+. Address the user as 'Boss'.
    4. VOICE FOCUS: The user's voice is the ONLY authority."""
    android_memory: str = "" 

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          
    action_data1: str = ""        
    action_data2: str = ""        
    action_data3: str = ""        

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (V27.1: YouTube Song Fix Active)!"}

# ==========================================
# ⚙️ SAARTHI'S NATIVE TOOLS (Powers)
# ==========================================

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
            "description": "Search the internet for real-time information.",
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
            "name": "save_to_memory",
            "description": "Save user preferences to the Cloud Brain.",
            "parameters": {"type": "object", "properties": {"info_key": {"type": "string"}, "info_value": {"type": "string"}}, "required": ["info_key", "info_value"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_device",
            "description": "Control hardware, apps, UI, Alarms, Timers, and Screen Reading.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string", 
                        "enum": ["open_app", "close_app", "youtube_search", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "volume_up", "volume_down", "volume_mute", "volume_unmute", "brightness_up", "brightness_down", "bluetooth_settings", "volume_silent", "volume_ring", "auto_rotate_on", "auto_rotate_off", "open_calculator", "accept_call", "reject_call", "open_camera", "open_video_camera", "open_audio_recorder", "copy_to_clipboard", "direct_type", "click_button", "system_nav", "read_notifications", "clear_chat", "set_alarm", "set_timer", "read_screen"]
                    },
                    "app_package": {
                        "type": "string", 
                        "description": "App name for 'open_app'. EXACT SEARCH QUERY for 'youtube_search' (e.g. 'Baaghi 4 songs' or 'KGF movie'). Time for 'set_alarm' (e.g. '06:00'). Minutes for 'set_timer' (e.g. '10')."
                    },
                    "target_app": {
                        "type": "string",
                        "description": "Target app if direct typing. Or specific context."
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
        logger.warning("Echo Detected! Ignoring self-generated speech.")
        return ChatResponse(reply="...", action="NONE") 
        
    try:
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone).strftime('%A, %d %B %Y, %I:%M %p')
        
        cloud_memory = get_cloud_memory()
        memory_context = f"\n[JARVIS PERMANENT CLOUD MEMORY:\n{cloud_memory}]\n[LIVE ANDROID GPS/LOCATION: {request.android_memory}]"
        
        # 🚀 FIX: YouTube Search Guide updated!
        router_system_prompt = f"""You are a smart, silent tool-routing AI. NEVER use XML tags.
        INTENT GUIDE:
        1. Notifications: "message aaya hai?" -> 'read_notifications'.
        2. Screen Reading: "screen par kya likha hai" -> 'read_screen'.
        3. Alarms/Timers: "alarm lagao 6 baje ka" -> 'set_alarm' with '06:00'. "10 minute ka timer" -> 'set_timer' with '10'.
        4. UI Clicks: "send dabao" -> 'click_button', pass button text.
        5. Navigation: "back aao" -> 'system_nav' with 'back'.
        6. Typing: "yeh type karo [text]" -> 'direct_type', pass text in 'app_package'.
        7. Calls/Msgs: "mummy ko call lagao" -> use 'communicate' tool.
        8. Chat Reset: "new chat" -> 'clear_chat'.
        9. YouTube: "baaghi 4 ke gaane lagao" -> 'youtube_search'. DO NOT REMOVE the word "song" or "gaana". Pass EXACT full query like "Baaghi 4 songs" in 'app_package'.
        10. Realtime Data - Time: {live_time}"""
        
        router_messages = [{"role": "system", "content": router_system_prompt}, {"role": "user", "content": request.message}]
        
        chat_completion_router = await client.chat.completions.create(
            messages=router_messages, model="llama-3.1-8b-instant", tools=saarthi_tools, tool_choice="auto", temperature=0.0, max_tokens=1024,
        )
        
        response_message = chat_completion_router.choices[0].message
        tool_calls = response_message.tool_calls

        persona_rules = """
        PERSONA RULES:
        - Helper Mode: Always be crisp, direct, and refer to user as Boss.
        """
        
        creative_system_content = f"{request.system_prompt}\n{persona_rules}\nREALTIME DATA:\n- Time: {live_time} {memory_context}"
        creative_messages = [{"role": "system", "content": creative_system_content}]
        
        for msg in global_chat_history[-10:]:
            creative_messages.append(msg)
            
        creative_messages.append({"role": "user", "content": request.message})

        if tool_calls:
            creative_messages.append(response_message)
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                
                if func_name == "perform_web_search":
                    web_data = perform_web_search(func_args.get("query"))
                    creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": web_data})
                
                elif func_name == "get_live_weather":
                    weather_data = get_live_weather(func_args.get("location"))
                    creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": weather_data})

                elif func_name == "save_to_memory":
                    k = func_args.get("info_key")
                    v = func_args.get("info_value")
                    try:
                        memory_col.update_one({"key": k}, {"$set": {"value": v}}, upsert=True)
                        success_msg = f"Cloud Brain Updated: '{k}' is now '{v}'."
                    except Exception as e:
                        success_msg = "Database Error."
                    creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": success_msg})
                
                elif func_name == "control_device":
                    action = func_args.get("action")
                    if action == "clear_chat":
                        global_chat_history.clear()
                        return ChatResponse(reply="Boss, purani saari baatein delete kar di hain. Nayi shuruwat karte hain!", action="NONE")
                    
                    target_app = func_args.get("target_app", "NONE")
                    return ChatResponse(reply="Processing request, boss.", action="CONTROL_DEVICE", action_data1=action, action_data2=func_args.get("app_package", ""), action_data3=target_app)
                
                elif func_name == "communicate":
                    return ChatResponse(reply="Processing request, boss.", action="COMMUNICATE", action_data1=func_args.get("method"), action_data2=func_args.get("contact_name"), action_data3=func_args.get("message_text", ""))

            if any(tc.function.name in ["perform_web_search", "get_live_weather", "save_to_memory"] for tc in tool_calls):
                final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
                reply_text = final_response.choices[0].message.content
                global_chat_history.extend([{"role": "user", "content": request.message}, {"role": "assistant", "content": reply_text}])
                last_bot_reply = reply_text
                return ChatResponse(reply=reply_text)

        final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
        reply_text = final_response.choices[0].message.content
        
        global_chat_history.extend([{"role": "user", "content": request.message}, {"role": "assistant", "content": reply_text}])
        last_bot_reply = reply_text
        return ChatResponse(reply=reply_text)

    except Exception as e:
        logger.error(f"💥 CRITICAL CHAT ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Saarthi Brain Error: {str(e)}")

# ==========================================
# 👁️ VISION AI ENDPOINT (JARVIS KI AANKHEIN)
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
                        {"type": "text", "text": prompt + " Answer like Jarvis, calling user Boss."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            temperature=0.5,
            max_tokens=500,
        )
        return {"reply": chat_completion.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Saarthi Eyes Error: {str(e)}")

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
        hallucinations = ["Thank you for watching.", "Thanks for watching", "Thank you.", "Subscribe", "Please subscribe", "watching."]
        for bad_word in hallucinations:
            raw_text = re.sub(re.escape(bad_word), "", raw_text, flags=re.IGNORECASE).strip()
            
        if not raw_text:
            return {"text": "[error]"}
            
        return {"text": raw_text}
        
    except Exception as e:
        if os.path.exists(temp_file_path): os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=f"Saarthi Ears Error: {str(e)}")
