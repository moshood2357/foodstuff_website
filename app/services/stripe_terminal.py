import stripe
from flask import current_app


def get_stripe():
    stripe.api_key = current_app.config.get("STRIPE_TERMINAL_SECRET_KEY")
    return stripe


def create_payment_intent(amount_pence: int, currency: str = "gbp", metadata: dict = None) -> dict:
    """Create a Stripe PaymentIntent for terminal payment."""
    s = get_stripe()

    intent = s.PaymentIntent.create(
        amount              = int(amount_pence),
        currency            = currency.lower(),
        payment_method_types= ["card_present"],
        capture_method      = "automatic",
        metadata            = metadata or {},
    )

    return {
        "intent_id":     intent.id,
        "client_secret": intent.client_secret,
        "status":        intent.status,
        "amount":        amount_pence / 100,
    }


def create_reader_action(reader_id: str, payment_intent_id: str) -> dict:
    """Send payment intent to the physical Stripe Terminal reader."""
    s = get_stripe()
    
    tries = 3
    for attempt in range(tries):
        try:
            reader = s.terminal.Reader.process_payment_intent(
                reader_id,
                payment_intent=payment_intent_id,
            )
            return {
                "reader_id":         reader.id,
                "action_status":     reader.action.status if reader.action else "in_progress",
                "payment_intent_id": payment_intent_id,
            }
        except stripe.error.InvalidRequestError as e:
            code = e.code
            if code == 'terminal_reader_timeout' and attempt < tries - 1:
                continue  # retry
            elif code == 'terminal_reader_offline':
                raise Exception("Reader is offline. Check the reader is powered on and connected.")
            elif code == 'terminal_reader_busy':
                raise Exception("Reader is busy. Please wait and try again.")
            elif code == 'intent_invalid_state':
                raise Exception("Payment already processed or cancelled.")
            else:
                raise


def get_payment_intent_status(payment_intent_id: str) -> str:
    """Poll payment intent status."""
    s = get_stripe()
    intent = s.PaymentIntent.retrieve(payment_intent_id)
    return intent.status


def cancel_reader_action(reader_id: str) -> bool:
    """Cancel current action on the reader."""
    s = get_stripe()
    try:
        s.terminal.Reader.cancel_action(reader_id)
        return True
    except Exception:
        return False


def list_readers(location_id: str = None) -> list:
    """List all registered Terminal readers."""
    s       = get_stripe()
    params  = {}
    if location_id:
        params["location"] = location_id

    readers = s.terminal.Reader.list(**params)
    return [
        {
            "id":     r.id,
            "label":  r.label,
            "status": r.status,
            "model":  r.device_type,
        }
        for r in readers.data
    ]


def create_connection_token() -> str:
    """Create a connection token for the Stripe Terminal SDK."""
    s     = get_stripe()
    token = s.terminal.ConnectionToken.create()
    return token.secret