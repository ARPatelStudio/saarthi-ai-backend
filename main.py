import os
import logging
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

app = FastAPI(title="Saarthi AI Core", version="35.5.0") 

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")

client = AsyncGroq(api_key=api_key)
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

MONGO_URI = "mongodb+srv://favouritegamer192_db_user:pjt6UStm6rB3ekEv@saarthi.sfsuxij.mongodb.net/?appName=Saarthi"
try:
    mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = mongo_client["saarthi_db"]
    location_col = db["location_history"] 
    memory_col = db["permanent_memory"]
    pc_col = db["device_commands"] # 🚀 NAYA ADD KIYA: PC commands store karne ke liye
    mongo_client.admin.command('ping') 
except Exception as e:
    logger.error(f"🔴 MongoDB Connection Error: {e}")

global_chat_history = []
last_bot_reply = "" 

class ChatRequest(BaseModel):
    message: str
    android_memory: str = "" 

class LocationTrackRequest(BaseModel):
    latitude: float
    longitude: float

class MemoryRequest(BaseModel):
    key: str
    value: str

# 🚀 NAYA MODEL ADD KIYA: PC Command request handle karne ke liye
class PCCommandReq(BaseModel):
    target: str
    command: str
    status: str = "pending"

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          
    action_data1: str = ""        
    action_data2: str = ""        
    action_data3: str = ""        

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (V35.5.0: Memory Gateway Active)!"}

# =======================================================
# 🚀 NAYE ENDPOINTS (ANDROID SE MEMORY SAVE AUR FETCH KARNE KE LIYE)
# =======================================================
@app.post("/api/save_memory")
async def save_memory(req: MemoryRequest):
    try:
        # Puraani memory update karega ya nayi bana dega
        memory_col.update_one({"key": req.key}, {"$set": {"value": req.value}}, upsert=True)
        return {"status": "Memory Saved Boss!"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/get_memory")
async def get_memory():
    try:
        # MongoDB se saari yaadein nikal kar Android ko dega
        records = list(memory_col.find({}, {"_id": 0}))
        mem_str = "\n".join([f"- {r['key']}: {r['value']}" for r in records])
        return {"memory": mem_str}
    except Exception as e:
        return {"memory": ""}

# =======================================================
# 🚀 PC CONTROLLER ENDPOINT (NAYA RASTA)
# =======================================================
@app.post("/api/pc_command")
async def pc_command(req: PCCommandReq):
    try:
        # Request MongoDB me jayegi jahan se PC Script ise catch karegi
        pc_col.insert_one({
            "target": req.target,
            "command": req.command,
            "status": req.status,
            "timestamp": datetime.datetime.now()
        })
        return {"success": True, "message": "PC Command queued!"}
    except Exception as e:
        return {"error": str(e)}

# =======================================================
# --- TRACKING & WEATHER LOGIC ---
# =======================================================
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

        # 🚀 AUTO-CLEANUP SHIELD: Database ko kabhi full nahi hone dega!
        # Agar locations 10,000 se zyada ho jayein, toh sabse purani wali delete kar do
        if location_col.count_documents({}) > 10000:
            oldest_record = location_col.find().sort("_id", 1).limit(1)[0]
            location_col.delete_one({"_id": oldest_record["_id"]})
        
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
    {"type": "function", "function": {"name": "perform_web_search", "description": "Search the internet.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_live_weather", "description": "Fetch real-time weather.", "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}}},
    {"type": "function", "function": {"name": "query_location_history", "description": "Find out where the user was.", "parameters": {"type": "object", "properties": {"date_query": {"type": "string"}}, "required": ["date_query"]}}},
    {"type": "function", "function": {"name": "control_device", "description": "Control hardware, apps, UI, Media, Volume, Vision.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["open_app", "close_app", "youtube_search", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "open_camera", "open_scanner", "set_alarm", "set_timer", "bluetooth_settings", "gps_settings", "quick_share", "vision_scanning", "scan_vision"]}, "app_package": {"type": "string"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "communicate", "description": "Make a phone call or send a WhatsApp.", "parameters": {"type": "object", "properties": {"method": {"type": "string", "enum": ["call", "whatsapp"]}, "contact_name": {"type": "string"}, "message_text": {"type": "string"}}, "required": ["method", "contact_name"]}}}
]

@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    return ChatResponse(reply="I am now handled by Android Native Engine.", action="NONE")
