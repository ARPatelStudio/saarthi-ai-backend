import imaplib
import email
import logging
import os
from email.header import decode_header

logger = logging.getLogger(__name__)

def check_unread_emails(limit: int = 3):
    """Reads latest unread emails via IMAP"""
    email_user = os.getenv("GMAIL_USER")
    email_pass = os.getenv("GMAIL_APP_PASSWORD")

    if not email_user or not email_pass:
        return "Boss, GMAIL_USER ya GMAIL_APP_PASSWORD environment variables missing hain."

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, email_pass)
        mail.select("inbox")

        status, messages = mail.search(None, "UNSEEN")
        if status != "OK": return "Boss, inbox read nahi kar pa raha hoon."

        mail_ids = messages[0].split()
        if not mail_ids: return "Boss, inbox mein koi naya unread mail nahi hai."

        recent_ids = mail_ids[-limit:]
        response_text = f"Boss, {len(mail_ids)} unread mails hain. Latest {len(recent_ids)} mails:\n"

        for i, num in enumerate(reversed(recent_ids), 1):
            status, msg_data = mail.fetch(num, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    response_text += f"{i}. From: {msg.get('From')} | Subject: {subject}\n"

        mail.logout()
        return response_text
    except Exception as e:
        logger.error(f"Mail Engine Error: {e}")
        return "Boss, mail check karne mein error aaya. App password verify kar lijiye."
