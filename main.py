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
from pymongo import MongoClient

# Logs Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Version Updated: Continuous Chat, Personas (Chef, Doctor, etc), Calls, Camera & Dictation
app = FastAPI(title="Saarthi AI Core", version="24.0.0") 

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
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["saarthi_db"]
    memory_col = db["permanent_memory"]
    mongo_client.admin.command('ping') 
    logger.info("🟢 MongoDB Cloud Brain Connected Successfully!")
except Exception as e:
    logger.error(f"🔴 MongoDB Connection Error: {e}")

def get_cloud_memory():
    """Database se saari memory nikal kar string banata hai"""
    try:
        memories = memory_col.find({})
        mem_list = [f"- {m['key']}: {m['value']}" for m in memories]
        return "\n".join(mem_list) if mem_list else "Abhi tak koi memory save nahi hui hai."
    except Exception as e:
        return "Database error."

# 🚀 CONTINUOUS CHAT MEMORY (Short-term memory)
global_chat_history = []

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = """You are Saarthi (Jarvis), an ultra-intelligent, highly empathetic AI assistant.
    CRITICAL RULES:
    1. LANGUAGE & TRANSLATOR: Converse naturally in 'Hinglish' (Hindi words in English alphabet). NEVER use Devanagari or Urdu. IF the user asks you to translate something, act as a Real-Time Translator and provide the exact translation in Hinglish.
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
    return {"status": "🟢 Saarthi AI is Online (V24: Personas + Continuous Chat + Call/Camera Controls)!"}

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
            "description": "Save important user preferences, locations, or facts permanently to the Cloud Brain.",
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
                        # 🚀 NEW ACTIONS ADDED HERE
                        "enum": ["open_app", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "close_app", "volume_up", "volume_down", "volume_mute", "volume_unmute", "youtube_search", "brightness_up", "brightness_down", "bluetooth_settings", "volume_silent", "volume_ring", "auto_rotate_on", "auto_rotate_off", "open_calculator", "accept_call", "reject_call", "open_camera", "open_video_camera", "open_audio_recorder", "copy_to_clipboard", "clear_chat"]
                    },
                    "app_package": {
                        "type": "string", 
                        "description": "If 'open_app', provide ONLY the app's COMMON NAME. If 'copy_to_clipboard', provide the EXACT TEXT the user wants you to copy/type."
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
    global global_chat_history
    try:
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone).strftime('%A, %d %B %Y, %I:%M %p')
        
        cloud_memory = get_cloud_memory()
        memory_context = f"\n[JARVIS PERMANENT CLOUD MEMORY:\n{cloud_memory}]\n[LIVE ANDROID GPS/LOCATION: {request.android_memory}]"
        
        # 🚀 1. ROUTER PROMPT (For 8B Model to pick tools)
        router_system_prompt = f"""You are a smart, silent tool-routing AI. AUTO-CORRECT spelling internally and map to the correct tool. NEVER use XML tags.
        INTENT GUIDE:
        1. Calls: "call uthao", "answer call" -> 'accept_call'. "call kaato", "reject" -> 'reject_call'.
        2. Media Capture: "photo khicho", "camera open" -> 'open_camera'. "video record" -> 'open_video_camera'. "voice record" -> 'open_audio_recorder'.
        3. Dictation/Typing: "yeh text likho [text]", "type karo [text]", "copy karo [text]" -> 'copy_to_clipboard' and pass the text in 'app_package'.
        4. Chat Reset: "new chat", "purani baat bhul jao", "restart" -> 'clear_chat'.
        5. App Opening: "khol", "open", "chalao" + [App Name] -> 'open_app'.
        6. Close All: "sabhi app band karo", "close all apps", "clear screen" -> 'close_app'.
        7. YouTube: "song", "gaana", "movie", "video" -> 'youtube_search'. Include "song" if requested.
        8. Memory: If user asks you to remember something, use 'save_to_memory'.
        9. Translation or Persona Request: DO NOT invoke tools. Let main AI handle it.
        10. Realtime Data - Time: {live_time}"""
        
        router_messages = [{"role": "system", "content": router_system_prompt}, {"role": "user", "content": request.message}]
        
        chat_completion_router = await client.chat.completions.create(
            messages=router_messages, model="llama-3.1-8b-instant", tools=saarthi_tools, tool_choice="auto", temperature=0.0, max_tokens=1024,
        )
        
        response_message = chat_completion_router.choices[0].message
        tool_calls = response_message.tool_calls

        # 🚀 2. CREATIVE PROMPT (For 70B Model to talk) + CONTINUOUS CHAT HISTORY + PERSONAS
        persona_rules = """
        PERSONA RULES (Adopt completely if requested by the user):
        - Teacher Mode: Explain simply with examples.
        - Doctor Mode: Ask symptoms, suggest home remedies, but advise seeing a real doctor.
        - Master Chef Mode: Ask for ingredients, give step-by-step recipes, wait for user to say "next step".
        - Bhav-Tau (Bargaining) Mode: Give solid tips on how to reduce price, act like a smart Indian shopper.
        - Gadar/Angry Mode: Speak with heavy attitude, aggressive and dramatic tone.
        - Love Guru Mode: Give romantic, poetic, and deep relationship advice.
        - Helper/Engineering Mode: Give practical, technical, and precise step-by-step solutions.
        """
        
        creative_system_content = f"{request.system_prompt}\n{persona_rules}\nREALTIME DATA:\n- Time: {live_time} {memory_context}"
        creative_messages = [{"role": "system", "content": creative_system_content}]
        
        # Add last 10 messages for context (Short-Term Memory)
        for msg in global_chat_history[-10:]:
            creative_messages.append(msg)
            
        creative_messages.append({"role": "user", "content": request.message})

        # 🚀 3. EXECUTE TOOLS IF ANY
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
                        success_msg = f"Database Error."
                    creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": success_msg})

                elif func_name == "navigate_to":
                    return ChatResponse(reply="Processing request, boss.", action="OPEN_MAPS", action_data1=func_args.get("destination"))
                
                elif func_name == "control_device":
                    action = func_args.get("action")
                    # 🚀 CLEAR CHAT TOOL LOGIC
                    if action == "clear_chat":
                        global_chat_history.clear()
                        return ChatResponse(reply="Boss, purani saari baatein memory se delete kar di hain. Nayi shuruwat karte hain!", action="NONE")
                        
                    return ChatResponse(reply="Processing request, boss.", action="CONTROL_DEVICE", action_data1=action, action_data2=func_args.get("app_package", ""))
                
                elif func_name == "communicate":
                    return ChatResponse(reply="Processing request, boss.", action="COMMUNICATE", action_data1=func_args.get("method"), action_data2=func_args.get("contact_name"), action_data3=func_args.get("message_text", ""))

            # Generate final response after tools (Web, Weather, Memory)
            if any(tc.function.name in ["perform_web_search", "get_live_weather", "save_to_memory"] for tc in tool_calls):
                final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
                reply_text = final_response.choices[0].message.content
                
                # Save to history
                global_chat_history.extend([{"role": "user", "content": request.message}, {"role": "assistant", "content": reply_text}])
                return ChatResponse(reply=reply_text)

        # Generate final response if no tools needed (General Chat)
        final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
        reply_text = final_response.choices[0].message.content
        
        # 🚀 Save conversation to history so Jarvis remembers context!
        global_chat_history.extend([{"role": "user", "content": request.message}, {"role": "assistant", "content": reply_text}])
        
        logger.info("✅ Success from Groq Chat (70B)")
        return ChatResponse(reply=reply_text)

    except Exception as e:
        logger.error(f"💥 CRITICAL CHAT ERROR: {str(e)}")
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
