import uuid
import stripe

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.models import CartItem, OrderStatus, PaymentStatus, Cart, Order, CheckoutDraft

from . import checkout_bp

from flask import render_template, redirect, url_for, session, request, flash
from flask_login import login_required, current_user

from app.ecommerce.checkout import checkout_bp
from app.extensions import db
from app.models import Cart, Product, CheckoutDraft


# =========================
# DETAILS
# =========================
@checkout_bp.route("/details", methods=["GET", "POST"])
@login_required
def details():

    checkout_id = session.get("checkout_id")

    if not checkout_id:
        flash("Checkout session expired. Please start again.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        return redirect(url_for("cart.view_cart"))

    cart = Cart.query.filter_by(user_id=current_user.id).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart.view_cart"))

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
        draft.tax = tax
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
@login_required
def summary():

    checkout_id = session.get("checkout_id")

    if not checkout_id:
        flash("Checkout session expired.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        return redirect(url_for("cart.view_cart"))

    cart = Cart.query.filter_by(user_id=current_user.id).first()

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
# PAY (Stripe)
# =========================
@checkout_bp.route("/pay", methods=["POST"])
@login_required
def pay():

    checkout_id = session.get("checkout_id")

    if not checkout_id:
        flash("Checkout session expired.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        flash("Invalid checkout session.", "danger")
        return redirect(url_for("cart.view_cart"))

    cart = Cart.query.filter_by(user_id=current_user.id).first()

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

            customer_email=current_user.email,

            metadata={
                "checkout_id": str(checkout_id),
                "user_id": str(current_user.id),
            }
        )

        return redirect(checkout_session.url)

    except Exception as e:
        print("Stripe error:", e)
        flash("Payment could not be initiated. Please try again.", "danger")
        return redirect(url_for("checkout.summary"))


# =========================
# SUCCESS (UI ONLY)
# =========================
@checkout_bp.route("/success")
@login_required
def success():
    return render_template("checkout/success.html")


# =========================
# STRIPE WEBHOOK
# =========================
@checkout_bp.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    endpoint_secret = current_app.config["STRIPE_WEBHOOK_SECRET"]

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except Exception as e:
        print("Webhook error:", e)
        return "Invalid webhook", 400

    if event["type"] == "checkout.session.completed":

        session_obj = event["data"]["object"]

        checkout_id = session_obj["metadata"]["checkout_id"]
        user_id = session_obj["metadata"]["user_id"]

        draft = CheckoutDraft.query.get(checkout_id)

        if draft:

            order = Order(
                user_id=user_id,
                order_number=str(uuid.uuid4()),
                subtotal=draft.subtotal,
                shipping_fee=draft.shipping_fee,
                tax=draft.tax,
                total_amount=draft.total,
                status=OrderStatus.processing,
                payment_status=PaymentStatus.paid
            )

            db.session.add(order)

            cart = Cart.query.filter_by(user_id=user_id).first()

            if cart:
                CartItem.query.filter_by(cart_id=cart.id).delete()

            db.session.delete(draft)
            db.session.commit()

    if event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        print("Payment failed:", intent["id"])

    return "success", 200