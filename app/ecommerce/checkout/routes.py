import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user

from app.extensions import db
from app.models import CartItem, OrderStatus, PaymentStatus, Cart, Order

from . import checkout_bp


from flask import render_template, redirect, url_for, session, request, flash
from flask_login import login_required, current_user

from app.ecommerce.checkout import checkout_bp
from app.extensions import db
from app.models import CheckoutDraft, Cart, Product


@checkout_bp.route("/details", methods=["GET", "POST"])
@login_required
def details():

    # =========================
    # GET CHECKOUT SESSION
    # =========================
    checkout_id = session.get("checkout_id")

    if not checkout_id:
        flash("Checkout session expired. Please start again.", "warning")
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        return redirect(url_for("cart.view_cart"))

    # =========================
    # GET USER CART
    # =========================
    cart = Cart.query.filter_by(user_id=current_user.id).first()

    if not cart or not cart.items:
        flash("Your cart is empty.", "warning")
        return redirect(url_for("cart.view_cart"))

    # =========================
    # HANDLE FORM SUBMISSION
    # =========================
    if request.method == "POST":

        draft.full_name = request.form.get("full_name")
        draft.email = request.form.get("email")
        draft.phone = request.form.get("phone")

        draft.delivery_address = request.form.get("delivery_address")
        draft.billing_address = request.form.get("billing_address")
        draft.delivery_method = request.form.get("delivery_method")

        # =========================
        # SNAPSHOT CART
        # =========================
        draft.cart_snapshot = [
            {
                "product_id": item.product_id,
                "name": item.product.name,
                "qty": item.quantity,
                "price": float(item.unit_price)
            }
            for item in cart.items
        ]

        # =========================
        # CALCULATE TOTALS
        # =========================
        subtotal = sum(i["qty"] * i["price"] for i in draft.cart_snapshot)

        shipping = subtotal * 0.1 if draft.delivery_method == "express" else subtotal * 0.05
        tax = subtotal * 0.05

        draft.subtotal = subtotal
        draft.shipping_fee = shipping
        draft.tax = tax
        draft.total = subtotal + shipping + tax

        db.session.commit()

        return redirect(url_for("checkout.summary"))

    # =========================
    # FETCH PRODUCTS FOR DISPLAY
    # =========================
    products = {}

    for item in draft.cart_snapshot or []:
        product = Product.query.get(item["product_id"])
        if product:
            products[item["product_id"]] = product

    # =========================
    # RENDER PAGE
    # =========================
    return render_template(
        "checkout/details.html",
        draft=draft,
        products=products
    )




@checkout_bp.route("/summary")
@login_required
def summary():

    checkout_id = session.get("checkout_id")
    if not checkout_id:
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        return redirect(url_for("cart.view_cart"))

    return render_template("checkout/summary.html", draft=draft)


@checkout_bp.route("/pay", methods=["POST"])
@login_required
def pay():

    checkout_id = session.get("checkout_id")
    if not checkout_id:
        return redirect(url_for("cart.view_cart"))

    draft = CheckoutDraft.query.get(checkout_id)

    if not draft:
        return redirect(url_for("cart.view_cart"))

    order = Order(
        user_id=current_user.id,
        order_number=str(uuid.uuid4()),
        subtotal=draft.subtotal,
        shipping_fee=draft.shipping_fee,
        tax=draft.tax,
        total_amount=draft.total,
        status=OrderStatus.processing,
        payment_status=PaymentStatus.paid
    )

    db.session.add(order)

    # clear cart safely
    cart = Cart.query.filter_by(user_id=current_user.id).first()
    if cart:
        CartItem.query.filter_by(cart_id=cart.id).delete()

    db.session.delete(draft)
    db.session.commit()

    session.pop("checkout_id", None)

    return redirect(url_for("checkout.success"))


@checkout_bp.route("/success")
@login_required
def success():
    return render_template("checkout/success.html")