import time
import logging
import threading
import datetime
import pytz
from dateutil.rrule import rrulestr

logger = logging.getLogger(__name__)

def calculate_next_occurrence(rrule_str: str, timezone_str: str):
    """Calculates the absolute next date based on the RRule and timezone."""
    if not rrule_str:
        return None
    try:
        tz = pytz.timezone(timezone_str)
        now_local = datetime.datetime.now(tz)
        rule = rrulestr(rrule_str)
        
        # Find the next date strictly after current time
        next_date_local = rule.after(now_local)
        
        if next_date_local:
            # Convert back to UTC for MongoDB storage
            if next_date_local.tzinfo is None:
                next_date_local = tz.localize(next_date_local)
            return next_date_local.astimezone(pytz.utc)
    except Exception as e:
        logger.error(f"Failed to parse RRule '{rrule_str}': {e}")
    return None

def start_reminder_scheduler(reminders_col):
    """Background thread that checks MongoDB for due reminders every 60 seconds."""
    
    def scheduler_loop():
        logger.info("🟢 Python Autonomous Scheduler Loop Started!")
        
        # Wait a few seconds before the first run to allow the main server to start fully
        time.sleep(5)
        
        while True:
            try:
                now_utc = datetime.datetime.utcnow()
                
                # 1. Query MongoDB for due reminders
                due_reminders = list(reminders_col.find({
                    "status": "PENDING",
                    "scheduledAt": {"$lte": now_utc}
                }))
                
                if due_reminders:
                    logger.info(f"🔔 Found {len(due_reminders)} due reminders!")
                
                for reminder in due_reminders:
                    task_id = reminder["_id"]
                    
                    # -------------------------------------------------------------
                    # 2. TRIGGER ACTION (FCM PUSH TO WAKE UP ANDROID APP)
                    # -------------------------------------------------------------
                    logger.info(f"🚨 ALARM TRIGGER: {reminder.get('title', 'Unknown Task')}")
                    
                    # TODO Boss: Yahan aap FCM Push ya WebSocket Broadcast call kar sakte hain.
                    # Example:
                    # if FCM_TARGET_TOKEN:
                    #     messaging.send(messaging.Message(
                    #         data={'command': 'SYNC_REMINDERS', 'type': 'REMINDER_WAKEUP'},
                    #         token=FCM_TARGET_TOKEN
                    #     ))
                    # -------------------------------------------------------------
                    
                    update_payload = {"lastTriggeredAt": now_utc}
                    
                    # 3. Calculate next Loop for Recurring Tasks
                    if reminder.get("isRecurring") and reminder.get("rrule"):
                        next_date_utc = calculate_next_occurrence(
                            reminder["rrule"], 
                            reminder.get("timezone", "Asia/Kolkata")
                        )
                        
                        if next_date_utc:
                            update_payload["scheduledAt"] = next_date_utc
                            update_payload["status"] = "PENDING"
                            logger.info(f"🔄 Rescheduled '{reminder.get('title')}' to {next_date_utc}")
                        else:
                            # Occurrences finished (e.g., COUNT reached)
                            update_payload["status"] = "COMPLETED"
                            update_payload["completedAt"] = now_utc
                    else:
                        # One-time task is done
                        update_payload["status"] = "COMPLETED"
                        update_payload["completedAt"] = now_utc
                    
                    update_payload["retryCount"] = 0
                    
                    # 4. Atomic MongoDB Update
                    reminders_col.update_one(
                        {"_id": task_id},
                        {"$set": update_payload}
                    )

            except Exception as e:
                logger.error(f"🔴 Scheduler Loop Error: {e}")
            
            # Sleep for 60 seconds before next check
            time.sleep(60)

    # Start the daemon thread so it runs continuously in the background without blocking FastAPI
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()
