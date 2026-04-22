import os
import requests

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

BREVO_API_KEY = os.getenv("BREVO_API_KEY") 


def send_email(to, subject, html_content, sender_name="Your App", sender_email=None):
    """
    Send transactional email via Brevo API
    """

    if not sender_email:
        sender_email = os.getenv("BREVO_SENDER_EMAIL")

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email
        },
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html_content
    }

    try:
        response = requests.post(BREVO_API_URL, json=payload, headers=headers)

        # safer handling
        if response.status_code not in [200, 201, 202]:
            print("Email failed:", response.text)

        return {
            "success": response.status_code in [200, 201, 202],
            "status_code": response.status_code,
            "response": response.json() if response.text else {}
        }

    except Exception as e:
        print("Email exception:", str(e))
        return {
            "success": False,
            "error": str(e)
        }