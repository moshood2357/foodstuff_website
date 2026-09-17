from importlib import metadata
import re
import uuid
import hmac
import hashlib
import traceback
import json

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    CartItem, OrderStatus, PaymentStatus, Cart, Order,
    CheckoutDraft, Address, OrderItem, Payment,
    Product, StockMovement, MovementType, OrderStatusLog, StockReservation
)

from app import csrf
from app.ecommerce.checkout import checkout_bp
from app.utils.helpers import get_user_key
from app.utils.email import send_order_notification
from app.services.dojo import create_dojo_hosted_payment


# =========================
# EMAIL VALIDATOR
# =========================
def is_valid_email(email):
    if not email:
        return False
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email.strip()))


# =========================
# HELPER
# =========================
def get_identity():
    if current_user.is_authenticated:
        return {"type": "user", "id": current_user.id}
    else:
        return {"type": "guest", "key": session.get("user_key") or get_user_key()}


# =========================
# DETAILS
# =========================
@checkout_bp.route("/details", methods=["GET", "POST"])
def details():
    checkout_id = session.get("checkout_id")
    if not checkout_id:
        flash("Checkout session expired. Please start again.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)
    if not draft:
        return redirect(url_for("cart.view_cart"))

    session["guest_email"] = draft.email
    identity = get_identity()

    if identity["type"] == "user":
        cart = Cart.query.filter_by(user_id=identity["id"]).first()
    else:
        cart = Cart.query.filter_by(user_key=identity["key"]).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart.view_cart"))

    if request.method == "GET":
        draft_is_empty = not any([
            draft.full_name, draft.address_line_1,
            draft.city, draft.postal_code
        ])
        if draft_is_empty:
            if identity["type"] == "user":
                previous = (
                    CheckoutDraft.query
                    .filter_by(user_id=identity["id"], completed=True)
                    .order_by(CheckoutDraft.id.desc())
                    .first()
                )
            else:
                guest_email = session.get("guest_email")
                previous = (
                    CheckoutDraft.query
                    .filter(
                        CheckoutDraft.email == guest_email,
                        CheckoutDraft.completed == True
                    )
                    .order_by(CheckoutDraft.id.desc())
                    .first()
                ) if guest_email else None

            if previous:
                draft.full_name      = previous.full_name
                draft.email          = previous.email
                draft.phone          = previous.phone
                draft.address_line_1 = previous.address_line_1
                draft.address_line_2 = previous.address_line_2
                draft.city           = previous.city
                draft.state          = previous.state
                draft.postal_code    = previous.postal_code
                db.session.commit()

    if request.method == "POST":
        draft.fulfillment_type = request.form.get("fulfillment_type", "delivery")
        subtotal = sum(item.quantity * float(item.unit_price) for item in cart.items)

        if draft.fulfillment_type == "pickup":
            draft.full_name      = request.form.get("pickup_name")
            draft.phone          = request.form.get("pickup_phone")
            submitted_email      = request.form.get("pickup_email", "").strip()
            if is_valid_email(submitted_email):
                draft.email      = submitted_email
            draft.pickup_date    = request.form.get("pickup_date")
            draft.pickup_time    = request.form.get("pickup_time")
            draft.note           = request.form.get("note", "").strip() or None
            draft.delivery_fee   = 0
            draft.delivery_miles = None
            draft.shipping_fee   = 0
            draft.subtotal       = subtotal
            draft.tax            = 0
            draft.total          = subtotal
            db.session.commit()
            return redirect(url_for("checkout.summary"))

        draft.full_name = request.form.get("full_name")
        submitted_email = request.form.get("email", "").strip()
        if is_valid_email(submitted_email):
            draft.email = submitted_email

        draft.phone          = request.form.get("phone")
        draft.address_line_1 = request.form.get("address_line_1")
        draft.address_line_2 = request.form.get("address_line_2")
        draft.city           = request.form.get("city")
        draft.state          = request.form.get("state")
        draft.postal_code    = request.form.get("postal_code")
        draft.note           = request.form.get("note", "").strip() or None
        draft.delivery_miles = request.form.get("delivery_miles") or None
        draft.delivery_fee   = request.form.get("delivery_fee") or None

        same_as_delivery = request.form.get("same_as_delivery") == "on"
        draft.same_as_delivery = same_as_delivery

        if same_as_delivery:
            draft.billing_address_line_1 = draft.address_line_1
            draft.billing_address_line_2 = draft.address_line_2
            draft.billing_city           = draft.city
            draft.billing_state          = draft.state
            draft.billing_postcode       = draft.postal_code
        else:
            draft.billing_address_line_1 = request.form.get("billing_address_line_1")
            draft.billing_address_line_2 = request.form.get("billing_address_line_2")
            draft.billing_city           = request.form.get("billing_city")
            draft.billing_state          = request.form.get("billing_state")
            draft.billing_postcode       = request.form.get("billing_postcode")

        delivery_fee       = float(draft.delivery_fee or 0)
        draft.subtotal     = subtotal
        draft.shipping_fee = delivery_fee
        draft.tax          = 0
        draft.total        = subtotal + delivery_fee

        db.session.commit()
        return redirect(url_for("checkout.summary"))

    products = {item.product_id: item.product for item in cart.items}
    total    = sum(item.quantity * float(item.unit_price) for item in cart.items)

    return render_template(
        "checkout/details.html",
        draft=draft,
        cart=cart,
        products=products,
        cart_total=total
    )


# =========================
# SUMMARY
# =========================
@checkout_bp.route("/summary")
def summary():
    checkout_id = session.get("checkout_id")
    if not checkout_id:
        flash("Checkout session expired.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)
    if not draft:
        return redirect(url_for("cart.view_cart"))

    identity = get_identity()
    if identity["type"] == "user":
        cart = Cart.query.filter_by(user_id=identity["id"]).first()
    else:
        cart = Cart.query.filter_by(user_key=identity["key"]).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart.view_cart"))

    products = {item.product_id: item.product for item in cart.items}
    subtotal = sum(item.quantity * float(item.unit_price) for item in cart.items)

    if draft.fulfillment_type == "pickup":
        draft.subtotal     = subtotal
        draft.shipping_fee = 0
        draft.tax          = 0
        draft.total        = subtotal
    else:
        delivery_fee       = float(draft.delivery_fee or 0)
        draft.subtotal     = subtotal
        draft.shipping_fee = delivery_fee
        draft.tax          = 0
        draft.total        = subtotal + delivery_fee

    db.session.commit()

    return render_template(
        "checkout/summary.html",
        draft=draft,
        cart=cart,
        products=products
    )


# =========================
# PAY — redirect to Dojo
# =========================
@checkout_bp.route("/pay", methods=["POST"])
def pay():
    checkout_id = session.get("checkout_id")
    if not checkout_id:
        flash("Checkout session expired.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)
    if not draft:
        flash("Invalid checkout session.", "danger")
        return redirect(url_for("cart.view_cart"))

    identity = get_identity()
    if identity["type"] == "user":
        cart = Cart.query.filter_by(user_id=identity["id"]).first()
    else:
        cart = Cart.query.filter_by(user_key=identity["key"]).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart.view_cart"))

    try:
        pay_url = create_dojo_hosted_payment(
            amount_pence=int(float(draft.total) * 100),
            currency="GBP",
            reference=f"CHK-{draft.id}",
            metadata={
                "checkout_id": str(draft.id),
                "user_id":     str(identity["id"]) if identity["type"] == "user" else "",
                "guest_key":   session.get("user_key", ""),
            }
        )
        return redirect(pay_url)

    except Exception as e:
        current_app.logger.error(f"Dojo payment init failed: {e}")
        current_app.logger.error(traceback.format_exc())
        flash("Payment could not be initiated. Please try again.", "danger")
        return redirect(url_for("checkout.summary"))


# =========================
# SUCCESS
# =========================
@checkout_bp.route("/success")
def success():
    import time
    payment_intent_id = request.args.get("paymentIntentId") or request.args.get("payment_intent_id")

    order = None

    if payment_intent_id:
        # retry up to 3 times with 1 second delay — webhook may not have fired yet
        for _ in range(3):
            payment = Payment.query.filter_by(transaction_id=payment_intent_id).first()
            if payment:
                order = Order.query.get(payment.order_id)
                break
            time.sleep(1)

    # fallback for authenticated users
    if not order and current_user.is_authenticated:
        order = Order.query.filter_by(
            user_id=current_user.id
        ).order_by(Order.id.desc()).first()

    # fallback for guests
    if not order:
        checkout_id = session.get("checkout_id")
        if checkout_id:
            payment = Payment.query.join(Order).filter(
                Order.guest_email == session.get("guest_email")
            ).order_by(Payment.id.desc()).first()
            if payment:
                order = Order.query.get(payment.order_id)

    guest_email = None if current_user.is_authenticated else session.get("guest_email")

    return render_template(
        "checkout/success.html",
        order=order,
        guest_email=guest_email
    )
# =========================
# DOJO WEBHOOK
# =========================

from hashlib import sha256

import requests



@checkout_bp.route("/dojo/webhook", methods=["POST"])
@csrf.exempt
def dojo_webhook():
    payload = request.get_data(cache=False)
    sig_header = request.headers.get("dojo-signature") or request.headers.get(
        "Dojo-Signature", ""
    )
    webhook_secret = current_app.config.get("DOJO_WEBHOOK_SECRET", "")

    # 1. Verify Signature
    if webhook_secret and sig_header:
        digest = hmac.new(
            webhook_secret.encode("utf-8"),
            msg=payload,
            digestmod=sha256,
        ).digest()
        expected_sig = "sha256=" + "-".join(f"{byte:02X}" for byte in digest)

        if not hmac.compare_digest(sig_header, expected_sig):
            current_app.logger.error("Dojo webhook signature mismatch")
            current_app.logger.error(f"Expected: {expected_sig} | Got: {sig_header}")
            return "Invalid signature", 400

    # 2. Parse Payload
    try:
        event = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        current_app.logger.error("Failed to decode JSON payload")
        return "Invalid JSON", 400

    event_type = event.get("event", "")
    current_app.logger.info(f"Dojo webhook received: {event_type}")

    if event_type != "payment_intent.status_updated":
        return "ok", 200

    data = event.get("data", {})
    payment_status = data.get("paymentStatus", "")
    intent_id = data.get("paymentIntentId", "")

    current_app.logger.info(
        f"Payment intent {intent_id} status: {payment_status}"
    )


    if payment_status in ["Failed", "Declined", "Cancelled", "Rejected"]:
        current_app.logger.info(f"Payment {payment_status} for intent {intent_id}")
        # fetch metadata to get checkout_id
        try:
            api_key  = current_app.config.get("DOJO_API_KEY")
            api_base = current_app.config.get("DOJO_API_BASE")
            fi_resp  = requests.get(
                f"{api_base}/payment-intents/{intent_id}",
                headers={
                    "Authorization": f"Basic {api_key}",
                    "version": "2024-02-05",
                },
                timeout=10,
            )
            if fi_resp.ok:
                fi_data     = fi_resp.json()
                fi_metadata = fi_data.get("metadata", {})
                checkout_id = fi_metadata.get("checkout_id")
                if checkout_id:
                    draft = CheckoutDraft.query.filter_by(id=int(checkout_id)).first()
                    if draft and not draft.completed:
                        failed_address = Address(
                            user_id       = int(fi_metadata.get("user_id")) if fi_metadata.get("user_id") else None,
                            full_name     = draft.full_name or "Unknown",
                            phone         = draft.phone or "",
                            address_line_1= draft.address_line_1 or "N/A",
                            address_line_2= draft.address_line_2 or "",
                            city          = draft.city or "N/A",
                            state         = draft.state or "N/A",
                            country       = "United Kingdom",
                            postal_code   = draft.postal_code or "N/A",
                        )
                        db.session.add(failed_address)
                        db.session.flush()

                        failed_order = Order(
                            user_id        = int(fi_metadata.get("user_id")) if fi_metadata.get("user_id") else None,
                            address_id     = failed_address.id,
                            order_number   = f"ORD-{uuid.uuid4().hex[:10].upper()}",
                            subtotal       = draft.subtotal or 0,
                            shipping_fee   = draft.shipping_fee or 0,
                            tax            = draft.tax or 0,
                            total_amount   = draft.total or 0,
                            status         = OrderStatus.payment_failed,
                            payment_status = PaymentStatus.failed,
                            guest_email    = draft.email,
                            fulfillment_type = draft.fulfillment_type or "delivery",
                            note           = f"Payment {payment_status} via Dojo",
                        )
                        db.session.add(failed_order)
                        db.session.commit()
                        current_app.logger.info(f"Payment failed order created: {failed_order.order_number}")
        except Exception as e:
            current_app.logger.error(f"Failed order creation error: {e}")
        return "ok", 200

    if payment_status != "Captured":
        current_app.logger.info(f"Ignoring unhandled status: {payment_status}")
        return "ok", 200
    

    # 3. Fetch Payment Details from Dojo
    try:
        api_key = current_app.config.get("DOJO_API_KEY")
        api_base = current_app.config.get("DOJO_API_BASE")
        resp = requests.get(
            f"{api_base}/payment-intents/{intent_id}",
            headers={
                "Authorization": f"Basic {api_key}",
                "version": "2024-02-05",
            },
            timeout=10,
        )
        resp.raise_for_status()
        intent_data = resp.json()
    except Exception as e:
        current_app.logger.error(
            f"Failed to fetch Dojo payment intent {intent_id}: {str(e)}"
        )
        return "Failed to fetch payment intent", 500

    metadata = intent_data.get("metadata", {})
    checkout_id = metadata.get("checkout_id")
    user_id = metadata.get("user_id")
    guest_key = metadata.get("guest_key")

    if not checkout_id:
        current_app.logger.error("Missing checkout_id in metadata")
        return "missing checkout_id", 200

    # 4. Database Operations
    try:
        # Prevent duplicate processing
        existing = Payment.query.filter_by(transaction_id=intent_id).first()
        if existing:
            current_app.logger.info(
                f"Transaction {intent_id} already processed"
            )
            return "already processed", 200

        draft = CheckoutDraft.query.filter_by(id=int(checkout_id)).first()
        if not draft:
            current_app.logger.error(f"Draft {checkout_id} not found")
            return "draft not found", 200

        # Create Address
        if draft.fulfillment_type == "pickup":
            address = Address(
                user_id=int(user_id) if user_id else None,
                full_name=draft.full_name or "",
                phone=draft.phone or "",
                address_line_1="311 High Street",
                address_line_2="",
                city="Cheltenham",
                state="Gloucestershire",
                country="United Kingdom",
                postal_code="GL50 3HW",
            )
        else:
            address = Address(
                user_id=int(user_id) if user_id else None,
                full_name=draft.full_name or "",
                phone=draft.phone or "",
                address_line_1=draft.address_line_1 or "",
                address_line_2=draft.address_line_2 or "",
                city=draft.city or "",
                state=draft.state or "",
                country=getattr(draft, "country", None) or "United Kingdom",
                postal_code=draft.postal_code or "",
            )
        db.session.add(address)
        db.session.flush()

        # Create Order
        guest_email_to_save = (
            draft.email if is_valid_email(draft.email) else None
        )
        order = Order(
            user_id=int(user_id) if user_id else None,
            address_id=address.id,
            order_number=f"ORD-{uuid.uuid4().hex[:10].upper()}",
            subtotal=draft.subtotal,
            shipping_fee=draft.shipping_fee,
            delivery_miles=draft.delivery_miles,
            delivery_fee=draft.delivery_fee,
            fulfillment_type=draft.fulfillment_type or "delivery",
            pickup_date=draft.pickup_date,
            pickup_time=draft.pickup_time,
            tax=draft.tax,
            total_amount=draft.total,
            status=OrderStatus.new, 
            payment_status=PaymentStatus.paid,
            guest_email=guest_email_to_save if not user_id else None,
            note=draft.note,
        )
        db.session.add(order)
        db.session.flush()

        # Create Items & Deduct Stock safely
        try:
            cart_items = json.loads(draft.cart_snapshot or "[]")
        except json.JSONDecodeError:
            cart_items = []

        for item in cart_items:
            product_id = item.get("product_id")
            quantity = item.get("quantity", 1)
            price = item.get("price", 0)

            if not product_id:
                continue

            order_item = OrderItem(
                order_id=order.id,
                product_id=product_id,
                quantity=quantity,
                price=price,
                product_name=item.get("name", ""),
                product_image=item.get("image", ""),
            )
            db.session.add(order_item)

            # Row locking for atomic stock deduction
            product = (
                db.session.query(Product)
                .with_for_update()
                .filter_by(id=product_id)
                .first()
            )
            if product and product.stock_quantity is not None:
                stock_before = product.stock_quantity
                product.stock_quantity = max(0, stock_before - quantity)
                movement = StockMovement(
                    product_id=product.id,
                    created_by=None,
                    movement_type=MovementType.sale,
                    quantity=-quantity,
                    stock_before=stock_before,
                    stock_after=product.stock_quantity,
                    reference=order.order_number,
                    note=f"Online sale",
                )
                db.session.add(movement)

            # Stock Reservation
            reservation = StockReservation(
                order_id=order.id,
                product_id=product_id,
                variant_id=item.get("variant_id"),
                quantity=quantity,
                is_active=True,
            )
            db.session.add(reservation)

        # Create Payment Record
        payment = Payment(
            order_id=order.id,
            payment_method="dojo",
            transaction_id=intent_id,
            amount=draft.total,
            status=PaymentStatus.paid,
            reference=intent_id,
            paid_at=datetime.utcnow(),
        )
        db.session.add(payment)

        # Clear Cart
        cart = None
        if user_id:
            try:
                cart = Cart.query.filter_by(user_id=int(user_id)).first()
            except (ValueError, TypeError):
                cart = None
        elif guest_key:
            cart = Cart.query.filter_by(user_key=guest_key).first()

        if cart:
            CartItem.query.filter_by(cart_id=cart.id).delete()

        # Update Draft status
        draft.completed = True
        draft.completed_at = datetime.utcnow()

        # Log Status Change
        log = OrderStatusLog(
            order_id=order.id,
            from_status="new",
            to_status="payment_confirmed",
            changed_by=None,
            note="Payment confirmed via Dojo webhook",
        )
        db.session.add(log)

        # Commit Entire Transaction At Once
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"Database error while processing Dojo webhook: {str(e)}"
        )
        current_app.logger.error(traceback.format_exc())
        return "Internal server error", 500

    # 5. Send Notifications (Outside DB Transaction)
    try:
        send_order_notification(order)
    except Exception:
        current_app.logger.error("Email notification failed")
        current_app.logger.error(traceback.format_exc())

    current_app.logger.info(
        f"Order created and payment confirmed: {order.order_number}"
    )
    return "ok", 200