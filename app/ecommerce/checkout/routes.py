import uuid
import stripe
import traceback
import json

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    CartItem, OrderStatus, PaymentStatus, Cart, Order,
    CheckoutDraft, Address, OrderItem, Payment
)

from flask import render_template, redirect, url_for, session, request, flash

from app import csrf
from app.ecommerce.checkout import checkout_bp

from app.utils.helpers import get_user_key
from app.utils.email import send_order_notification

# =========================
# HELPER (GUEST SAFE)
# =========================
def get_identity():
    if current_user.is_authenticated:
        return {
            "type": "user",
            "id": current_user.id
        }
    else:
        return {
            "type": "guest",
            "key": session.get("user_key") or get_user_key()
        }


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

    # =========================
    # PRE-POPULATE ON GET
    # =========================
    if request.method == "GET":

        draft_is_empty = not any([
            draft.full_name,
            draft.address_line_1,
            draft.city,
            draft.postal_code
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
                draft.full_name = previous.full_name
                draft.email = previous.email
                draft.phone = previous.phone
                draft.address_line_1 = previous.address_line_1
                draft.address_line_2 = previous.address_line_2
                draft.city = previous.city
                draft.state = previous.state
                draft.postal_code = previous.postal_code
                db.session.commit()

    # =========================
    # POST
    # =========================
    if request.method == "POST":

        draft.full_name = request.form.get("full_name")
        draft.email = request.form.get("email")
        draft.phone = request.form.get("phone")

        draft.address_line_1 = request.form.get("address_line_1")
        draft.address_line_2 = request.form.get("address_line_2")
        draft.city = request.form.get("city")
        draft.state = request.form.get("state")
        draft.postal_code = request.form.get("postal_code")

        draft.delivery_method = request.form.get("delivery_method")

        same_as_delivery = request.form.get("same_as_delivery") == "on"
        draft.same_as_delivery = same_as_delivery

        if same_as_delivery:
            draft.billing_address_line_1 = draft.address_line_1
            draft.billing_address_line_2 = draft.address_line_2
            draft.billing_city = draft.city
            draft.billing_state = draft.state
            draft.billing_postcode = draft.postal_code
        else:
            draft.billing_address_line_1 = request.form.get("billing_address_line_1")
            draft.billing_address_line_2 = request.form.get("billing_address_line_2")
            draft.billing_city = request.form.get("billing_city")
            draft.billing_state = request.form.get("billing_state")
            draft.billing_postcode = request.form.get("billing_postcode")

        subtotal = sum(item.quantity * float(item.unit_price) for item in cart.items)

        shipping = subtotal * 0.10 if draft.delivery_method == "express" else subtotal * 0.05
        tax = subtotal * 0.05

        draft.subtotal = subtotal
        draft.shipping_fee = shipping
        draft.tax  = tax
        draft.total = subtotal + shipping + tax

        db.session.commit()

        return redirect(url_for("checkout.summary"))

    products = {item.product_id: item.product for item in cart.items}
    total = sum(item.quantity * float(item.unit_price) for item in cart.items)

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

    shipping = subtotal * 0.10 if draft.delivery_method == "express" else subtotal * 0.05
    tax = subtotal * 0.05

    draft.subtotal = subtotal
    draft.shipping_fee = shipping
    draft.tax = tax
    draft.total = subtotal + shipping + tax

    db.session.commit()

    return render_template(
        "checkout/summary.html",
        draft=draft,
        cart=cart,
        products=products
    )


# =========================
# PAY (STRIPE)
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
        amount = int(draft.total * 100)

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",

            line_items=[{
                "price_data": {
                    "currency": "gbp",
                    "product_data": {
                        "name": f"Order #{checkout_id}",
                    },
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],

            success_url=url_for("checkout.success", _external=True),
            cancel_url=url_for("checkout.summary", _external=True),

            customer_email=draft.email,

            metadata={
                "checkout_id": str(checkout_id),
                "user_id": str(identity["id"]) if identity["type"] == "user" else "",
                "guest_key": session.get("user_key", "")
            }
        )

        return redirect(checkout_session.url)

    except Exception as e:
        print("Stripe error:", e)
        flash("Payment could not be initiated. Please try again.", "danger")
        return redirect(url_for("checkout.summary"))


# =========================
# SUCCESS
# =========================
@checkout_bp.route("/success")
def success():

    if current_user.is_authenticated:
        order = Order.query.filter_by(user_id=current_user.id)\
            .order_by(Order.id.desc()).first()

        return render_template(
            "checkout/success.html",
            order=order,
            guest_email=None
        )

    else:
        # guest flow
        guest_email = session.get("guest_email")
        order = Order.query.filter_by(guest_email=guest_email)\
            .order_by(Order.id.desc()).first()

        return render_template(
            "checkout/success.html",
            order=order,
            guest_email=guest_email
        )


# =========================================================
# STRIPE WEBHOOK
# =========================================================
@checkout_bp.route("/stripe/webhook", methods=["POST"])
@csrf.exempt
def stripe_webhook():

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    endpoint_secret = current_app.config["STRIPE_WEBHOOK_SECRET"]

    # =====================================================
    # VERIFY STRIPE SIGNATURE
    # =====================================================
    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            endpoint_secret
        )

    except ValueError:
        current_app.logger.error("Invalid payload")
        return "Invalid payload", 400

    except stripe.error.SignatureVerificationError:
        current_app.logger.error("Invalid Stripe signature")
        return "Invalid signature", 400

    except Exception:
        current_app.logger.error(traceback.format_exc())
        return "Webhook verification failed", 400

    # =====================================================
    # HANDLE EVENT
    # =====================================================
    try:

        # =================================================
        # CHECKOUT SUCCESS
        # =================================================
        if event["type"] == "checkout.session.completed":

            session_obj = event["data"]["object"]
            metadata = session_obj.to_dict().get("metadata") or {}

            checkout_id = metadata.get("checkout_id")
            user_id = metadata.get("user_id")
            guest_key = metadata.get("guest_key")

            # =============================================
            # VALIDATE CHECKOUT ID
            # =============================================
            if not checkout_id:
                current_app.logger.error("Missing checkout_id")
                return "missing checkout id", 200

            try:
                checkout_id = int(checkout_id)
            except (ValueError, TypeError):
                current_app.logger.error("Invalid checkout_id")
                return "invalid checkout id", 200

            # =============================================
            # PREVENT DUPLICATE PROCESSING
            # =============================================
            existing_payment = Payment.query.filter_by(
                reference=session_obj.id  #  fixed
            ).first()

            if existing_payment:
                current_app.logger.info("Webhook already processed")
                return "already processed", 200

            # =============================================
            # GET DRAFT
            # =============================================
            draft = CheckoutDraft.query.filter_by(
                id=checkout_id
            ).first()

            if not draft:
                current_app.logger.error("Draft not found")
                return "draft not found", 200

            # =============================================
            # CREATE ADDRESS
            # =============================================
            address = Address(
                user_id=int(user_id) if user_id else None,
                full_name=draft.full_name or "",
                phone=draft.phone or "",
                address_line_1=draft.address_line_1 or "",
                address_line_2=draft.address_line_2 or "",
                city=draft.city or "",
                state=draft.state or "",
                country=draft.country or "United Kingdom",
                postal_code=draft.postal_code or "",
            )

            db.session.add(address)
            db.session.flush()

            # =============================================
            # CREATE ORDER
            # =============================================
            order = Order(
                user_id=int(user_id) if user_id else None,
                address_id=address.id,
                order_number=f"ORD-{uuid.uuid4().hex[:10].upper()}",
                subtotal=draft.subtotal,
                shipping_fee=draft.shipping_fee,
                delivery_method=draft.delivery_method,
                tax=draft.tax,
                total_amount=draft.total,
                status=OrderStatus.processing,
                payment_status=PaymentStatus.paid,
                guest_email=draft.email if not user_id else None,
            )

            db.session.add(order)
            db.session.flush()

            # =============================================
            # CART ITEMS
            # =============================================
            try:
                cart_items = json.loads(
                    draft.cart_snapshot or "[]"
                )
            except json.JSONDecodeError:
                current_app.logger.error("Invalid cart snapshot JSON")
                cart_items = []

            # =============================================
            # CREATE ORDER ITEMS
            # =============================================
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

            # =============================================
            # CREATE PAYMENT
            # =============================================
            payment = Payment(
                order_id=order.id,
                payment_method="stripe",
                transaction_id=session_obj.payment_intent,  #  fixed
                amount=draft.total,
                status=PaymentStatus.paid,
                reference=session_obj.id,                   #  fixed
                paid_at=datetime.utcnow(),
            )

            db.session.add(payment)

            # =============================================
            # CLEAR CART
            # =============================================
            cart = None

            if user_id:
                try:
                    cart = Cart.query.filter_by(
                        user_id=int(user_id)
                    ).first()
                except (ValueError, TypeError):
                    cart = None

            elif guest_key:
                cart = Cart.query.filter_by(
                    user_key=guest_key
                ).first()

            if cart:
                db.session.query(CartItem).filter_by(
                    cart_id=cart.id
                ).delete()

            # =============================================
            # KEEP CHECKOUT DRAFT
            # =======================================
            draft.completed = True
            draft.completed_at = datetime.utcnow()
            # =============================================
            # COMMIT TRANSACTION
            # =============================================
            db.session.commit()

            # after db.session.commit()
            
            try:
                send_order_notification(order)
            except Exception:
                current_app.logger.error("Email notification failed")
                current_app.logger.error(traceback.format_exc())

            current_app.logger.info(f"Stripe order created successfully: {order.order_number}")

        # =================================================
        # SUCCESS RESPONSE
        # =================================================
        return "success", 200

    except Exception:
        db.session.rollback()

        current_app.logger.error("Stripe webhook processing failed")
        current_app.logger.error(traceback.format_exc())

        return "server error", 500