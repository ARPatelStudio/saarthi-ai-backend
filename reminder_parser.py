import os
import json
import logging
import datetime
import pytz
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Initialize Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')

def parse_and_save_reminder(command: str, user_id: str, reminders_col, timezone: str = 'Asia/Kolkata'):
    """Parses natural language and saves the structured reminder to MongoDB."""
    now_local = datetime.datetime.now(pytz.timezone(timezone)).strftime('%Y-%m-%d %H:%M:%S')
    
    prompt = f"""
    Current Time in {timezone}: {now_local}
    Analyze the user's reminder command: "{command}"
    Return ONLY a JSON response matching this exact structure:
    {{
        "title": "Cleaned task name in Hindi/English (e.g., 'Bill pay karna')",
        "isRecurring": true or false,
        "rrule": "Standard RFC 5545 string if recurring (e.g., 'FREQ=MONTHLY;BYMONTHDAY=5'), else null",
        "scheduledAt": "ISO-8601 UTC Date string for the FIRST occurrence (e.g., '2026-10-25T09:00:00Z')",
        "priority": 1 to 5
    }}
    """
    
    try:
        response = model.generate_content(prompt)
        raw_json = response.text.replace('```json', '').replace('```', '').strip()
        data = json.loads(raw_json)
        
        # Format the document for MongoDB
        reminder_doc = {
            "userId": user_id,
            "title": data.get("title"),
            "isRecurring": data.get("isRecurring", False),
            "rrule": data.get("rrule"),
            "timezone": timezone,
            "scheduledAt": datetime.datetime.fromisoformat(data["scheduledAt"].replace('Z', '+00:00')),
            "status": "PENDING",
            "retryCount": 0,
            "createdAt": datetime.datetime.utcnow()
        }
        
        reminders_col.insert_one(reminder_doc)
        logger.info(f"✅ Reminder Saved to DB: {reminder_doc['title']}")
        return reminder_doc
        
    except Exception as e:
        logger.error(f"🔴 NLP Parsing Failed: {e}")
        return None
