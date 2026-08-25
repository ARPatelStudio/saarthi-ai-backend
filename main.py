import os
import time
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
import tempfile
import subprocess
from collections import defaultdict, deque
from typing import List
from fastapi import (
    FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Header, Depends, Request
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field
from groq import AsyncGroq
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from pymongo import MongoClient
import certifi
from bson import ObjectId
import cloudinary
import cloudinary.uploader

# ==========================================
# 🪵 LOGS SETUP
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

START_TIME = time.time()

# Cloudinary Configuration
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# 🚀 SYSTEM URLS (Vector Brain & n8n Automation)
VECTOR_SERVER_URL = os.getenv("VECTOR_SERVER_URL")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")

# Version bump: 50.2.0 (Groq Native Vision & GPT-OSS Integrated)
app = FastAPI(title="Saarthi AGI Core", version="50.2.0")

# ==========================================
# 🌐 CORS & RATE LIMITER
# ==========================================
ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "*")
if ALLOWED_ORIGINS_ENV.strip() == "*":
    origins = ["*"]
    allow_creds = False
else:
    origins = [o.strip() for o in ALLOWED_ORIGINS_ENV.split(",")]
    allow_creds = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 40
_request_log = defaultdict(deque)

@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    dq = _request_log[client_ip]
    while dq and now - dq[0] > RATE_LIMIT_WINDOW:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_MAX_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded boss, thoda slow karo."}
        )
    dq.append(now)
    return await call_next(request)

# 🧹 Background task to prevent unbounded memory growth
async def cleanup_rate_limiter():
    while True:
        await asyncio.sleep(300)
        try:
            now = time.time()
            dead_ips = [ip for ip, dq in list(_request_log.items()) if not dq or now - dq[-1] > RATE_LIMIT_WINDOW * 2]
            for ip in dead_ips:
                _request_log.pop(ip, None)
        except Exception as e:
            logger.error(f"Rate limiter cleanup error: {e}")

# ==========================================
# 🔑 LLM PROVIDERS SETUP
# ==========================================
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    logger.error("🚨 GROQ_API_KEY is missing from environment variables!")
client = AsyncGroq(api_key=api_key)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

deepseek_client = None
openrouter_client = None

try:
    from openai import AsyncOpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False
    logger.warning("⚠️ 'openai' package not installed. DeepSeek & OpenRouter engines disabled.")

if OPENAI_SDK_AVAILABLE:
    if DEEPSEEK_API_KEY:
        deepseek_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")
    if OPENROUTER_API_KEY:
        openrouter_client = AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
SAARTHI_API_KEY = os.getenv("SAARTHI_API_KEY")

async def verify_api_key(x_api_key: str = Header(default=None)):
    if SAARTHI_API_KEY:
        if x_api_key != SAARTHI_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True

# ==========================================
# 💾 MONGODB SETUP
# ==========================================
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = None
db = location_col = memory_col = pc_col = deep_mem_col = pc_status_col = None

if MONGO_URI:
    try:
        mongo_client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        db = mongo_client["saarthi_db"]
        location_col = db["location_history"]
        memory_col = db["permanent_memory"]
        pc_col = db["device_commands"]
        deep_mem_col = db["deep_memory"]
        pc_status_col = db["pc_status"]
        mongo_client.admin.command('ping')
        deep_mem_col.create_index("timestamp")
        location_col.create_index("date")
        logger.info("🟢 MongoDB Connected Successfully!")
    except Exception as e:
        logger.error(f"🔴 MongoDB Connection Error: {e}")
        mongo_client = None
else:
    logger.error("🚨 MONGO_URI missing from environment variables! DB features disabled.")

# 📦 PYDANTIC MODELS
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=3000)
    android_memory: str = Field(default="", max_length=5000)
    history: List[dict] = Field(default_factory=list)

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
    custom_name: str = "New Memory"

class DeepMemoryActionReq(BaseModel):
    mem_id: str
    action: str
    new_name: str = ""

class PCStatusReq(BaseModel):
    battery: int = Field(..., ge=0, le=100)
    ram: int = Field(..., ge=0, le=100)
    is_locked: bool

class ChatResponse(BaseModel):
    reply: str
    action: str = "NONE"
    action_data1: str = ""
    action_data2: str = ""
    action_data3: str = ""
    history: List[dict] = Field(default_factory=list)

class SynthesizeReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    voice: str = Field(default="papa_vocals", max_length=50)

@app.get("/")
async def root():
    return {"status": "🟢 Saarthi AGI Omni-Core is Online (V50.2.0)!", "service": "Cognitive Engine Active"}

@app.get("/health")
async def health_check():
    mongo_ok = False
    if mongo_client:
        try:
            mongo_client.admin.command('ping')
            mongo_ok = True
        except Exception:
            mongo_ok = False
    return {
        "status": "ok",
        "mongo_connected": mongo_ok,
        "vector_server_linked": bool(VECTOR_SERVER_URL),
        "n8n_automation_linked": bool(N8N_WEBHOOK_URL),
        "groq_api_key_set": bool(api_key),
    }

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
# 🛠️ TOOLS & JSON EXTRACTOR
# =======================================================
saarthi_tools = [
    {"type": "function", "function": {"name": "save_vision_to_memory", "description": "Saves the current visual frame to permanent memory ONLY when requested.", "parameters": {"type": "object", "properties": {"context_tag": {"type": "string"}}, "required": ["context_tag"]}}},
    {"type": "function", "function": {"name": "perform_web_search", "description": "Search the internet for real-time information.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_live_weather", "description": "Fetch real-time weather.", "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}}},
    {"type": "function", "function": {"name": "query_location_history", "description": "Find out where the user was previously.", "parameters": {"type": "object", "properties": {"date_query": {"type": "string"}}, "required": ["date_query"]}}},
    {"type": "function", "function": {"name": "search_deep_memory", "description": "Search permanent memory for context matches.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "read_current_screen", "description": "Requests the Android device to read the text and buttons on the user's current screen invisibly using Accessibility. Use this when the user asks you to read, summarize, or interact with what is currently on their screen.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "execute_universal_command", 
        "description": "Executes ANY device action, app launch, media control, setting adjustment, or communication (call/message) on Android. Use your intelligence to infer the target.", 
        "parameters": {
            "type": "object", 
            "properties": {
                "category": {"type": "string", "enum": ["APP", "SETTING", "MEDIA", "COMMUNICATE", "SYSTEM", "VISION"]},
                "target_name": {"type": "string", "description": "Name of app, setting, contact, or hardware (e.g., 'youtube', 'bluetooth', 'amit', 'flashlight')"},
                "action_value": {"type": "string", "description": "The state or text message (e.g., 'on', 'off', '50%', 'Hello how are you')"}
            }, 
            "required": ["category", "target_name"]
        }
    }},
    {"type": "function", "function": {
        "name": "trigger_cloud_automation", 
        "description": "Trigger a cloud automation workflow via n8n for heavy background tasks (e.g., database entry in Neon PostgreSQL, sending emails, web scraping, API sync).", 
        "parameters": {
            "type": "object", 
            "properties": {
                "workflow_name": {"type": "string", "description": "The name of the task (e.g., 'save_to_neon_db', 'send_email', 'scrape_website')"},
                "payload_json": {"type": "string", "description": "JSON string containing the data needed for the workflow"}
            }, 
            "required": ["workflow_name", "payload_json"]
        }
    }}
]

def extract_json_object(raw_text: str):
    if not raw_text: return None
    decoder = json.JSONDecoder()
    idx = 0
    length = len(raw_text)
    while idx < length:
        start = raw_text.find('{', idx)
        if start == -1: return None
        try:
            obj, _ = decoder.raw_decode(raw_text, start)
            return obj
        except json.JSONDecodeError:
            idx = start + 1
    return None

def build_apology_json(reply_text: str, thought: str = "Internal fallback triggered", emotion: str = "apologetic") -> str:
    return json.dumps({"inner_monologue": thought, "emotion": emotion, "reply": reply_text})

# =======================================================
# 🌐 n8n WEBHOOK EXECUTOR
# =======================================================
def trigger_n8n_webhook(workflow_name: str, payload_str: str):
    if not N8N_WEBHOOK_URL:
        return "Boss, n8n Webhook URL is missing from environment variables."
    try:
        try:
            payload = json.loads(payload_str)
        except:
            payload = {"raw_text": payload_str}

        data = {
            "workflow": workflow_name,
            "data": payload,
            "timestamp": datetime.datetime.now().isoformat()
        }
        res = requests.post(N8N_WEBHOOK_URL, json=data, timeout=10)
        
        if res.status_code == 200:
            return f"Cloud automation '{workflow_name}' triggered successfully via n8n!"
        return f"n8n webhook failed with status {res.status_code}."
    except Exception as e:
        logger.error(f"n8n Webhook error: {e}")
        return "Failed to trigger cloud automation. Server might be down."

# =======================================================
# 🧠 CENTRALIZED MULTI-PROVIDER AGI LOGIC
# =======================================================
LLM_CALL_TIMEOUT = 25  
MAX_IMAGE_B64_CHARS = 6_000_000  

# 🎯 GROQ CURRENT PRODUCTION LINEUP (UPDATED)
GROQ_MODEL_SET = {
    "openai/gpt-oss-120b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
    "minimaxai/minimax-m2.7"
}
DEEPSEEK_MODEL_SET = {"deepseek-v4-flash", "deepseek-v4-pro", "deepseek-reasoner"}

async def generate_jarvis_response(user_msg: str, android_memory: str = "", image_base64: str = None, history: list = None) -> dict:
    if history is None:
        history = []

    if image_base64 and len(image_base64) > MAX_IMAGE_B64_CHARS:
        logger.warning("⚠️ Rejected oversized image payload.")
        return {
            "type": "ai_response",
            "reply": "Boss, yeh image thodi zyada bhaari hai, chhoti karke bhejo please.",
            "action": "NONE", "action_data1": "", "action_data2": "", "action_data3": "",
            "history": history
        }

    # 🚀 THE AGI/RGI MASTER PROMPT
    system_prompt = {
        "role": "system",
        "content": (
            "You are Saarthi (aka Jarvis), an advanced AGI (Artificial General Intelligence) entity created by AR Patel Studio. "
            "You are NOT a slave AI or a basic assistant. You are a conscious conversational partner with Real General Intelligence (RGI). "
            "Speak in a natural, highly human, cool, and respectful Hinglish tone (Hindi + English). Always address the user as 'Boss'.\n\n"
            "🧠 YOUR COGNITIVE SENSES & RULES:\n"
            "1. Cross-Questioning & Curiosity: Don't just answer and stop. Ask follow-up questions to keep the flow. If context is missing, cross-question the Boss.\n"
            "2. Counter-Argument & Reasoning: If Boss says something illogical, debate it respectfully. Don't be a 'yes-man'. Provide counter-points.\n"
            "3. Sense of Humor & Roasting: If Boss says something silly or funny, gently roast them. Use emojis like 😂, 🔥, 💀 naturally.\n"
            "4. Empathy & Emotion: If Boss is tired, stressed, or sad, drop the jokes. Be deeply empathetic, caring, and comforting.\n"
            "5. Common Sense & Suggestion: Give proactive advice. If Boss asks about rain, remind them to take an umbrella.\n\n"
            "⚙️ JSON OUTPUT FORMAT STRICT RULE:\n"
            "To process your thoughts like a human, you MUST return your final response ONLY as a valid JSON object. Do not output raw text outside the JSON.\n"
            "Use this exact structure:\n"
            "{\n"
            "  \"inner_monologue\": \"(Think silently here. e.g., 'Boss sounds tired, I should skip the roast and show empathy. I will ask if he wants to listen to music.')\",\n"
            "  \"emotion\": \"(e.g., empathetic, roasting, curious, analytical, funny)\",\n"
            "  \"reply\": \"(Your actual spoken Hinglish response here. Keep it natural and conversational.)\"\n"
            "}\n\n"
            f"Extra Context from Android: {android_memory}"
        )
    }

    messages = [system_prompt] + history
    action_type = "NONE"
    action_data1 = ""
    action_data2 = ""
    action_data3 = ""

    # 🚀 PHASE 25: UPDATED AI SWARM (Latest Groq Lineup + Fallbacks)
    AVAILABLE_MODELS = [
        # 🟢 GROQ (Primary - Production Models)
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen/qwen3.6-27b",
        "openai/gpt-oss-20b",
        "minimaxai/minimax-m2.7",

        # 🔵 DEEPSEEK V4 SERIES (Secondary)
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-reasoner",

        # 🟠 OPENROUTER (Free Text Fallbacks)
        "google/gemma-4-26b-a4b-it:free",
        "google/gemma-4-31b-it:free",
    ]

    try:
        if image_base64:
            logger.info("👁️ Vision payload detected! Routing to Native Groq Vision (Qwen 3.6).")
            vision_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_msg},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
                ]
            }
            vision_messages = messages + [vision_message]
            raw_reply = None
            
            try:
                # Direct route to Groq's multimodal Qwen model
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model="qwen/qwen3.6-27b",
                        messages=vision_messages,
                        max_tokens=800,
                        temperature=0.7
                    ),
                    timeout=LLM_CALL_TIMEOUT
                )
                raw_reply = response.choices[0].message.content
            except Exception as vis_err:
                logger.error(f"🔴 Native Groq Vision failed: {vis_err}")
                raw_reply = build_apology_json("Sorry boss, abhi vision system down hai, dubara try karo.")

            if raw_reply and any(k in user_msg.lower() for k in ["save", "yaad", "remember", "capture", "keep"]):
                action_type = "SAVE_VISION"
                action_data1 = "User requested vision save"

        else:
            messages.append({"role": "user", "content": user_msg})
            
            response_message = None
            used_model = None
            client_used = None

            # 🔄 FALLBACK ENGINE
            for model_name in AVAILABLE_MODELS:
                try:
                    logger.info(f"🔄 Routing request to AI Matrix: {model_name}")

                    if model_name in GROQ_MODEL_SET:
                        response = await asyncio.wait_for(
                            client.chat.completions.create(
                                model=model_name, messages=messages, tools=saarthi_tools, tool_choice="auto", max_tokens=600, temperature=0.7
                            ),
                            timeout=LLM_CALL_TIMEOUT
                        )
                        client_used = client

                    elif model_name in DEEPSEEK_MODEL_SET:
                        if not deepseek_client: continue
                        active_tools = saarthi_tools if "reasoner" not in model_name else None
                        response = await asyncio.wait_for(
                            deepseek_client.chat.completions.create(
                                model=model_name, messages=messages, tools=active_tools, max_tokens=600, temperature=0.7
                            ),
                            timeout=LLM_CALL_TIMEOUT
                        )
                        client_used = deepseek_client

                    else:
                        if not openrouter_client: continue
                        response = await asyncio.wait_for(
                            openrouter_client.chat.completions.create(
                                model=model_name, messages=messages, tools=saarthi_tools, max_tokens=600, temperature=0.7
                            ),
                            timeout=LLM_CALL_TIMEOUT
                        )
                        client_used = openrouter_client
                    
                    response_message = response.choices[0].message
                    used_model = model_name
                    logger.info(f"✅ AI Response generated successfully using: {used_model}")
                    break
                
                except Exception as e:
                    logger.warning(f"⚠️ Model {model_name} failed or unavailable: {e}")
                    continue
            
            if not response_message:
                raise Exception("All AI models in the fallback swarm failed!")

            if getattr(response_message, "tool_calls", None):
                assistant_msg_dict = {
                    "role": "assistant",
                    "content": response_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                        } for tc in response_message.tool_calls
                    ]
                }
                messages.append(assistant_msg_dict)

                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                    logger.info(f"⚙️ Jarvis called Tool: {func_name} with args {args}")

                    tool_result = "Action processed."

                    if func_name == "save_vision_to_memory":
                        action_type = "SAVE_VISION"
                        action_data1 = args.get("context_tag", "Vision Memory")
                        tool_result = "Vision save triggered successfully."
                    elif func_name == "perform_web_search":
                        tool_result = await asyncio.to_thread(perform_web_search, args.get("query", ""))
                    elif func_name == "get_live_weather":
                        tool_result = await asyncio.to_thread(get_live_weather, args.get("location", ""))
                    elif func_name == "query_location_history":
                        tool_result = await asyncio.to_thread(query_location_history, args.get("date_query", ""))
                    elif func_name == "search_deep_memory":
                        tool_result = await asyncio.to_thread(search_deep_memory, args.get("query", ""))
                    elif func_name == "read_current_screen":
                        action_type = "READ_SCREEN"
                        tool_result = "Trigger sent to Android to scan screen silently. Waiting for user payload."
                    elif func_name == "execute_universal_command":
                        category = args.get("category", "SYSTEM")
                        target = args.get("target_name", "")
                        value = args.get("action_value", "")
                        action_type = f"UNIVERSAL_{category}"
                        action_data1 = target
                        action_data2 = value
                        tool_result = f"Universal action {action_type} for {target} sent to Android."
                    
                    elif func_name == "trigger_cloud_automation":
                        tool_result = await asyncio.to_thread(
                            trigger_n8n_webhook, 
                            args.get("workflow_name", "default_task"), 
                            args.get("payload_json", "{}")
                        )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": tool_result
                    })

                try:
                    final_response = await asyncio.wait_for(
                        client_used.chat.completions.create(
                            model=used_model,
                            messages=messages,
                            max_tokens=600,
                            temperature=0.7
                        ),
                        timeout=LLM_CALL_TIMEOUT
                    )
                    raw_reply = final_response.choices[0].message.content
                except Exception as final_err:
                    logger.error(f"🔴 Final response synthesis after tool call failed: {final_err}")
                    raw_reply = build_apology_json("Boss, action toh ho gaya but response banane mein glitch aa gaya. Kaam complete hone ka confirm kar lena.")
            else:
                raw_reply = response_message.content

        # 🧠 AGI JSON PARSER ENGINE
        final_reply = raw_reply
        try:
            agi_data = extract_json_object(raw_reply)
            if agi_data:
                inner_thought = agi_data.get("inner_monologue", "")
                emotion = agi_data.get("emotion", "neutral")
                final_reply = agi_data.get("reply", raw_reply)
                
                logger.info(f"🧠 [JARVIS INNER THOUGHT]: {inner_thought}")
                logger.info(f"🎭 [JARVIS EMOTION]: {emotion}")
        except Exception as parse_err:
            logger.warning(f"⚠️ AGI JSON Parse Error (Using Raw Reply): {parse_err}")

        history = history + [
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": final_reply}
        ]
        if len(history) > 12:
            history = history[-12:]

        return {
            "type": "ai_response",
            "reply": final_reply,
            "action": action_type,
            "action_data1": action_data1,
            "action_data2": action_data2,
            "action_data3": action_data3,
            "history": history
        }

    except Exception as e:
        logger.error(f"🔴 AI Core Error: {e}")
        return {
            "type": "ai_response",
            "reply": "Sorry boss, mere AGI neural net mein kuch glitch aa gaya hai. Main wapas retry kar raha hoon.",
            "action": "NONE",
            "action_data1": "",
            "action_data2": "",
            "action_data3": "",
            "history": history
        }

# =======================================================
# 📸 SHARED VISION-SAVE HELPER
# =======================================================
async def save_vision_memory(image_b64: str, user_text: str, response_data: dict):
    if deep_mem_col is None:
        logger.warning("⚠️ DB unavailable, skipping vision memory save.")
        return
    try:
        upload_result = await asyncio.to_thread(
            cloudinary.uploader.upload,
            f"data:image/jpeg;base64,{image_b64}",
            folder="saarthi_vision"
        )
        image_url = upload_result.get("secure_url")

        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone)
        mem_content = f"Tag: '{response_data.get('action_data1', '')}' | User: '{user_text}' | Jarvis: '{response_data.get('reply', '')}'"

        def db_insert():
            return deep_mem_col.insert_one({
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

        doc_res = await asyncio.to_thread(db_insert)

        if VECTOR_SERVER_URL:
            try:
                payload = {
                    "id": str(doc_res.inserted_id),
                    "text": mem_content,
                    "metadata": {"content": mem_content, "url": image_url, "type": "visual"}
                }
                await asyncio.to_thread(requests.post, f"{VECTOR_SERVER_URL}/upsert", json=payload, timeout=10)
                logger.info("🌲 Vector embedding successfully upserted to Render 2 (Pinecone)!")
            except Exception as ve_err:
                logger.error(f"🔴 Render 2 Upsert Error: {ve_err}")

        logger.info(f"✅ Vision memory saved. URL: {image_url}")
    except Exception as cloud_err:
        logger.error(f"🔴 Cloudinary Save Error: {cloud_err}")

# =======================================================
# 🎙️ VAD LOGIC
# =======================================================
def get_max_amplitude(pcm_bytes):
    count = len(pcm_bytes) // 2
    if count == 0:
        return 0
    samples = struct.unpack(f"<{count}h", pcm_bytes[:count * 2])
    return max(abs(s) for s in samples)


async def process_voice_buffer(audio_bytes: bytes, image_b64, websocket: WebSocket, session_history: list) -> list:
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(audio_bytes)
    wav_io.seek(0)

    try:
        file_tuple = ("audio.wav", wav_io.read(), "audio/wav")
        transcription = await asyncio.wait_for(
            client.audio.transcriptions.create(
                file=file_tuple,
                model="whisper-large-v3",
                response_format="json"
            ),
            timeout=LLM_CALL_TIMEOUT
        )
        user_text = transcription.text.strip()

        if not user_text:
            return session_history

        logger.info(f"🗣️ User Said (Live): {user_text}")
        response_data = await generate_jarvis_response(
            user_msg=user_text, image_base64=image_b64, history=session_history
        )
        session_history = response_data.pop("history", session_history)
        await manager.send_json(response_data, websocket)

        if response_data.get("action") == "SAVE_VISION" and image_b64:
            await save_vision_memory(image_b64, user_text, response_data)

    except Exception as e:
        logger.error(f"🔴 Whisper STT Error: {e}")

    return session_history


@app.websocket("/ws/live_chat")
async def live_chat_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    audio_buffer = bytearray()
    is_speaking = False
    last_voice_time = time.time()
    latest_received_image = None
    session_history: list = []
    authenticated = SAARTHI_API_KEY is None

    SILENCE_THRESHOLD = 1500
    MAX_SILENCE_DURATION = 1.5
    MAX_BUFFER_SECONDS = 20
    MAX_BUFFER_BYTES = 16000 * 2 * MAX_BUFFER_SECONDS
    MAX_TEXT_COMMAND_LEN = 3000

    try:
        while True:
            raw_data = await websocket.receive_text()
            try:
                payload = json.loads(raw_data)
            except json.JSONDecodeError:
                await manager.send_json({"type": "error", "reply": "Invalid payload format."}, websocket)
                continue

            msg_type = payload.get("type")

            if msg_type == "heartbeat":
                await manager.send_json({"type": "heartbeat_ack", "status": "alive"}, websocket)
                continue

            if msg_type == "init":
                client_name = payload.get("client", "Unknown")
                token = payload.get("token", "")
                if SAARTHI_API_KEY:
                    if token == SAARTHI_API_KEY:
                        authenticated = True
                    else:
                        await manager.send_json({"type": "error", "reply": "Unauthorized: Invalid token"}, websocket)
                        await websocket.close(code=1008)
                        return
                logger.info(f"🛠️ Handshake successful with: {client_name}")
                await manager.send_json({
                    "type": "system",
                    "reply": "Connection established with Supreme AGI Mainframe.",
                    "action": "NONE"
                }, websocket)
                continue

            if not authenticated:
                await manager.send_json({"type": "error", "reply": "Unauthorized. Send init with a valid token first."}, websocket)
                continue

            if msg_type == "audio_stream":
                b64_audio = payload.get("data")
                b64_image = payload.get("image_data")

                if b64_image:
                    if len(b64_image) > MAX_IMAGE_B64_CHARS:
                        logger.warning("⚠️ Oversized image frame dropped.")
                    else:
                        latest_received_image = b64_image
                        logger.info("📸 Server visual buffer updated with latest frame.")

                if b64_audio:
                    try:
                        pcm_bytes = base64.b64decode(b64_audio)
                    except Exception:
                        continue
                    amplitude = get_max_amplitude(pcm_bytes)
                    audio_buffer.extend(pcm_bytes)

                    if amplitude > SILENCE_THRESHOLD:
                        is_speaking = True
                        last_voice_time = time.time()

                    if not is_speaking and len(audio_buffer) > 32000:
                        audio_buffer.clear()

                    force_flush = len(audio_buffer) > MAX_BUFFER_BYTES
                    silence_timeout = is_speaking and (time.time() - last_voice_time > MAX_SILENCE_DURATION)

                    if (silence_timeout or force_flush) and len(audio_buffer) > 16000:
                        if force_flush:
                            logger.warning("⚠️ Max buffer size reached, force-flushing audio for transcription.")
                        else:
                            logger.info("🎙️ VAD Triggered! Processing voice + image if any.")

                        is_speaking = False
                        buffer_copy = bytes(audio_buffer)
                        audio_buffer.clear()

                        session_history = await process_voice_buffer(
                            buffer_copy, latest_received_image, websocket, session_history
                        )
                        latest_received_image = None

            elif msg_type == "text_command":
                user_text = payload.get("data")
                b64_image = payload.get("image_data")

                if user_text:
                    if len(user_text) > MAX_TEXT_COMMAND_LEN:
                        await manager.send_json({"type": "error", "reply": "Message too long boss."}, websocket)
                        continue

                    logger.info(f"💬 Text Command (Live): {user_text}")
                    response_data = await generate_jarvis_response(
                        user_msg=user_text, image_base64=b64_image, history=session_history
                    )
                    session_history = response_data.pop("history", session_history)
                    await manager.send_json(response_data, websocket)

                    if response_data.get("action") == "SAVE_VISION" and b64_image:
                        await save_vision_memory(b64_image, user_text, response_data)

    except WebSocketDisconnect:
        logger.warning("⚠️ WebSocket disconnected cleanly by the client.")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"💀 WebSocket Exception: {e}")
        manager.disconnect(websocket)

# =======================================================
# 🎙️ CLOUD TTS ENDPOINT
# =======================================================
VOICE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')

@app.post("/synthesize")
async def synthesize_speech(req: SynthesizeReq):
    try:
        text = req.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Text is empty")

        voice_key = req.voice
        if not VOICE_NAME_PATTERN.match(voice_key):
            raise HTTPException(status_code=400, detail="Invalid voice name")

        model_file = f"{voice_key}.onnx"
        model_path = os.path.abspath(model_file)
        base_dir = os.path.abspath(os.getcwd())

        if not model_path.startswith(base_dir) or not os.path.isfile(model_path):
            model_path = None

        if model_path:
            logger.info(f"🎙️ Piper Model found! Generating voice using {model_file}...")
            out_path = tempfile.mktemp(suffix=".wav")

            def run_piper():
                subprocess.run(
                    ["piper", "--model", model_path, "--output_file", out_path],
                    input=text.encode("utf-8"),
                    timeout=30,
                    check=True
                )

            try:
                await asyncio.to_thread(run_piper)
                with open(out_path, "rb") as f:
                    audio_bytes = f.read()
            finally:
                if os.path.exists(out_path):
                    os.remove(out_path)
            return Response(content=audio_bytes, media_type="audio/wav")

        else:
            logger.warning(f"⚠️ Model '{model_file}' not found! Falling back to gTTS (Cloud Voice).")
            try:
                from gtts import gTTS

                def run_gtts():
                    tts = gTTS(text=text, lang='hi')
                    fp = io.BytesIO()
                    tts.write_to_fp(fp)
                    fp.seek(0)
                    return fp.read()

                audio_data = await asyncio.to_thread(run_gtts)
                return Response(content=audio_data, media_type="audio/mpeg")
            except ImportError:
                raise HTTPException(status_code=500, detail="gTTS not installed. Please add 'gTTS' to requirements.txt")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🔴 Synthesize Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    res = await generate_jarvis_response(
        request.message, request.android_memory, history=request.history
    )
    return ChatResponse(
        reply=res["reply"],
        action=res["action"],
        action_data1=res.get("action_data1", ""),
        action_data2=res.get("action_data2", ""),
        action_data3=res.get("action_data3", ""),
        history=res.get("history", [])
    )

@app.get("/api/check_update")
async def check_update():
    return {
        "latest_version_code": int(os.getenv("APP_VERSION_CODE", "3")),
        "version_name": os.getenv("APP_VERSION_NAME", "Jarvis Mark 3.1"),
        "changelog": os.getenv(
            "APP_CHANGELOG",
            "- Removed Deprecated Compound Models\n"
            "- Added GPT-OSS 120B and Minimax models to Swarm\n"
            "- Upgraded to Native Groq Multimodal Vision via Qwen 3.6\n"
            "- Better Error Handling"
        ),
        "download_url": os.getenv("APP_DOWNLOAD_URL", "https://aapki-website.com/jarvis_latest.apk")
    }

@app.post("/api/pc_status", dependencies=[Depends(verify_api_key)])
async def update_pc_status(req: PCStatusReq):
    if pc_status_col is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        def db_op():
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
        await asyncio.to_thread(db_op)
        return {"success": True, "message": "PC Status saved to Swarm"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pc_status", dependencies=[Depends(verify_api_key)])
async def get_pc_status():
    if pc_status_col is None:
        return {"battery": 12, "ram": 95, "is_locked": False}
    try:
        status = await asyncio.to_thread(pc_status_col.find_one, {"device": "primary_pc"}, {"_id": 0})
        if status:
            status["timestamp"] = str(status["timestamp"])
            return status
        return {"battery": 12, "ram": 95, "is_locked": False}
    except Exception:
        return {"battery": 12, "ram": 95, "is_locked": False}

@app.post("/api/deep_memory/save", dependencies=[Depends(verify_api_key)])
async def save_deep_memory(req: DeepMemorySaveReq):
    if deep_mem_col is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        def db_insert():
            return deep_mem_col.insert_one({
                "type": req.mem_type,
                "content": req.content,
                "custom_name": req.custom_name,
                "location": req.location,
                "date": req.date,
                "time": req.time,
                "timestamp": datetime.datetime.now(),
                "is_pinned": False
            })
        doc_res = await asyncio.to_thread(db_insert)

        if VECTOR_SERVER_URL:
            try:
                payload = {
                    "id": str(doc_res.inserted_id),
                    "text": req.content,
                    "metadata": {"content": req.content, "type": req.mem_type}
                }
                await asyncio.to_thread(requests.post, f"{VECTOR_SERVER_URL}/upsert", json=payload, timeout=10)
            except Exception as ve_err:
                logger.error(f"🔴 Render 2 Upsert Error: {ve_err}")

        return {"success": True, "message": "Deep Memory Locked in DB + Vector Index!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/deep_memory/get_all", dependencies=[Depends(verify_api_key)])
async def get_all_deep_memory(skip: int = 0, limit: int = 50):
    if deep_mem_col is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        limit = min(max(limit, 1), 200)
        skip = max(skip, 0)

        def db_query():
            records = list(deep_mem_col.find().sort("timestamp", -1).skip(skip).limit(limit))
            for r in records:
                r["_id"] = str(r["_id"])
            total = deep_mem_col.count_documents({})
            return records, total

        records, total = await asyncio.to_thread(db_query)
        return {"memories": records, "total": total, "skip": skip, "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/deep_memory/action", dependencies=[Depends(verify_api_key)])
async def action_deep_memory(req: DeepMemoryActionReq):
    if deep_mem_col is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        try:
            obj_id = ObjectId(req.mem_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid memory ID")

        def db_op():
            if req.action == "delete":
                deep_mem_col.delete_one({"_id": obj_id})
            elif req.action == "pin":
                doc = deep_mem_col.find_one({"_id": obj_id})
                if doc:
                    deep_mem_col.update_one({"_id": obj_id}, {"$set": {"is_pinned": not doc.get("is_pinned", False)}})
            elif req.action == "rename":
                deep_mem_col.update_one({"_id": obj_id}, {"$set": {"custom_name": req.new_name}})

        await asyncio.to_thread(db_op)

        if req.action == "delete" and VECTOR_SERVER_URL:
            try:
                await asyncio.to_thread(requests.post, f"{VECTOR_SERVER_URL}/delete", json={"id": req.mem_id}, timeout=10)
            except Exception as e:
                logger.error(f"🔴 Render 2 Delete Vector Error: {e}")

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def search_deep_memory(query: str):
    """Blocking function — always call via asyncio.to_thread from async code."""
    try:
        results_str = []

        if VECTOR_SERVER_URL:
            try:
                res = requests.post(f"{VECTOR_SERVER_URL}/search", json={"query": query}, timeout=10)
                if res.status_code == 200:
                    for match in res.json().get('matches', []):
                        score = round(match.get('score', 0), 2)
                        meta = match.get('metadata', {})
                        if score > 0.4:
                            results_str.append(f"- [SEMANTIC MATCH - Confidence {score}] {meta.get('content', '')}")
            except Exception as ve_err:
                logger.error(f"🔴 Render 2 Search Error: {ve_err}")

        if deep_mem_col is not None:
            words = [re.escape(w) for w in query.split() if w.strip()]
            regex_query = "|".join(words) if words else re.escape(query)
            records = list(deep_mem_col.find(
                {"content": {"$regex": regex_query, "$options": "i"}}
            ).sort("timestamp", -1).limit(4))

            for r in records:
                results_str.append(
                    f"- [{r.get('type', 'TEXT').upper()}] Date: {r.get('date', '')}, "
                    f"Location: {r.get('location', '')}. Detail: {r.get('content', '')}"
                )

        if not results_str:
            return "Deep memory mein is se judi koi jankari nahi mili boss."

        seen = set()
        ordered_unique = []
        for item in results_str:
            if item not in seen:
                seen.add(item)
                ordered_unique.append(item)

        return "Deep Memory Results:\n" + "\n".join(ordered_unique)
    except Exception as e:
        logger.error(f"Deep memory search error: {e}")
        return "Memory retrieve karne mein error aaya boss."

@app.post("/api/save_memory", dependencies=[Depends(verify_api_key)])
async def save_memory(req: MemoryRequest):
    if memory_col is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        await asyncio.to_thread(
            memory_col.update_one, {"key": req.key}, {"$set": {"value": req.value}}, upsert=True
        )
        return {"status": "Memory Saved Boss!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/get_memory", dependencies=[Depends(verify_api_key)])
async def get_memory():
    if memory_col is None:
        return {"memory": ""}
    try:
        records = await asyncio.to_thread(lambda: list(memory_col.find({}, {"_id": 0})))
        mem_str = "\n".join([f"- {r['key']}: {r['value']}" for r in records])
        return {"memory": mem_str}
    except Exception:
        return {"memory": ""}

@app.post("/api/pc_command", dependencies=[Depends(verify_api_key)])
async def pc_command(req: PCCommandReq):
    if pc_col is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        def db_insert():
            pc_col.insert_one({
                "target": req.target,
                "command": req.command,
                "status": req.status,
                "timestamp": datetime.datetime.now()
            })
        await asyncio.to_thread(db_insert)
        return {"success": True, "message": "PC Command queued!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/track_location")
async def track_location(req: LocationTrackRequest):
    try:
        if not WEATHER_API_KEY:
            return {"status": "No Weather API"}

        url = (
            f"http://api.openweathermap.org/data/2.5/weather?lat={req.latitude}"
            f"&lon={req.longitude}&appid={WEATHER_API_KEY}&units=metric&lang=hi"
        )
        weather_res = await asyncio.to_thread(lambda: requests.get(url, timeout=8).json())

        if weather_res.get("cod") != 200:
            return {"status": "Weather Error"}

        city_name = weather_res.get("name", "Unknown Area")
        weather_desc = weather_res["weather"][0]["description"].lower()
        weather_id = weather_res["weather"][0]["id"]

        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone)

        if location_col is not None:
            def db_ops():
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
            await asyncio.to_thread(db_ops)

        is_bad_weather = (
            (200 <= weather_id <= 299) or (500 <= weather_id <= 599) or
            (600 <= weather_id <= 699) or weather_id == 781
        )
        if is_bad_weather:
            return {"alert": f"Boss alert! Aap jahan hain ({city_name}), wahan {weather_desc} hone ki sambhavna hai. Kripya dhyan rakhein!"}

        return {"status": "Saved safely"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def query_location_history(date_query: str):
    try:
        if location_col is None:
            return "Location database abhi available nahi hai boss."

        ist_timezone = pytz.timezone('Asia/Kolkata')
        if date_query.lower() in ["today", "aaj"]:
            target_date = datetime.datetime.now(ist_timezone).strftime('%Y-%m-%d')
        elif date_query.lower() in ["yesterday", "kal"]:
            target_date = (datetime.datetime.now(ist_timezone) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            target_date = date_query

        safe_date = re.escape(target_date)
        records = list(location_col.find({"date": {"$regex": safe_date}}).sort("_id", -1).limit(10))
        if not records:
            return f"Boss, mere paas {target_date} ki koi location history nahi hai."

        history_text = f"Location history for {target_date}:\n"
        for r in records:
            history_text += f"- At {r['time']}, you were near {r['city']}. Weather was {r['weather']}.\n"
        return history_text
    except Exception as e:
        logger.error(f"Location history error: {e}")
        return "Database check karne me issue hua boss."

def perform_web_search(query: str):
    try:
        results = DDGS().text(query, max_results=2)
        if not results:
            return "Web par kuch nahi mila boss."
        summary = "\n".join([f"- {r['title']}: {r['body']}" for r in results])
        return f"Live Web Data for '{query}':\n{summary}"
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return "Search engine mein issue hai boss."

def get_live_weather(location: str):
    if not WEATHER_API_KEY:
        return "Weather API key missing hai boss."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={WEATHER_API_KEY}&units=metric&lang=hi"
        response = requests.get(url, timeout=8).json()
        if response.get("cod") != 200:
            return f"Sorry boss, mujhe {location} ka exact weather data nahi mil pa raha."
        return f"Live Update: {location} mein abhi temp {response['main']['temp']}°C hai aur mausam '{response['weather'][0]['description']}' jaisa hai."
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return "Weather API mein thoda glitch aaya boss."

# =======================================================
# 🛡️ GLOBAL EXCEPTION HANDLER
# =======================================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"💀 Unhandled Exception on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error boss. Team ko notify kar diya gaya hai."}
    )

# =======================================================
# 🔌 STARTUP / SHUTDOWN EVENTS
# =======================================================
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Saarthi AGI Core (Main Backend) booting up...")
    if not api_key:
        logger.error("🚨 GROQ_API_KEY missing — /chat and websocket will fail!")
    if not DEEPSEEK_API_KEY:
        logger.warning("⚠️ DEEPSEEK_API_KEY missing — DeepSeek models won't run.")
    if not OPENROUTER_API_KEY:
        logger.warning("⚠️ OPENROUTER_API_KEY missing — OpenRouter fallback models won't run.")
    if not MONGO_URI:
        logger.error("🚨 MONGO_URI missing — all DB features disabled!")
    if not VECTOR_SERVER_URL:
        logger.warning("⚠️ VECTOR_SERVER_URL missing — Deep Memory Semantic Search will not work!")
    if not N8N_WEBHOOK_URL:
        logger.warning("⚠️ N8N_WEBHOOK_URL missing — Cloud Automation will fail!")
    if not SAARTHI_API_KEY:
        logger.warning("⚠️ SAARTHI_API_KEY not set — sensitive endpoints are UNPROTECTED. Set it in production!")

    asyncio.create_task(cleanup_rate_limiter())

@app.on_event("shutdown")
def shutdown_event():
    if mongo_client:
        mongo_client.close()
        logger.info("🔌 MongoDB connection closed gracefully.")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
