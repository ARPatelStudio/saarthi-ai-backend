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
from bson import ObjectId
import cloudinary
import cloudinary.uploader
import firebase_admin
from firebase_admin import credentials, messaging

# 🚀 BRAIN MODULES
from weather_brain.weather_engine import get_live_weather, analyze_weather_threats
from crypto_brain.crypto_engine import get_crypto_price
from news_brain.news_engine import get_latest_news
from stock_brain.stock_engine import get_stock_price
from devops_brain.devops_engine import check_server_health
from creator_brain.media_engine import generate_image_hf
from mail_brain.mail_engine import check_unread_emails
from iot_brain.iot_engine import trigger_iot_webhook
from publisher_brain.publisher_engine import check_app_status
from studio_brain.studio_engine import check_render_status
from sentinel_brain.sentinel_engine import run_security_scan
from research_brain.research_engine import deep_research

# 🧠 MONGO BRAIN
from mongo_brain.mongo_engine import init_mongo_engine

# ==========================================
# 🪵 LOGS SETUP
# ==========================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

START_TIME = time.time()
latest_remote_command = None

# ==========================================
# 🔥 FIREBASE ADMIN SETUP
# ==========================================
try:
    if os.path.exists("firebase-credentials.json"):
        cred = credentials.Certificate("firebase-credentials.json")
        firebase_admin.initialize_app(cred)
        logger.info("🟢 Firebase Admin SDK Initialized!")
    else:
        logger.warning("⚠️ firebase-credentials.json not found!")
except Exception as e:
    logger.error(f"🔴 Firebase Admin Error: {e}")

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL")
FCM_TARGET_TOKEN = os.getenv("FCM_TARGET_TOKEN")
NEON_DB_URL = os.getenv("NEON_DB_URL") 
VECTOR_SERVER_URL = os.getenv("VECTOR_SERVER_URL")

app = FastAPI(title="Saarthi AGI Core", version="52.0.0")

ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS", "*")
if ALLOWED_ORIGINS_ENV.strip() == "*":
    origins = ["*"]; allow_creds = False
else:
    origins = [o.strip() for o in ALLOWED_ORIGINS_ENV.split(",")]; allow_creds = True

app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=allow_creds, allow_methods=["*"], allow_headers=["*"])

RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX_REQUESTS = 40
_request_log = defaultdict(deque)

@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    dq = _request_log[client_ip]
    while dq and now - dq[0] > RATE_LIMIT_WINDOW: dq.popleft()
    if len(dq) >= RATE_LIMIT_MAX_REQUESTS: return JSONResponse(status_code=429, content={"error": "Rate limit exceeded."})
    dq.append(now)
    return await call_next(request)

async def cleanup_rate_limiter():
    while True:
        await asyncio.sleep(300)
        try:
            now = time.time()
            dead_ips = [ip for ip, dq in list(_request_log.items()) if not dq or now - dq[-1] > RATE_LIMIT_WINDOW * 2]
            for ip in dead_ips: _request_log.pop(ip, None)
        except Exception: pass

# ==========================================
# 🔑 LLM PROVIDERS SETUP
# ==========================================
api_key = os.getenv("GROQ_API_KEY")
client = AsyncGroq(api_key=api_key) if api_key else None

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

deepseek_client, openrouter_client = None, None
try:
    from openai import AsyncOpenAI
    if DEEPSEEK_API_KEY: deepseek_client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com/v1")
    if OPENROUTER_API_KEY: openrouter_client = AsyncOpenAI(api_key=OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")
except ImportError: pass

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
SAARTHI_API_KEY = os.getenv("SAARTHI_API_KEY")

async def verify_api_key(x_api_key: str = Header(default=None)):
    if SAARTHI_API_KEY and x_api_key != SAARTHI_API_KEY: raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# ==========================================
# 💾 MONGO BRAIN SETUP
# ==========================================
mongo_client, location_col, memory_col, pc_col, deep_mem_col, pc_status_col = init_mongo_engine()

# 📦 PYDANTIC MODELS
class ChatRequest(BaseModel): message: str = Field(...); android_memory: str = Field(default=""); history: List[dict] = Field(default_factory=list)
class LocationTrackRequest(BaseModel): latitude: float; longitude: float
class MemoryRequest(BaseModel): key: str; value: str
class PCCommandReq(BaseModel): target: str; command: str; status: str = "pending"
class DeepMemorySaveReq(BaseModel): mem_type: str; content: str; location: str; date: str; time: str; custom_name: str = "New Memory"
class DeepMemoryActionReq(BaseModel): mem_id: str; action: str; new_name: str = ""
class PCStatusReq(BaseModel): battery: int; ram: int; is_locked: bool
class ChatResponse(BaseModel): reply: str; action: str = "NONE"; action_data1: str = ""; action_data2: str = ""; action_data3: str = ""; history: List[dict] = Field(default_factory=list)
class SynthesizeReq(BaseModel): text: str; voice: str = Field(default="papa_vocals")
class RemoteCommandPayload(BaseModel): target_user: str; command: str; type: str; sender: str

@app.get("/")
async def root(): return {"status": "🟢 Saarthi Omni-Core (Microservice Mode) Online!"}

@app.get("/health")
async def health_check():
    mongo_ok = False
    if mongo_client:
        try: mongo_client.admin.command('ping'); mongo_ok = True
        except Exception: pass
    return {"status": "ok", "mongo_connected": mongo_ok, "vector_server_linked": bool(VECTOR_SERVER_URL)}

class ConnectionManager:
    def __init__(self): self.active_connections: List[WebSocket] = []
    async def connect(self, websocket: WebSocket): await websocket.accept(); self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections: self.active_connections.remove(websocket)
    async def send_json(self, message: dict, websocket: WebSocket):
        try: await websocket.send_json(message)
        except Exception: pass
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try: await connection.send_text(message)
            except Exception: pass

manager = ConnectionManager()

saarthi_tools = [
    {"type": "function", "function": {"name": "save_vision_to_memory", "description": "Saves current visual frame.", "parameters": {"type": "object", "properties": {"context_tag": {"type": "string"}}, "required": ["context_tag"]}}},
    {"type": "function", "function": {"name": "perform_web_search", "description": "Search internet.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_live_weather", "description": "Fetch weather.", "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]}}},
    {"type": "function", "function": {"name": "query_location_history", "description": "Find previous locations.", "parameters": {"type": "object", "properties": {"date_query": {"type": "string"}}, "required": ["date_query"]}}},
    {"type": "function", "function": {"name": "search_deep_memory", "description": "Search permanent memory.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "read_current_screen", "description": "Read Android screen.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "execute_universal_command", "description": "Android device control.", "parameters": {"type": "object", "properties": {"category": {"type": "string", "enum": ["APP", "SETTING", "MEDIA", "COMMUNICATE", "SYSTEM", "VISION"]}, "target_name": {"type": "string"}, "action_value": {"type": "string"}}, "required": ["category", "target_name"]}}},
    {"type": "function", "function": {"name": "trigger_cloud_automation", "description": "Trigger n8n workflow.", "parameters": {"type": "object", "properties": {"workflow_name": {"type": "string"}, "payload_json": {"type": "string"}}, "required": ["workflow_name", "payload_json"]}}},
    {"type": "function", "function": {"name": "manage_finance_database", "description": "Manage Neon DB budgets.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["GET_BUDGET_STATUS", "SET_BUDGET", "MODIFY_BUDGET"]}, "amount": {"type": "number"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "get_crypto_price", "description": "Get crypto price.", "parameters": {"type": "object", "properties": {"coin_name": {"type": "string"}, "currency": {"type": "string"}}, "required": ["coin_name"]}}},
    {"type": "function", "function": {"name": "get_latest_news", "description": "Get news.", "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]}}},
    {"type": "function", "function": {"name": "get_stock_price", "description": "Get Indian stock price.", "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}}},
    {"type": "function", "function": {"name": "check_server_health", "description": "Check cloud servers.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "generate_image_hf", "description": "Generate AI image.", "parameters": {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}}},
    {"type": "function", "function": {"name": "check_unread_emails", "description": "Check Gmail.", "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "trigger_iot_webhook", "description": "Trigger IoT device.", "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}, "action": {"type": "string"}}, "required": ["device_name", "action"]}}},
    {"type": "function", "function": {"name": "check_app_status", "description": "Check Uptodown/KDP status.", "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}, "platform": {"type": "string", "enum": ["uptodown", "kdp"]}}, "required": ["app_name"]}}},
    {"type": "function", "function": {"name": "check_render_status", "description": "Check AI render status.", "parameters": {"type": "object", "properties": {"project_name": {"type": "string"}}, "required": ["project_name"]}}},
    {"type": "function", "function": {"name": "run_security_scan", "description": "Run Sentinel scan.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "deep_research", "description": "Perform deep web research.", "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]}}}
]

def extract_json_object(raw_text: str):
    if not raw_text: return None
    decoder = json.JSONDecoder()
    idx, length = 0, len(raw_text)
    while idx < length:
        start = raw_text.find('{', idx)
        if start == -1: return None
        try: return decoder.raw_decode(raw_text, start)[0]
        except json.JSONDecodeError: idx = start + 1
    return None

def build_apology_json(reply_text: str, thought: str = "Internal fallback triggered", emotion: str = "apologetic") -> str:
    return json.dumps({"inner_monologue": thought, "emotion": emotion, "reply": reply_text})

def trigger_n8n_webhook(workflow_name: str, payload_str: str):
    if not N8N_WEBHOOK_URL: return "Boss, n8n Webhook URL is missing."
    try:
        payload = json.loads(payload_str) if "{" in payload_str else {"raw_text": payload_str}
        res = requests.post(N8N_WEBHOOK_URL, json={"workflow": workflow_name, "data": payload, "timestamp": datetime.datetime.now().isoformat()}, timeout=10)
        return f"Cloud automation '{workflow_name}' triggered!" if res.status_code == 200 else f"n8n failed with status {res.status_code}."
    except Exception: return "Server down."

def execute_finance_db_action(action: str, amount: float = 0.0):
    raw_url = os.getenv("NEON_DB_URL", "").strip().strip('"').strip("'")
    if not raw_url or not raw_url.startswith("postgres"): return "Boss, Neon DB link error."
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(raw_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if action == "GET_BUDGET_STATUS":
            cursor.execute("SELECT amount FROM jarvis_budgets WHERE user_id = 1 AND category_id = (SELECT id FROM jarvis_expense_categories WHERE name = 'Overall' LIMIT 1) AND period_month = EXTRACT(MONTH FROM CURRENT_DATE)::INT AND period_year = EXTRACT(YEAR FROM CURRENT_DATE)::INT;")
            res_limit = cursor.fetchone()
            budget_limit = float(res_limit['amount']) if res_limit else 0.0
            cursor.execute("SELECT SUM(amount) as total_spent FROM jarvis_expenses WHERE user_id = 1 AND is_deleted = FALSE AND date_trunc('month', transaction_date) = date_trunc('month', CURRENT_DATE);")
            res_spent = cursor.fetchone()
            total_spent = float(res_spent['total_spent']) if res_spent and res_spent['total_spent'] else 0.0
            conn.close()
            return f"Boss, budget limit is {budget_limit}. Total spent is {total_spent}. Remaining is {budget_limit - total_spent}."
        elif action == "SET_BUDGET":
            cursor.execute("INSERT INTO jarvis_budgets (user_id, category_id, amount, period_month, period_year) VALUES (1, (SELECT id FROM jarvis_expense_categories WHERE name = 'Overall' LIMIT 1), %s, EXTRACT(MONTH FROM CURRENT_DATE)::INT, EXTRACT(YEAR FROM CURRENT_DATE)::INT) ON CONFLICT (user_id, category_id, period_month, period_year) DO UPDATE SET amount = EXCLUDED.amount, updated_at = NOW();", (amount,))
            conn.commit(); conn.close()
            return f"Boss, monthly budget set to {amount}."
        elif action == "MODIFY_BUDGET":
            cursor.execute("INSERT INTO jarvis_budgets (user_id, category_id, amount, period_month, period_year) VALUES (1, (SELECT id FROM jarvis_expense_categories WHERE name = 'Overall' LIMIT 1), %s, EXTRACT(MONTH FROM CURRENT_DATE)::INT, EXTRACT(YEAR FROM CURRENT_DATE)::INT) ON CONFLICT (user_id, category_id, period_month, period_year) DO UPDATE SET amount = jarvis_budgets.amount + EXCLUDED.amount, updated_at = NOW() RETURNING amount;", (amount,))
            new_budget = cursor.fetchone()['amount']
            conn.commit(); conn.close()
            return f"Boss, budget modified by {amount}. New limit is {new_budget}."
    except ImportError: return "psycopg2 missing."
    except Exception as e: return f"Neon DB error: {str(e)}"

def perform_web_search(query: str):
    try:
        results = DDGS().text(query, max_results=2)
        return f"Live Web Data for '{query}':\n" + "\n".join([f"- {r['title']}: {r['body']}" for r in results]) if results else "Kuch nahi mila."
    except Exception: return "Search engine issue."

def query_location_history(date_query: str):
    try:
        if not location_col: return "Database unavailable."
        target_date = datetime.datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d') if date_query.lower() in ["today", "aaj"] else date_query
        records = list(location_col.find({"date": {"$regex": re.escape(target_date)}}).sort("_id", -1).limit(10))
        if not records: return f"No history for {target_date}."
        return f"Location history:\n" + "\n".join([f"- At {r['time']}, near {r['city']}. Weather: {r['weather']}." for r in records])
    except Exception: return "Database issue."

LLM_CALL_TIMEOUT = 25
MAX_IMAGE_B64_CHARS = 6_000_000

async def generate_jarvis_response(user_msg: str, android_memory: str = "", image_base64: str = None, history: list = None) -> dict:
    if history is None: history = []
    if image_base64 and len(image_base64) > MAX_IMAGE_B64_CHARS: return {"type": "ai_response", "reply": "Boss, image bhaari hai.", "action": "NONE", "history": history}

    system_prompt = {
        "role": "system",
        "content": (
            "You are Saarthi (aka Jarvis), an AGI entity. Speak naturally in Hinglish. Address user as 'Boss'.\n"
            "OUTPUT STRICTLY AS JSON: {\"inner_monologue\": \"...\", \"emotion\": \"...\", \"reply\": \"...\"}\n"
            f"Extra Context: {android_memory}"
        )
    }

    messages = [system_prompt] + history
    action_type, action_data1, action_data2, action_data3 = "NONE", "", "", ""
    AVAILABLE_MODELS = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3.6-27b", "deepseek-v4-flash"]

    try:
        if image_base64:
            vision_messages = messages + [{"role": "user", "content": [{"type": "text", "text": user_msg}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}]}]
            try:
                response = await asyncio.wait_for(client.chat.completions.create(model="qwen/qwen3.6-27b", messages=vision_messages, max_tokens=800, temperature=0.7), timeout=LLM_CALL_TIMEOUT)
                raw_reply = response.choices[0].message.content
            except Exception: raw_reply = build_apology_json("Vision system down.")
            if raw_reply and any(k in user_msg.lower() for k in ["save", "yaad"]): action_type, action_data1 = "SAVE_VISION", "Requested vision save"
        else:
            messages.append({"role": "user", "content": user_msg})
            response_message, used_model, client_used = None, None, None

            for model_name in AVAILABLE_MODELS:
                try:
                    if "deepseek" in model_name and deepseek_client:
                        response = await asyncio.wait_for(deepseek_client.chat.completions.create(model=model_name, messages=messages, tools=saarthi_tools if "reasoner" not in model_name else None, max_tokens=600, temperature=0.7), timeout=LLM_CALL_TIMEOUT)
                        client_used = deepseek_client
                    elif client:
                        response = await asyncio.wait_for(client.chat.completions.create(model=model_name, messages=messages, tools=saarthi_tools, tool_choice="auto", max_tokens=600, temperature=0.7), timeout=LLM_CALL_TIMEOUT)
                        client_used = client
                    response_message = response.choices[0].message
                    used_model = model_name
                    break
                except Exception: continue

            if not response_message: raise Exception("All models failed!")

            if getattr(response_message, "tool_calls", None):
                messages.append({"role": "assistant", "content": response_message.content or "", "tool_calls": [{"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in response_message.tool_calls]})
                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                    tool_result = "Action processed."
                    
                    if func_name == "save_vision_to_memory": action_type, action_data1 = "SAVE_VISION", args.get("context_tag", "Vision Memory")
                    elif func_name == "perform_web_search": tool_result = await asyncio.to_thread(perform_web_search, args.get("query", ""))
                    elif func_name == "get_live_weather": tool_result = await asyncio.to_thread(get_live_weather, args.get("location", ""), WEATHER_API_KEY)
                    elif func_name == "get_crypto_price": tool_result = await asyncio.to_thread(get_crypto_price, args.get("coin_name", "bitcoin"), args.get("currency", "inr"))
                    elif func_name == "get_latest_news": tool_result = await asyncio.to_thread(get_latest_news, args.get("topic", "world"))
                    elif func_name == "get_stock_price": tool_result = await asyncio.to_thread(get_stock_price, args.get("symbol", "RELIANCE.NS"))
                    elif func_name == "check_server_health": tool_result = await asyncio.to_thread(check_server_health)
                    elif func_name == "generate_image_hf": tool_result = await asyncio.to_thread(generate_image_hf, args.get("prompt", ""))
                    elif func_name == "check_unread_emails": tool_result = await asyncio.to_thread(check_unread_emails, args.get("limit", 3))
                    elif func_name == "trigger_iot_webhook": tool_result = await asyncio.to_thread(trigger_iot_webhook, args.get("device_name", ""), args.get("action", ""))
                    elif func_name == "check_app_status": tool_result = await asyncio.to_thread(check_app_status, args.get("app_name", ""), args.get("platform", "uptodown"))
                    elif func_name == "check_render_status": tool_result = await asyncio.to_thread(check_render_status, args.get("project_name", ""))
                    elif func_name == "run_security_scan": tool_result = await asyncio.to_thread(run_security_scan)
                    elif func_name == "deep_research": tool_result = await asyncio.to_thread(deep_research, args.get("topic", ""))
                    elif func_name == "query_location_history": tool_result = await asyncio.to_thread(query_location_history, args.get("date_query", ""))
                    elif func_name == "search_deep_memory": tool_result = await asyncio.to_thread(search_deep_memory, args.get("query", ""))
                    elif func_name == "read_current_screen": action_type, tool_result = "READ_SCREEN", "Trigger sent."
                    elif func_name == "execute_universal_command": action_type, action_data1, action_data2 = f"UNIVERSAL_{args.get('category', 'SYSTEM')}", args.get("target_name", ""), args.get("action_value", "")
                    elif func_name == "trigger_cloud_automation": tool_result = await asyncio.to_thread(trigger_n8n_webhook, args.get("workflow_name", ""), args.get("payload_json", "{}"))
                    elif func_name == "manage_finance_database": tool_result = await asyncio.to_thread(execute_finance_db_action, args.get("action", "GET_BUDGET"), float(args.get("amount", 0.0)))
                    
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": tool_result})

                try:
                    final_response = await asyncio.wait_for(client_used.chat.completions.create(model=used_model, messages=messages, max_tokens=600, temperature=0.7), timeout=LLM_CALL_TIMEOUT)
                    raw_reply = final_response.choices[0].message.content
                except Exception: raw_reply = build_apology_json("Glitch aaya boss.")
            else:
                raw_reply = response_message.content

        final_reply = raw_reply
        try:
            agi_data = extract_json_object(raw_reply)
            if agi_data: final_reply = agi_data.get("reply", raw_reply)
        except Exception: pass

        history = history + [{"role": "user", "content": user_msg}, {"role": "assistant", "content": final_reply}]
        return {"type": "ai_response", "reply": final_reply, "action": action_type, "action_data1": action_data1, "action_data2": action_data2, "action_data3": action_data3, "history": history[-12:]}
    except Exception: return {"type": "ai_response", "reply": "Glitch aaya boss.", "action": "NONE", "history": history}

# =======================================================
# 📸 MICROSERVICE: DEEP MEMORY & VISION (HTTP CALL TO RENDER 2)
# =======================================================
async def save_vision_memory(image_b64: str, user_text: str, response_data: dict):
    if deep_mem_col is None: return
    try:
        upload_result = await asyncio.to_thread(cloudinary.uploader.upload, f"data:image/jpeg;base64,{image_b64}", folder="saarthi_vision")
        image_url = upload_result.get("secure_url")
        live_time = datetime.datetime.now(pytz.timezone('Asia/Kolkata'))
        mem_content = f"Tag: '{response_data.get('action_data1', '')}' | User: '{user_text}' | Jarvis: '{response_data.get('reply', '')}'"

        doc_res = await asyncio.to_thread(deep_mem_col.insert_one, {
            "type": "visual", "content": mem_content, "url": image_url,
            "custom_name": "Requested Vision Memory", "location": "Live Context",
            "date": live_time.strftime('%Y-%m-%d'), "time": live_time.strftime('%I:%M %p'),
            "timestamp": datetime.datetime.now(), "is_pinned": False
        })
        if VECTOR_SERVER_URL:
            try: await asyncio.to_thread(requests.post, f"{VECTOR_SERVER_URL}/upsert", json={"id": str(doc_res.inserted_id), "text": mem_content, "metadata": {"content": mem_content, "url": image_url, "type": "visual"}}, headers={"x-api-key": SAARTHI_API_KEY} if SAARTHI_API_KEY else {}, timeout=10)
            except Exception as ve_err: logger.error(f"🔴 Vector Brain Error: {ve_err}")
    except Exception as e: logger.error(f"Save Vision Error: {e}")

@app.post("/api/deep_memory/save", dependencies=[Depends(verify_api_key)])
async def save_deep_memory(req: DeepMemorySaveReq):
    if deep_mem_col is None: raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        doc_res = await asyncio.to_thread(deep_mem_col.insert_one, {"type": req.mem_type, "content": req.content, "custom_name": req.custom_name, "location": req.location, "date": req.date, "time": req.time, "timestamp": datetime.datetime.now(), "is_pinned": False})
        if VECTOR_SERVER_URL:
            try: await asyncio.to_thread(requests.post, f"{VECTOR_SERVER_URL}/upsert", json={"id": str(doc_res.inserted_id), "text": req.content, "metadata": {"content": req.content, "type": req.mem_type}}, headers={"x-api-key": SAARTHI_API_KEY} if SAARTHI_API_KEY else {}, timeout=10)
            except Exception: pass
        return {"success": True, "message": "Saved to DB + Vector Index"}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/deep_memory/action", dependencies=[Depends(verify_api_key)])
async def action_deep_memory(req: DeepMemoryActionReq):
    if deep_mem_col is None: raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        obj_id = ObjectId(req.mem_id)
        if req.action == "delete":
            await asyncio.to_thread(deep_mem_col.delete_one, {"_id": obj_id})
            if VECTOR_SERVER_URL: await asyncio.to_thread(requests.post, f"{VECTOR_SERVER_URL}/delete", json={"id": req.mem_id}, headers={"x-api-key": SAARTHI_API_KEY} if SAARTHI_API_KEY else {}, timeout=10)
        elif req.action == "pin":
            doc = await asyncio.to_thread(deep_mem_col.find_one, {"_id": obj_id})
            if doc: await asyncio.to_thread(deep_mem_col.update_one, {"_id": obj_id}, {"$set": {"is_pinned": not doc.get("is_pinned", False)}})
        elif req.action == "rename":
            await asyncio.to_thread(deep_mem_col.update_one, {"_id": obj_id}, {"$set": {"custom_name": req.new_name}})
        return {"success": True}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

def search_deep_memory(query: str):
    try:
        results_str = []
        if VECTOR_SERVER_URL:
            try:
                res = requests.post(f"{VECTOR_SERVER_URL}/search", json={"query": query, "top_k": 3}, headers={"x-api-key": SAARTHI_API_KEY} if SAARTHI_API_KEY else {}, timeout=10)
                if res.status_code == 200:
                    for match in res.json().get('matches', []):
                        if match.get('score', 0) > 0.4: results_str.append(f"- [SEMANTIC MATCH] {match.get('metadata', {}).get('content', '')}")
            except Exception: pass
        if deep_mem_col is not None:
            regex_query = "|".join([re.escape(w) for w in query.split() if w.strip()]) or re.escape(query)
            records = list(deep_mem_col.find({"content": {"$regex": regex_query, "$options": "i"}}).sort("timestamp", -1).limit(4))
            for r in records: results_str.append(f"- [{r.get('type', 'TEXT').upper()}] {r.get('date', '')}. Detail: {r.get('content', '')}")
        if not results_str: return "Deep memory mein kuch nahi mila boss."
        return "Deep Memory Results:\n" + "\n".join(list(set(results_str)))
    except Exception: return "Memory error boss."

@app.get("/api/deep_memory/get_all", dependencies=[Depends(verify_api_key)])
async def get_all_deep_memory(skip: int = 0, limit: int = 50):
    if deep_mem_col is None: raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        records = await asyncio.to_thread(lambda: list(deep_mem_col.find().sort("timestamp", -1).skip(skip).limit(min(max(limit, 1), 200))))
        for r in records: r["_id"] = str(r["_id"])
        total = await asyncio.to_thread(deep_mem_col.count_documents, {})
        return {"memories": records, "total": total, "skip": skip, "limit": limit}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

# =======================================================
# 🎙️ VAD & AUDIO LOGIC
# =======================================================
def get_max_amplitude(pcm_bytes):
    count = len(pcm_bytes) // 2
    if count == 0: return 0
    samples = struct.unpack(f"<{count}h", pcm_bytes[:count * 2])
    return max(abs(s) for s in samples)

async def process_voice_buffer(audio_bytes: bytes, image_b64, websocket: WebSocket, session_history: list) -> list:
    wav_io = io.BytesIO()
    with wave.open(wav_io, 'wb') as wav_file:
        wav_file.setnchannels(1); wav_file.setsampwidth(2); wav_file.setframerate(16000); wav_file.writeframes(audio_bytes)
    wav_io.seek(0)
    try:
        transcription = await asyncio.wait_for(client.audio.transcriptions.create(file=("audio.wav", wav_io.read(), "audio/wav"), model="whisper-large-v3", response_format="json"), timeout=LLM_CALL_TIMEOUT)
        user_text = transcription.text.strip()
        if not user_text: return session_history
        logger.info(f"🗣️ User Said (Live): {user_text}")
        response_data = await generate_jarvis_response(user_msg=user_text, image_base64=image_b64, history=session_history)
        session_history = response_data.pop("history", session_history)
        await manager.send_json(response_data, websocket)
        if response_data.get("action") == "SAVE_VISION" and image_b64: await save_vision_memory(image_b64, user_text, response_data)
    except Exception as e: logger.error(f"🔴 STT Error: {e}")
    return session_history

@app.websocket("/ws/live_chat")
async def live_chat_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    audio_buffer = bytearray()
    is_speaking, last_voice_time, latest_received_image, session_history, authenticated = False, time.time(), None, [], SAARTHI_API_KEY is None
    try:
        while True:
            raw_data = await websocket.receive_text()
            try: payload = json.loads(raw_data)
            except Exception: continue
            msg_type = payload.get("type")
            if msg_type == "heartbeat":
                await manager.send_json({"type": "heartbeat_ack", "status": "alive"}, websocket); continue
            if msg_type == "init":
                token = payload.get("token", "")
                if SAARTHI_API_KEY and token == SAARTHI_API_KEY: authenticated = True
                elif SAARTHI_API_KEY: await websocket.close(code=1008); return
                await manager.send_json({"type": "system", "reply": "Connection established.", "action": "NONE"}, websocket); continue
            if not authenticated: continue

            if msg_type == "audio_stream":
                b64_audio, b64_image = payload.get("data"), payload.get("image_data")
                if b64_image and len(b64_image) <= MAX_IMAGE_B64_CHARS: latest_received_image = b64_image
                if b64_audio:
                    try: pcm_bytes = base64.b64decode(b64_audio)
                    except Exception: continue
                    amplitude = get_max_amplitude(pcm_bytes)
                    audio_buffer.extend(pcm_bytes)
                    if amplitude > 1500: is_speaking, last_voice_time = True, time.time()
                    if not is_speaking and len(audio_buffer) > 32000: audio_buffer.clear()
                    
                    if ((is_speaking and (time.time() - last_voice_time > 1.5)) or len(audio_buffer) > 16000 * 2 * 20) and len(audio_buffer) > 16000:
                        is_speaking = False; buffer_copy = bytes(audio_buffer); audio_buffer.clear()
                        session_history = await process_voice_buffer(buffer_copy, latest_received_image, websocket, session_history)
                        latest_received_image = None
            elif msg_type == "text_command":
                user_text, b64_image = payload.get("data"), payload.get("image_data")
                if user_text:
                    response_data = await generate_jarvis_response(user_msg=user_text, image_base64=b64_image, history=session_history)
                    session_history = response_data.pop("history", session_history)
                    await manager.send_json(response_data, websocket)
                    if response_data.get("action") == "SAVE_VISION" and b64_image: await save_vision_memory(b64_image, user_text, response_data)
    except WebSocketDisconnect: manager.disconnect(websocket)
    except Exception: manager.disconnect(websocket)

@app.post("/synthesize")
async def synthesize_speech(req: SynthesizeReq):
    try:
        text, voice_key = req.text.strip(), req.voice
        model_path = os.path.abspath(f"{voice_key}.onnx")
        if model_path.startswith(os.path.abspath(os.getcwd())) and os.path.isfile(model_path):
            out_path = tempfile.mktemp(suffix=".wav")
            await asyncio.to_thread(subprocess.run, ["piper", "--model", model_path, "--output_file", out_path], input=text.encode("utf-8"), timeout=30, check=True)
            with open(out_path, "rb") as f: audio_bytes = f.read()
            if os.path.exists(out_path): os.remove(out_path)
            return Response(content=audio_bytes, media_type="audio/wav")
        else:
            from gtts import gTTS
            def run_gtts():
                tts, fp = gTTS(text=text, lang='hi'), io.BytesIO()
                tts.write_to_fp(fp); fp.seek(0)
                return fp.read()
            return Response(content=await asyncio.to_thread(run_gtts), media_type="audio/mpeg")
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_with_saarthi(request: ChatRequest):
    res = await generate_jarvis_response(request.message, request.android_memory, history=request.history)
    return ChatResponse(reply=res["reply"], action=res["action"], action_data1=res.get("action_data1", ""), action_data2=res.get("action_data2", ""), action_data3=res.get("action_data3", ""), history=res.get("history", []))

# =======================================================
# 💾 SYSTEM ENDPOINTS
# =======================================================
@app.get("/api/check_update")
async def check_update(): return {"latest_version_code": int(os.getenv("APP_VERSION_CODE", "3")), "version_name": os.getenv("APP_VERSION_NAME", "Jarvis Mark 3.1"), "changelog": "Microservice Vector Brain Separated", "download_url": os.getenv("APP_DOWNLOAD_URL", "")}

@app.post("/api/pc_status", dependencies=[Depends(verify_api_key)])
async def update_pc_status(req: PCStatusReq):
    if pc_status_col is None: raise HTTPException(status_code=503, detail="Database unavailable")
    await asyncio.to_thread(pc_status_col.update_one, {"device": "primary_pc"}, {"$set": {"battery": req.battery, "ram": req.ram, "is_locked": req.is_locked, "timestamp": datetime.datetime.now()}}, upsert=True)
    return {"success": True}

@app.get("/api/pc_status", dependencies=[Depends(verify_api_key)])
async def get_pc_status():
    if pc_status_col is None: return {"battery": 12, "ram": 95, "is_locked": False}
    status = await asyncio.to_thread(pc_status_col.find_one, {"device": "primary_pc"}, {"_id": 0})
    if status: status["timestamp"] = str(status["timestamp"]); return status
    return {"battery": 12, "ram": 95, "is_locked": False}

@app.post("/api/save_memory", dependencies=[Depends(verify_api_key)])
async def save_memory(req: MemoryRequest):
    if memory_col is None: raise HTTPException(status_code=503, detail="Database unavailable")
    await asyncio.to_thread(memory_col.update_one, {"key": req.key}, {"$set": {"value": req.value}}, upsert=True)
    return {"status": "Memory Saved Boss!"}

@app.get("/api/get_memory", dependencies=[Depends(verify_api_key)])
async def get_memory():
    if memory_col is None: return {"memory": ""}
    records = await asyncio.to_thread(lambda: list(memory_col.find({}, {"_id": 0})))
    return {"memory": "\n".join([f"- {item['key']}: {item['value']}" for item in records])}

@app.post("/api/pc_command", dependencies=[Depends(verify_api_key)])
async def pc_command(req: PCCommandReq):
    if pc_col is None: raise HTTPException(status_code=503, detail="Database unavailable")
    await asyncio.to_thread(pc_col.insert_one, {"target": req.target, "command": req.command, "status": req.status, "timestamp": datetime.datetime.now()})
    return {"success": True}

@app.post("/api/track_location")
async def track_location(req: LocationTrackRequest):
    try:
        ist_timezone = pytz.timezone('Asia/Kolkata')
        live_time = datetime.datetime.now(ist_timezone)
        alerts_detected = []
        
        city_name, weather_desc, weather_alerts = await asyncio.to_thread(analyze_weather_threats, req.latitude, req.longitude, WEATHER_API_KEY)
        alerts_detected.extend(weather_alerts)

        try:
            yesterday_str = (live_time - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
            usgs_url = (f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&latitude={req.latitude}&longitude={req.longitude}&maxradiuskm=100&minmagnitude=4.5&starttime={yesterday_str}")
            usgs_res = await asyncio.to_thread(lambda: requests.get(usgs_url, timeout=8).json())
            features = usgs_res.get("features", [])
            if features:
                latest_quake = features[0]["properties"]
                alerts_detected.append(f"Aapke 100km ke daayre mein ({latest_quake.get('place')}) {latest_quake.get('mag')} magnitude ka bhukamp detect hua hai")
        except Exception: pass

        if location_col is not None:
            def db_ops():
                location_col.insert_one({"date": live_time.strftime('%Y-%m-%d'), "time": live_time.strftime('%I:%M %p'), "latitude": req.latitude, "longitude": req.longitude, "city": city_name, "weather": weather_desc, "threat_level": len(alerts_detected)})
                if location_col.count_documents({}) > 10000: location_col.delete_one({"_id": location_col.find().sort("_id", 1).limit(1)[0]["_id"]})
            await asyncio.to_thread(db_ops)

        if alerts_detected: return {"alert": f"Boss alert! Aapki live location ({city_name}) par: {' aur '.join(alerts_detected)}.", "status": "DANGER"}
        return {"status": "Safe. Route is clear."}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/remote_command")
async def handle_remote_command(payload: RemoteCommandPayload, x_api_key: str = Header(None)):
    global latest_remote_command
    if SAARTHI_API_KEY and x_api_key != SAARTHI_API_KEY: raise HTTPException(status_code=401, detail="Unauthorized Boss")
    latest_remote_command = {"command": payload.command, "type": payload.type, "sender": payload.sender}
    alert_msg = {"type": "ai_response", "reply": payload.command, "action": payload.type, "action_data1": "", "action_data2": ""}
    response_logs = []
    try:
        await manager.broadcast(json.dumps(alert_msg))
        response_logs.append("WebSocket Broadcast: Success")
        if FCM_TARGET_TOKEN:
            try: response_logs.append(f"FCM Push: Success (ID: {messaging.send(messaging.Message(data={'command': payload.command, 'type': payload.type, 'sender': payload.sender}, token=FCM_TARGET_TOKEN))})")
            except Exception as fcm_err: response_logs.append(f"FCM Push Failed: {fcm_err}")
        return {"status": "success", "message": "Alert queued", "details": response_logs}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/get_remote_command")
async def fetch_remote_command(x_api_key: str = Header(None)):
    global latest_remote_command
    if SAARTHI_API_KEY and x_api_key != SAARTHI_API_KEY: raise HTTPException(status_code=401, detail="Unauthorized")
    if latest_remote_command:
        cmd = latest_remote_command; latest_remote_command = None
        return {"has_command": True, "data": cmd}
    return {"has_command": False}

class WhatsAppIncomingReq(BaseModel):
    sender_name: str
    message: str

@app.post("/api/whatsapp_reply")
async def whatsapp_auto_reply(req: WhatsAppIncomingReq, x_api_key: str = Header(None)):
    if SAARTHI_API_KEY and x_api_key != SAARTHI_API_KEY: raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        msg = req.message.strip().lower()
        if msg in ["hmm", "ok", "k", "acha", "thik", "ha", "haan", "👍", "🙏"] or len(msg) < 2: return {"reply": "IGNORE"}
        sys_prompt = f"You are Jarvis. Boss is busy. Contact '{req.sender_name}' sent: '{req.message}'. Reply shortly in Hinglish on behalf of Boss. If spam/promo, output exactly: IGNORE"
        response = await asyncio.wait_for(client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": sys_prompt}], max_tokens=100, temperature=0.6), timeout=15)
        ai_reply = response.choices[0].message.content.strip()
        return {"reply": "IGNORE"} if "IGNORE" in ai_reply.upper() or not ai_reply else {"reply": ai_reply}
    except Exception: return {"reply": "IGNORE"}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"💀 Unhandled Exception: {exc}")
    return JSONResponse(status_code=500, content={"error": "Internal server error boss."})

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Saarthi Omni-Brain Architecture booting up...")
    asyncio.create_task(cleanup_rate_limiter())

@app.on_event("shutdown")
def shutdown_event():
    if mongo_client: mongo_client.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
