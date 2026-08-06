import os
import logging
import json
import datetime
import pytz
import requests
import re
import base64
import io
import wave
import struct
import asyncio
from typing import List
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import AsyncGroq
from dotenv import load_dotenv
from duckduckgo_search import DDGS 
from pymongo import MongoClient
import certifi
from bson import ObjectId
import cloudinary
import cloudinary.uploader

# ==========================================
# 🧠 VECTOR DB & NEURAL EMBEDDINGS ENGINE
# ==========================================
try:
    from pinecone import Pinecone
    from sentence_transformers import SentenceTransformer
    # Loading the 384-dimension embedding model
    embed_model = SentenceTransformer('all-MiniLM-L6-v2')
    logger.info("🟢 SentenceTransformer (all-MiniLM-L6-v2) Loaded Successfully!")
except Exception as embed_err:
    embed_model = None
    Pinecone = None
    logger.warning(f"⚠️ Vector Engine Load Warning: {embed_err}")

# Logs Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# Cloudinary Configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# Pinecone Vector DB Configuration
pc_api_key = os.getenv("PINECONE_API_KEY")
pc_index = None
if pc_api_key and Pinecone:
    try:
        pc = Pinecone(api_key=pc_api_key)
        if "saarthi-memory" in [idx.name for idx in pc.list_indexes()]:
            pc_index = pc.Index("saarthi-memory")
            logger.info("🟢 Pinecone Index 'saarthi-memory' Connected Successfully!")
    except Exception as pc_err:
        logger.error(f"🔴 Pinecone Init Error: {pc_err}")

# Version update kar diya 42.0.0 (Mark 12.0: Neural Vector Embedding Core Active)
app = FastAPI(title="Saarthi AI Core", version="42.0.0") 

# CORS Middleware (Cross-device connectivity ke liye)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")

client = AsyncGroq(api_key=api_key)
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")

# 💾 MONGODB SETUP
MONGO_URI = "mongodb+srv://favouritegamer192_db_user:pjt6UStm6rB3ekEv@saarthi.sfsuxij.mongodb.net/?appName=Saarthi"
try:
    mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = mongo_client["saarthi_db"]
    location_col = db["location_history"] 
    memory_col = db["permanent_memory"]
    pc_col = db["device_commands"]
    deep_mem_col = db["deep_memory"] 
    pc_status_col = db["pc_status"] 
    mongo_client.admin.command('ping') 
    logger.info("🟢 MongoDB Connected Successfully!")
except Exception as e:
    logger.error(f"🔴 MongoDB Connection Error: {e}")

global_chat_history = []

# 📦 PYDANTIC MODELS
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

class DeepMemorySaveReq(BaseModel):
    mem_type: str 
    content: str
    location: str
    date: str
    time: str

class DeepMemoryActionReq(BaseModel):
    mem_id: str
    action: str 
    new_name: str = ""

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
    return {"status": "🟢 Saarthi Omni-Core is Online (V42.0.0)!", "service": "Pinecone Neural Vector Core Active"}

# =======================================================
# 🌐 WEBSOCKET CONNECTION MANAGER
# =======================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"🟢 New Client Connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"🔴 Client Disconnected. Total active: {len(self.active_connections)}")

    async def send_json(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send JSON message: {e}")

manager = ConnectionManager()

# =======================================================
# 🧠 CENTRALIZED LLM LOGIC (TEXT + VISION MULTIMODAL)
# =======================================================
async def generate_jarvis_response(user_msg: str, android_memory: str = "", image_base64: str = None) -> dict:
    global global_chat_history
    
    system_prompt = {
        "role": "system",
        "content": (
            "You are Saarthi (aka Jarvis), an extremely advanced AI assistant created by AR Patel Studio. "
            "Speak in a natural, cool, and respectful Hinglish tone (Hindi + English). "
            "Always address the user as 'Boss'. Keep your answers concise, straight to the point. "
            f"Extra Context from Android: {android_memory}"
        )
    }

    messages = [system_prompt] + global_chat_history
    action_type = "NONE"
    action_data1 = ""
    action_data2 = ""

    try:
        if image_base64:
            logger.info("👁️ Vision payload detected! Switching to Llama-3.2-90B-Vision model.")
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user_msg},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            })
            
            response = await client.chat.completions.create(
                model="llama-3.2-90b-vision-preview",  
                messages=messages,
                max_tokens=800,
                temperature=0.7
            )
            final_reply = response.choices[0].message.content
            
            # Simple fallback intent detection for saving vision memory when using the vision model
            if any(k in user_msg.lower() for k in ["save", "yaad", "remember", "capture", "keep"]):
                action_type = "SAVE_VISION"
                action_data1 = "User requested vision save"
            
        else:
            messages.append({"role": "user", "content": user_msg})
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",  
                messages=messages,
                tools=saarthi_tools,
                tool_choice="auto",
                max_tokens=500,
                temperature=0.7
            )

            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                messages.append(response_message) 
                
                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    logger.info(f"⚙️ Jarvis called Tool: {func_name} with args {args}")

                    if func_name == "save_vision_to_memory":
                        action_type = "SAVE_VISION"
                        action_data1 = args.get("context_tag", "Vision Memory")
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": "Vision save triggered successfully."})
                    elif func_name == "perform_web_search":
                        result = perform_web_search(args.get("query"))
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": result})
                    elif func_name == "get_live_weather":
                        result = get_live_weather(args.get("location"))
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": result})
                    elif func_name == "query_location_history":
                        result = query_location_history(args.get("date_query"))
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": result})
                    elif func_name == "search_deep_memory":
                        result = search_deep_memory(args.get("query"))
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": result})
                    elif func_name == "control_device":
                        action_type = args.get("action", "NONE")
                        action_data1 = args.get("app_package", "")
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": "Action triggered on Android."})
                    elif func_name == "communicate":
                        action_type = args.get("method", "call").upper()
                        action_data1 = args.get("contact_name", "")
                        action_data2 = args.get("message_text", "")
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": "Communication intent sent to Android."})

                final_response = await client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    max_tokens=500,
                    temperature=0.7
                )
                final_reply = final_response.choices[0].message.content
            else:
                final_reply = response_message.content

        global_chat_history.append({"role": "user", "content": user_msg})
        global_chat_history.append({"role": "assistant", "content": final_reply})
        if len(global_chat_history) > 12: 
            global_chat_history = global_chat_history[-12:]

        return {
            "type": "ai_response",
            "reply": final_reply,
            "action": action_type,
            "action_data1": action_data1,
            "action_data2": action_data2
        }

    except Exception as e:
        logger.error(f"🔴 Groq LLM Error: {e}")
        return {
            "type": "ai_response",
            "reply": "Sorry boss, mere neural net mein kuch glitch aa gaya hai. Kripya thodi der baad try karein.",
            "action": "NONE",
            "action_data1": "",
            "action_data2": ""
        }

# =======================================================
# 🎙️ VAD & VISUAL BUFFER LOGIC FOR WEBSOCKET
# =======================================================
def get_max_amplitude(pcm_bytes):
    count = len(pcm_bytes) // 2
    if count == 0: return 0
    samples = struct.unpack(f"<{count}h", pcm_bytes[:count*2])
    return max(abs(s) for s in samples)

@app.websocket("/ws/live_chat")
async def live_chat_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    audio_buffer = bytearray()
    is_speaking = False
    last_voice_time = time.time()
    
    latest_received_image = None 
    
    SILENCE_THRESHOLD = 1500     
    MAX_SILENCE_DURATION = 1.5   
    
    try:
        while True:
            raw_data = await websocket.receive_text()
            payload = json.loads(raw_data)
            msg_type = payload.get("type")

            if msg_type == "heartbeat":
                await manager.send_json({"type": "heartbeat_ack", "status": "alive"}, websocket)

            elif msg_type == "init":
                client_name = payload.get("client", "Unknown")
                logger.info(f"🛠️ Handshake successful with: {client_name}")
                await manager.send_json({
                    "type": "system",
                    "reply": "Connection established with Supreme Mainframe.",
                    "action": "NONE"
                }, websocket)

            elif msg_type == "audio_stream":
                b64_audio = payload.get("data")
                b64_image = payload.get("image_data")
                
                if b64_image:
                    latest_received_image = b64_image
                    logger.info("📸 Server visual buffer updated with latest frame.")
                
                if b64_audio:
                    pcm_bytes = base64.b64decode(b64_audio)
                    amplitude = get_max_amplitude(pcm_bytes)
                    audio_buffer.extend(pcm_bytes)
                    
                    if amplitude > SILENCE_THRESHOLD:
                        is_speaking = True
                        last_voice_time = time.time()
                    else:
                        if is_speaking and (time.time() - last_voice_time > MAX_SILENCE_DURATION):
                            is_speaking = False
                            
                            if len(audio_buffer) > 16000:
                                logger.info(f"🎙️ VAD Triggered! Processing voice + image if any.")
                                
                                wav_io = io.BytesIO()
                                with wave.open(wav_io, 'wb') as wav_file:
                                    wav_file.setnchannels(1)
                                    wav_file.setsampwidth(2)
                                    wav_file.setframerate(16000)
                                    wav_file.writeframes(audio_buffer)
                                wav_io.seek(0)
                                audio_buffer.clear()
                                
                                try:
                                    file_tuple = ("audio.wav", wav_io.read(), "audio/wav")
                                    transcription = await client.audio.transcriptions.create(
                                        file=file_tuple,
                                        model="whisper-large-v3",
                                        response_format="json"
                                    )
                                    user_text = transcription.text.strip()
                                    
                                    if user_text:
                                        logger.info(f"🗣️ User Said (Live): {user_text}")
                                        
                                        response_data = await generate_jarvis_response(
                                            user_msg=user_text, 
                                            image_base64=latest_received_image
                                        )
                                        
                                        await manager.send_json(response_data, websocket)

                                        # ☁️ SELECTIVE CLOUDINARY + MONGO + PINECONE VECTOR SAVE
                                        if response_data.get("action") == "SAVE_VISION" and latest_received_image:
                                            try:
                                                logger.info("☁️ Command received. Uploading frame to Cloudinary...")
                                                upload_result = cloudinary.uploader.upload(
                                                    f"data:image/jpeg;base64,{latest_received_image}", 
                                                    folder="saarthi_vision"
                                                )
                                                image_url = upload_result.get("secure_url")
                                                
                                                ist_timezone = pytz.timezone('Asia/Kolkata')
                                                live_time = datetime.datetime.now(ist_timezone)
                                                
                                                mem_content = f"Tag: '{response_data.get('action_data1', '')}' | User: '{user_text}' | Jarvis: '{response_data['reply']}'"
                                                
                                                doc_res = deep_mem_col.insert_one({
                                                    "type": "visual",
                                                    "content": mem_content,
                                                    "url": image_url,
                                                    "custom_name": "Requested Vision Memory",
                                                    "location": "Live Context",
                                                    "date": live_time.strftime('%Y-%m-%d'),
                                                    "time": live_time.strftime('%I:%M %p'),
                                                    "timestamp": datetime.datetime.now(),
                                                    "is_pinned": False
                                                })
                                                
                                                # 🌲 Pinecone Vector Integration
                                                if pc_index and embed_model:
                                                    vector = embed_model.encode(mem_content).tolist()
                                                    pc_index.upsert(vectors=[(
                                                        str(doc_res.inserted_id),
                                                        vector,
                                                        {"content": mem_content, "url": image_url, "type": "visual"}
                                                    )])
                                                    logger.info("🌲 Vector embedding successfully upserted to Pinecone!")

                                                logger.info(f"✅ Selective Visual Memory saved. URL: {image_url}")
                                            except Exception as cloud_err:
                                                logger.error(f"🔴 Cloudinary / Vector Save Error: {cloud_err}")
                                            
                                        latest_received_image = None
                                        
                                except Exception as e:
                                    logger.error(f"🔴 Whisper STT Error: {e}")
                            else:
                                audio_buffer.clear()

            elif msg_type == "text_command":
                user_text = payload.get("data")
                b64_image = payload.get("image_data")
                
                if user_text:
                    logger.info(f"💬 Text Command (Live): {user_text}")
                    response_data = await generate_jarvis_response(
                        user_msg=user_text, 
                        image_base64=b64_image
                    )
                    await manager.send_json(response_data, websocket)
                    
                    if response_data.get("action") == "SAVE_VISION" and b64_image:
                        try:
                            upload_result = cloudinary.uploader.upload(f"data:image/jpeg;base64,{b64_image}", folder="saarthi_vision")
                            image_url = upload_result.get("secure_url")
                            ist_timezone = pytz.timezone('Asia/Kolkata')
                            live_time = datetime.datetime.now(ist_timezone)
                            mem_content = f"Tag: '{response_data.get('action_data1', '')}' | User: '{user_text}' | Jarvis: '{response_data['reply']}'"
                            
                            doc_res = deep_mem_col.insert_one({
                                "type": "visual",
                                "content": mem_content,
                                "url": image_url,
                                "custom_name": "Requested Vision Memory",
                                "location": "Live Context",
                                "date": live_time.strftime('%Y-%m-%d'),
                                "time": live_time.strftime('%I:%M %p'),
                                "timestamp": datetime.datetime.now(),
                                "is_pinned": False
                            })
                            
                            if pc_index and embed_model:
                                vector = embed_model.encode(mem_content).tolist()
                                pc_index.upsert(vectors=[(
                                    str(doc_res.inserted_id),
                                    vector,
                                    {"content": mem_content, "url": image_url, "type": "visual"}
                                )])
                                logger.info("🌲 Text Command Vector embedding upserted to Pinecone!")

                            logger.info(f"✅ Text Selective Visual Memory saved. URL: {image_url}")
                        except Exception as cloud_err:
                            logger.error(f"🔴 Cloudinary Save Error: {cloud_err}")

    except WebSocketDisconnect:
        logger.warning("⚠️ WebSocket disconnected cleanly by the client.")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"💀 WebSocket Exception: {e}")
        manager.disconnect(websocket)

# =======================================================
# 🌐 OLD REST ENDPOINT & UTILS (Intact and Safe)
# =======================================================
@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    res = await generate_jarvis_response(request.message, request.android_memory)
    return ChatResponse(
        reply=res["reply"],
        action=res["action"],
        action_data1=res.get("action_data1", ""),
        action_data2=res.get("action_data2", ""),
        action_data3=""
    )

@app.get("/api/check_update")
async def check_update():
    return {
        "latest_version_code": 2,
        "version_name": "Jarvis Mark 3.0",
        "changelog": "- Added Ghost Camera\n- Added Omni-Device Control\n- Improved AI Memory\n- U.L.T.R.O.N. Swarm Added",
        "download_url": "https://aapki-website.com/jarvis_latest.apk"
    }

@app.post("/api/pc_status")
async def update_pc_status(req: PCStatusReq):
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
    try:
        status = pc_status_col.find_one({"device": "primary_pc"}, {"_id": 0})
        if status:
            status["timestamp"] = str(status["timestamp"])
            return status
        else:
            return {"battery": 12, "ram": 95, "is_locked": False}
    except Exception as e:
        return {"battery": 12, "ram": 95, "is_locked": False}

@app.post("/api/deep_memory/save")
async def save_deep_memory(req: DeepMemorySaveReq):
    try:
        doc_res = deep_mem_col.insert_one({
            "type": req.mem_type,
            "content": req.content,
            "custom_name": "New Memory",
            "location": req.location,
            "date": req.date,
            "time": req.time,
            "timestamp": datetime.datetime.now(),
            "is_pinned": False
        })
        
        # Save to Pinecone Vector DB
        if pc_index and embed_model:
            vector = embed_model.encode(req.content).tolist()
            pc_index.upsert(vectors=[(
                str(doc_res.inserted_id),
                vector,
                {"content": req.content, "type": req.mem_type}
            )])
            
        return {"success": True, "message": "Deep Memory Locked in DB + Vector Index!"}
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
            if pc_index:
                pc_index.delete(ids=[req.mem_id])
        elif req.action == "pin":
            doc = deep_mem_col.find_one({"_id": obj_id})
            deep_mem_col.update_one({"_id": obj_id}, {"$set": {"is_pinned": not doc.get("is_pinned", False)}})
        elif req.action == "rename":
            deep_mem_col.update_one({"_id": obj_id}, {"$set": {"custom_name": req.new_name}})
        return {"success": True}
    except Exception as e: return {"error": str(e)}

def search_deep_memory(query: str):
    try:
        results_str = []
        
        # 1. Pinecone Semantic Vector Search
        if pc_index and embed_model:
            try:
                query_vector = embed_model.encode(query).tolist()
                pc_res = pc_index.query(vector=query_vector, top_k=4, include_metadata=True)
                for match in pc_res.get('matches', []):
                    score = round(match.get('score', 0), 2)
                    meta = match.get('metadata', {})
                    # Sirf high confidence match hi lenge
                    if score > 0.4:
                        results_str.append(f"- [SEMANTIC MATCH - Confidence {score}] {meta.get('content', '')}")
            except Exception as ve_err:
                logger.error(f"Pinecone Search Error: {ve_err}")

        # 2. MongoDB Keyword Fallback
        words = query.split()
        regex_query = "|".join(words)
        records = list(deep_mem_col.find({"content": {"$regex": regex_query, "$options": "i"}}).sort("timestamp", -1).limit(4))
        
        for r in records:
            results_str.append(f"- [{r.get('type', 'TEXT').upper()}] Date: {r.get('date', '')}, Location: {r.get('location', '')}. Detail: {r.get('content', '')}")

        if not results_str: 
            return "Deep memory mein is se judi koi jankari nahi mili boss."
            
        # Remove duplicates
        unique_results = list(set(results_str))
        return "Deep Memory Results:\n" + "\n".join(unique_results)
    except Exception as e: 
        return "Memory retrieve karne mein error aaya boss."

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

saarthi_tools = [
    {"type": "function", "function": {"name": "save_vision_to_memory", "description": "Saves the current visual frame/photo to permanent memory ONLY when the user explicitly asks to save, remember, capture, or keep a photo of what they are pointing at.", "parameters": {"type": "object", "properties": {"context_tag": {"type": "string", "description": "A short summary of what is being saved based on user command."}}, "required": ["context_tag"]}}},
    {"type": "function", "function": {"name": "perform_web_search", "description": "Search the internet.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_live_weather", "description": "Fetch real-time weather.", "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}}},
    {"type": "function", "function": {"name": "query_location_history", "description": "Find out where the user was.", "parameters": {"type": "object", "properties": {"date_query": {"type": "string"}}, "required": ["date_query"]}}},
    {"type": "function", "function": {"name": "search_deep_memory", "description": "Search permanent Deep Memory for semantic context matches.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "control_device", "description": "Control hardware, apps, UI, Media, Volume, Vision.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["open_app", "close_app", "youtube_search", "flashlight_on", "flashlight_off", "media_play", "media_pause", "media_stop", "open_camera", "open_scanner", "set_alarm", "set_timer", "bluetooth_settings", "gps_settings", "quick_share", "vision_scanning", "scan_vision"]}, "app_package": {"type": "string"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "communicate", "description": "Make a phone call or send a WhatsApp.", "parameters": {"type": "object", "properties": {"method": {"type": "string", "enum": ["call", "whatsapp"]}, "contact_name": {"type": "string"}, "message_text": {"type": "string"}}, "required": ["method", "contact_name"]}}}
]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
