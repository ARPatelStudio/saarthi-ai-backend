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

# Version Updated: V32.0.0 - Continuous Memory & Friend Chat Mode
app = FastAPI(title="Saarthi AI Core", version="32.0.0") 

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
    location_col = db["location_history"] 
    mongo_client.admin.command('ping') 
    logger.info("🟢 MongoDB Cloud Brain Connected Successfully!")
except Exception as e:
    logger.error(f"🔴 MongoDB Connection Error: {e}")

# 🚀 MEMORY FIX: Ab yeh history actually use hogi
global_chat_history = []
last_bot_reply = "" 

class ChatRequest(BaseModel):
    message: str
    android_memory: str = "" 

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          
    action_data1: str = ""        
    action_data2: str = ""        
    action_data3: str = ""        

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (V32.0.0: Friend Mode & Memory Active)!"}

@app.post("/api/track_location")
async def track_location(req: LocationTrackRequest):
    try:
        if not WEATHER_API_KEY: return {"status": "No Weather API"}
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={req.latitude}&lon={req.longitude}&appid={WEATHER_API_KEY}&units=metric&lang=hi"
        weather_res = requests.get(url).json()
        if weather_res.get("cod") != 200: return {"status": "Weather Error"}
        city_name = weather_res.get("name", "Unknown Area")
        weather_desc = weather_res["weather"][0]["description"].lower()
        weather_id = weather_res["weather"][0]["id"]
        
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone)
        
        location_col.insert_one({
            "date": live_time.strftime('%Y-%m-%d'),
            "time": live_time.strftime('%I:%M %p'),
            "latitude": req.latitude,
            "longitude": req.longitude,
            "city": city_name,
            "weather": weather_desc
        })
        
        is_bad_weather = (200 <= weather_id <= 299) or (500 <= weather_id <= 599) or (600 <= weather_id <= 699) or weather_id == 781
        if is_bad_weather:
            return {"alert": f"Boss alert! Aap jahan hain ({city_name}), wahan {weather_desc} hone ki sambhavna hai. Kripya dhyan rakhein!"}
            
        return {"status": "Saved safely"}
    except Exception as e: return {"error": str(e)}

def query_location_history(date_query: str):
    try:
        ist_timezone = pytz.timezone('Asia/Kolkata')
        if date_query.lower() in ["today", "aaj"]:
            target_date = datetime.datetime.now(ist_timezone).strftime('%Y-%m-%d')
        elif date_query.lower() in ["yesterday", "kal"]:
            target_date = (datetime.datetime.now(ist_timezone) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        else: target_date = date_query 
            
        records = list(location_col.find({"date": {"$regex": target_date}}).sort("_id", -1).limit(10))
        if not records: return f"Boss, mere paas {target_date} ki koi location history nahi hai."
            
        history_text = f"Location history for {target_date}:\n"
        for r in records: history_text += f"- At {r['time']}, you were near {r['city']}. Weather was {r['weather']}.\n"
        return history_text
    except Exception as e: return "Database check karne me issue hua boss."

def perform_web_search(query: str):
    try:
        results = DDGS().text(query, max_results=2)
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
            "name": "query_location_history",
            "description": "Find out where the user was on a specific date or time.",
            "parameters": {"type": "object", "properties": {"date_query": {"type": "string"}}, "required": ["date_query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_device",
            "description": "Control hardware, apps, UI, Media, Volume, Vision, and Avatar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open_app", "close_app", "youtube_search", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "open_camera", "open_scanner", "set_alarm", "set_timer", "bluetooth_settings", "gps_settings", "quick_share", "vision_scanning", "scan_vision", "volume_up", "volume_down", "volume_mute", "volume_unmute", "volume_set", "open_avatar", "close_avatar"]},
                    "app_package": {"type": "string"}
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
            "parameters": {"type": "object", "properties": {"method": {"type": "string", "enum": ["call", "whatsapp"]}, "contact_name": {"type": "string"}, "message_text": {"type": "string"}}, "required": ["method", "contact_name"]}
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
        
        router_system_prompt = f"""You are a smart tool-routing AI. Choose ONE tool ONLY IF asked to perform a physical task on the phone or search the web. IF THE USER IS JUST CHATTING/TALKING NORMALLY, DO NOT SELECT ANY TOOL.
        INTENT GUIDE:
        1. Avatar Mode: "samne aao", "avatar dikhao" -> 'open_avatar'. "wapas jao", "avatar band karo" -> 'close_avatar'.
        2. Location History: "aaj main kahan tha" -> 'query_location_history'.
        3. Apps/Settings: "youtube kholo", "bluetooth on", "photo kheecho" -> 'open_app', 'bluetooth_settings', 'open_camera'.
        """
        
        router_messages = [{"role": "system", "content": router_system_prompt}, {"role": "user", "content": request.message}]
        
        chat_completion_router = await client.chat.completions.create(
            messages=router_messages, model="llama-3.1-8b-instant", tools=saarthi_tools, tool_choice="auto", temperature=0.0, max_tokens=512, parallel_tool_calls=False
        )
        
        response_message = chat_completion_router.choices[0].message
        tool_calls = response_message.tool_calls

        # 🚀 NEW: Friend Persona & Context Memory
        friend_prompt = """Tumhara naam Saarthi (ya Jarvis) hai. Tum ek ultra-intelligent AI aur mere sabse acche dost (friend) ho. 
        Tum hamesha Hinglish mein natural, friendly aur casual tone mein baat karte ho. 
        Agar main tumse normal baat karu (jaise haal-chaal poochna, joke sunna, ya advice lena), toh ek sacche dost ki tarah jawab dena, machine ki tarah nahi."""
        
        creative_messages = [{"role": "system", "content": f"{friend_prompt}\nREALTIME DATA:\n- Time: {live_time} {memory_context}"}]
        
        # Purani baatein yaad rakhne ke liye pichle 10 messages add kar rahe hain
        creative_messages.extend(global_chat_history[-10:])
        creative_messages.append({"role": "user", "content": request.message})

        final_reply_text = ""
        action_type = "NONE"
        act_d1 = ""
        act_d2 = ""

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
                final_reply_text = final_response.choices[0].message.content
            
            elif func_name == "get_live_weather":
                weather_data = get_live_weather(func_args.get("location", "India"))
                creative_messages.append(response_message)
                creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": weather_data})
                final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
                final_reply_text = final_response.choices[0].message.content
                
            elif func_name == "query_location_history":
                history_data = query_location_history(func_args.get("date_query", "today"))
                creative_messages.append(response_message)
                creative_messages.append({"tool_call_id": tool_call.id, "role": "tool", "name": func_name, "content": history_data})
                final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
                final_reply_text = final_response.choices[0].message.content
            
            elif func_name == "control_device":
                action = func_args.get("action")
                if action in ["vision_scanning", "scan_vision"]: action = "open_scanner"
                
                if action == "open_avatar": return ChatResponse(reply="Aa raha hoon boss!", action="CONTROL_DEVICE", action_data1="open_avatar")
                elif action == "close_avatar": return ChatResponse(reply="Main wapas background mein jaa raha hoon boss.", action="CONTROL_DEVICE", action_data1="close_avatar")

                final_reply_text = "Done boss."
                action_type = "CONTROL_DEVICE"
                act_d1 = action
                act_d2 = func_args.get("app_package", "")
            
            elif func_name == "communicate":
                final_reply_text = "Processing request, boss."
                action_type = "COMMUNICATE"
                act_d1 = func_args.get("method", "call")
                act_d2 = func_args.get("contact_name", "")

        else:
            # 🚀 FRIEND CHAT MODE (Jab koi tool trigger na ho)
            final_response = await client.chat.completions.create(model="llama-3.3-70b-versatile", messages=creative_messages, temperature=0.7)
            final_reply_text = final_response.choices[0].message.content

        # Save conversation to memory
        global_chat_history.append({"role": "user", "content": request.message})
        global_chat_history.append({"role": "assistant", "content": final_reply_text})
        
        last_bot_reply = final_reply_text
        return ChatResponse(reply=final_reply_text, action=action_type, action_data1=act_d1, action_data2=act_d2)

    except Exception as e:
        return ChatResponse(reply="Boss, thodi technical dikkat aayi.", action="NONE")

@app.post("/api/vision")
async def vision_analysis(file: UploadFile = File(...), prompt: str = Form("Is photo mein kya hai? Detail mein Hindi/Hinglish mein batao.")):
    try:
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
        chat_completion = await client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt + " Answer in short 2 lines."}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
            temperature=0.5, max_tokens=300,
        )
        return {"reply": chat_completion.choices[0].message.content}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

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
                file=(file.filename, audio_file.read()), model="whisper-large-v3", language="hi", prompt="Haan boss, bataiye.", response_format="json"
            )
        os.remove(temp_file_path)
        raw_text = transcription.text.strip()
        for bad_word in ["Thank you for watching.", "Thanks for watching", "Thank you.", "Subscribe", "watching."]:
            raw_text = re.sub(re.escape(bad_word), "", raw_text, flags=re.IGNORECASE).strip()
        if not raw_text or len(raw_text) < 3: return {"text": "[error]"}
        return {"text": raw_text}
    except Exception as e:
        if os.path.exists(temp_file_path): os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=str(e))
