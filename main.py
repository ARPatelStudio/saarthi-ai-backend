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
from bson import ObjectId

# Logs Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Version update kar diya 36.0.0 (Ultron Swarm Active)
app = FastAPI(title="Saarthi AI Core", version="36.0.0") 

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
    pc_col = db["device_commands"]
    deep_mem_col = db["deep_memory"] 
    pc_status_col = db["pc_status"] # 🚀 NAYA ADD KIYA: Ultron PC Status ke liye
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

class PCCommandReq(BaseModel):
    target: str
    command: str
    status: str = "pending"

# 🚀 NAYE MODELS: Deep Memory & Ultron Data Handle karne ke liye
class DeepMemorySaveReq(BaseModel):
    mem_type: str # "text" or "visual"
    content: str
    location: str
    date: str
    time: str

class DeepMemoryActionReq(BaseModel):
    mem_id: str
    action: str # "delete", "pin", "rename"
    new_name: str = ""

# 🚀 NAYA MODEL: Ultron Swarm PC Status
class PCStatusReq(BaseModel):
    battery: int
    ram: int
    is_locked: bool

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"          
    action_data1: str = ""        
    action_data2: str = ""        
    action_data3: str = ""        

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AI is Online (V36.0.0: Deep Memory Gateway & Ultron Swarm Active)!"}

# =======================================================
# 🚀 NAYA ENDPOINT: SYSTEM OTA UPDATE CHECK
# =======================================================
@app.get("/api/check_update")
async def check_update():
    """Android App yahan se check karegi ki koi naya update aaya hai ya nahi"""
    return {
        "latest_version_code": 2,
        "version_name": "Jarvis Mark 3.0",
        "changelog": "- Added Ghost Camera\n- Added Omni-Device Control\n- Improved AI Memory\n- U.L.T.R.O.N. Swarm Added",
        "download_url": "https://aapki-website.com/jarvis_latest.apk"
    }

# =======================================================
# 🚀 NAYA ENDPOINT: U.L.T.R.O.N. SWARM NETWORK (PC STATUS)
# =======================================================
@app.post("/api/pc_status")
async def update_pc_status(req: PCStatusReq):
    """Laptop/PC yahan se apni halat (battery, RAM) update karega"""
    try:
        pc_status_col.update_one(
            {"device": "primary_pc"}, 
            {"$set": {
                "battery": req.battery, 
                "ram": req.ram, 
                "is_locked": req.is_locked, 
                "timestamp": datetime.datetime.now()
            }}, 
            upsert=True
        )
        return {"success": True, "message": "PC Status saved to Swarm"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/pc_status")
async def get_pc_status():
    """Android ka UltronWorker yahan se PC ki halat check karega"""
    try:
        status = pc_status_col.find_one({"device": "primary_pc"}, {"_id": 0})
        if status:
            status["timestamp"] = str(status["timestamp"])
            return status
        else:
            # Agar PC ne abhi tak data nahi bheja, toh Alert Test karne ke liye Default Data:
            return {"battery": 12, "ram": 95, "is_locked": False}
    except Exception as e:
        return {"battery": 12, "ram": 95, "is_locked": False}

# =======================================================
# DEEP MEMORY (UI & JARVIS KE LIYE)
# =======================================================
@app.post("/api/deep_memory/save")
async def save_deep_memory(req: DeepMemorySaveReq):
    try:
        deep_mem_col.insert_one({
            "type": req.mem_type,
            "content": req.content,
            "custom_name": "New Memory",
            "location": req.location,
            "date": req.date,
            "time": req.time,
            "timestamp": datetime.datetime.now(),
            "is_pinned": False
        })
        return {"success": True, "message": "Deep Memory Locked!"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/deep_memory/get_all")
async def get_all_deep_memory():
    try:
        records = list(deep_mem_col.find().sort("timestamp", -1))
        for r in records: r["_id"] = str(r["_id"]) 
        return {"memories": records}
    except Exception as e: return {"error": str(e)}

@app.post("/api/deep_memory/action")
async def action_deep_memory(req: DeepMemoryActionReq):
    try:
        obj_id = ObjectId(req.mem_id)
        if req.action == "delete":
            deep_mem_col.delete_one({"_id": obj_id})
        elif req.action == "pin":
            doc = deep_mem_col.find_one({"_id": obj_id})
            deep_mem_col.update_one({"_id": obj_id}, {"$set": {"is_pinned": not doc.get("is_pinned", False)}})
        elif req.action == "rename":
            deep_mem_col.update_one({"_id": obj_id}, {"$set": {"custom_name": req.new_name}})
        return {"success": True}
    except Exception as e: return {"error": str(e)}

def search_deep_memory(query: str):
    """Jarvis is function ko khud call karega aapke sawaal ka jawab dene ke liye"""
    try:
        words = query.split()
        regex_query = "|".join(words)
        records = list(deep_mem_col.find({"content": {"$regex": regex_query, "$options": "i"}}).sort("timestamp", -1).limit(5))
        
        if not records: return "Deep memory mein is se judi koi jankari nahi mili boss."
        
        mem_str = "Deep Memory Results:\n"
        for r in records:
            mem_str += f"- [{r['type'].upper()}] Date: {r['date']}, Time: {r['time']}, Location: {r['location']}. Detail: {r['content']}\n"
        return mem_str
    except Exception as e: return "Memory retrieve karne mein error aaya boss."

# =======================================================
# PURANE ENDPOINTS (ANDROID SE MEMORY SAVE AUR FETCH)
# =======================================================
@app.post("/api/save_memory")
async def save_memory(req: MemoryRequest):
    try:
        memory_col.update_one({"key": req.key}, {"$set": {"value": req.value}}, upsert=True)
        return {"status": "Memory Saved Boss!"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/get_memory")
async def get_memory():
    try:
        records = list(memory_col.find({}, {"_id": 0}))
        mem_str = "\n".join([f"- {r['key']}: {r['value']}" for r in records])
        return {"memory": mem_str}
    except Exception as e:
        return {"memory": ""}

# =======================================================
# 🚀 PC CONTROLLER ENDPOINT
# =======================================================
@app.post("/api/pc_command")
async def pc_command(req: PCCommandReq):
    try:
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

# 🚀 TOOLS UPDATE
saarthi_tools = [
    {"type": "function", "function": {"name": "perform_web_search", "description": "Search the internet.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_live_weather", "description": "Fetch real-time weather.", "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}}},
    {"type": "function", "function": {"name": "query_location_history", "description": "Find out where the user was.", "parameters": {"type": "object", "properties": {"date_query": {"type": "string"}}, "required": ["date_query"]}}},
    {"type": "function", "function": {"name": "search_deep_memory", "description": "Search user's permanent Deep Memory to answer questions about past events, items, or visual memories.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "control_device", "description": "Control hardware, apps, UI, Media, Volume, Vision.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["open_app", "close_app", "youtube_search", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "open_camera", "open_scanner", "set_alarm", "set_timer", "bluetooth_settings", "gps_settings", "quick_share", "vision_scanning", "scan_vision"]}, "app_package": {"type": "string"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "communicate", "description": "Make a phone call or send a WhatsApp.", "parameters": {"type": "object", "properties": {"method": {"type": "string", "enum": ["call", "whatsapp"]}, "contact_name": {"type": "string"}, "message_text": {"type": "string"}}, "required": ["method", "contact_name"]}}}
]

@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    return ChatResponse(reply="I am now handled by Android Native Engine.", action="NONE")
