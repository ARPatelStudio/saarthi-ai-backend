import os
import logging
import certifi
from pymongo import MongoClient

logger = logging.getLogger(__name__)

def init_mongo_engine():
    """Initializes and returns MongoDB client and all collections."""
    mongo_uri = os.getenv("MONGO_URI")
    mongo_client = None
    location_col = memory_col = pc_col = deep_mem_col = pc_status_col = None

    if mongo_uri:
        try:
            # 1. Connect to Mongo
            mongo_client = MongoClient(mongo_uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
            db = mongo_client["saarthi_db"]
            
            # 2. Define Collections
            location_col = db["location_history"]
            memory_col = db["permanent_memory"]
            pc_col = db["device_commands"]
            deep_mem_col = db["deep_memory"]
            pc_status_col = db["pc_status"]
            
            # 3. Verify Connection
            mongo_client.admin.command('ping')
            
            # 4. Set Indexes for fast searching
            deep_mem_col.create_index("timestamp")
            location_col.create_index("date")
            
            logger.info("🟢 Mongo Brain: Database Connected & Indexes Verified Successfully!")
        except Exception as e:
            logger.error(f"🔴 Mongo Brain Connection Error: {e}")
            mongo_client = None
    else:
        logger.warning("🚨 MONGO_URI missing from environment variables! DB features disabled.")

    return mongo_client, location_col, memory_col, pc_col, deep_mem_col, pc_status_col
