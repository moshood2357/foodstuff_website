from flask import current_app


def send_order_sms(order, message):
    """Send SMS to customer via Twilio."""
    try:
        from twilio.rest import Client
        account_sid = current_app.config.get("TWILIO_ACCOUNT_SID")
        auth_token  = current_app.config.get("TWILIO_AUTH_TOKEN")
        from_number = current_app.config.get("TWILIO_SMS_FROM")

        if not all([account_sid, auth_token, from_number]):
            current_app.logger.error("Twilio SMS not configured")
            return

        # get customer phone
        phone = None
        if order.address:
            phone = order.address.phone
        if not phone:
            return

        # format phone
        phone = phone.strip().replace(' ', '')
        if not phone.startswith('+'):
            phone = '+44' + phone.lstrip('0')

        client = Client(account_sid, auth_token)
        client.messages.create(
            from_=from_number,
            to=phone,
            body='sms_order_confirmation'
        )
        current_app.logger.info(f"SMS sent to {phone} for order {order.order_number}")

    except Exception as e:
        current_app.logger.error(f"SMS failed for order {order.order_number}: {e}")