import re
import uuid

from flask_login import current_user
from flask import session

def generate_slug(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    
    return f"{text}-{uuid.uuid4().hex[:6]}"




def get_user_key():
    if current_user.is_authenticated:
        return f"user_{current_user.id}"

    if "guest_id" not in session:
        session["guest_id"] = f"guest_{uuid.uuid4()}"

    return session["guest_id"]