from flask import flash, redirect, render_template, jsonify, request, session, url_for
from flask_login import login_required, current_user

from app.utils.helpers import get_user_key
from . import cart_bp
from app.models import Product, CartItem, Cart, Wishlist, CheckoutDraft
from app.extensions import db


# =========================
# VIEW CART
# =========================
@cart_bp.route('/')
def view_cart():

    user_key = get_user_key()

    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
    else:
        cart = Cart.query.filter_by(user_key=user_key).first()

    if not cart:
        return render_template('cart/cart.html', cart_items=[], total=0)

    cart_items = (
        db.session.query(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .filter(CartItem.cart_id == cart.id)
        .all()
    )

    total = sum(ci.quantity * p.price for ci, p in cart_items)

    return render_template(
        'cart/cart.html',
        cart_items=cart_items,
        total=total
    )


# =========================
# ADD TO CART
# =========================
@cart_bp.route('/add/<slug>', methods=['POST'])
def add_to_cart(slug):

    product = Product.query.filter_by(slug=slug).first_or_404()
    source = request.form.get("source")

    user_key = get_user_key()

    if current_user.is_authenticated:
        cart = Cart.query.filter_by(user_id=current_user.id).first()
    else:
        cart = Cart.query.filter_by(user_key=user_key).first()

    if not cart:
        if current_user.is_authenticated:
            cart = Cart(user_id=current_user.id)
        else:
            cart = Cart(user_key=user_key)

        db.session.add(cart)
        db.session.flush()

    item = CartItem.query.filter_by(
        cart_id=cart.id,
        product_id=product.id
    ).first()

    already_in_cart = item is not None

    if not item:
        db.session.add(CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=1,
            unit_price=product.price,
            from_wishlist=(source == "wishlist")
        ))

    # remove from wishlist if logged in
    if current_user.is_authenticated:
        Wishlist.query.filter_by(
            user_id=current_user.id,
            product_id=product.id
        ).delete()
    else:
        Wishlist.query.filter_by(
            user_key=user_key,
            product_id=product.id
        ).delete()

    db.session.commit()

    cart_count = db.session.query(
        db.func.coalesce(db.func.sum(CartItem.quantity), 0)
    ).filter_by(cart_id=cart.id).scalar() or 0

    if current_user.is_authenticated:
        wishlist_count = Wishlist.query.filter_by(
            user_id=current_user.id
        ).count()
    else:
        wishlist_count = Wishlist.query.filter_by(
            user_key=user_key
        ).count()

    return jsonify({
        "success": True,
        "cart_count": cart_count,
        "already_in_cart": already_in_cart,
        "wishlist_count": wishlist_count
    })


# =========================
# REMOVE ITEM
# =========================
@cart_bp.route('/remove/<int:item_id>', methods=['POST'])
def remove_item(item_id):

    user_key = get_user_key()

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        (
            (Cart.user_id == current_user.id)
            if current_user.is_authenticated
            else (Cart.user_key == user_key)
        )
    ).first_or_404()

    cart = item.cart

    db.session.delete(item)
    db.session.commit()

    cart_count = db.session.query(CartItem).filter_by(cart_id=cart.id).count()

    cart_total = db.session.query(
        db.func.sum(CartItem.quantity * Product.price)
    ).join(Product).filter(
        CartItem.cart_id == cart.id
    ).scalar() or 0

    return jsonify({
        "success": True,
        "cart_count": cart_count,
        "cart_total": cart_total
    })


# =========================
# INCREASE QTY
# =========================
@cart_bp.route('/increase/<int:item_id>', methods=['POST'])
def increase_qty(item_id):

    user_key = get_user_key()

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        (
            (Cart.user_id == current_user.id)
            if current_user.is_authenticated
            else (Cart.user_key == user_key)
        )
    ).first_or_404()

    item.quantity += 1
    db.session.commit()

    cart = item.cart

    cart_total = db.session.query(
        db.func.sum(CartItem.quantity * Product.price)
    ).join(Product).filter(
        CartItem.cart_id == cart.id
    ).scalar() or 0

    return jsonify({
        "success": True,
        "quantity": item.quantity,
        "subtotal": item.quantity * item.product.price,
        "deleted": False,
        "cart_total": cart_total
    })


# =========================
# DECREASE QTY
# =========================
@cart_bp.route('/decrease/<int:item_id>', methods=['POST'])
def decrease_qty(item_id):

    user_key = get_user_key()

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        (
            (Cart.user_id == current_user.id)
            if current_user.is_authenticated
            else (Cart.user_key == user_key)
        )
    ).first_or_404()

    cart = item.cart

    if item.quantity > 1:
        item.quantity -= 1
        db.session.commit()
        deleted = False
    else:
        db.session.delete(item)
        db.session.commit()
        deleted = True

    cart_total = db.session.query(
        db.func.sum(CartItem.quantity * Product.price)
    ).join(Product).filter(
        CartItem.cart_id == cart.id
    ).scalar() or 0

    return jsonify({
        "success": True,
        "quantity": item.quantity if not deleted else 0,
        "subtotal": item.quantity * item.product.price if not deleted else 0,
        "deleted": deleted,
        "cart_total": cart_total
    })


# =========================
# CHECKOUT START
# =========================
@cart_bp.route("/checkout/start")
@login_required
def start_checkout():

    # =========================
    # MERGE GUEST CART → USER
    # =========================
    guest_key = session.get("user_key")

    if guest_key:
        guest_cart = Cart.query.filter_by(user_key=guest_key).first()
        user_cart = Cart.query.filter_by(user_id=current_user.id).first()

        if guest_cart:
            if not user_cart:
                guest_cart.user_id = current_user.id
                guest_cart.user_key = None
            else:
                for item in guest_cart.items:
                    existing = CartItem.query.filter_by(
                        cart_id=user_cart.id,
                        product_id=item.product_id
                    ).first()

                    if existing:
                        existing.quantity += item.quantity
                    else:
                        item.cart_id = user_cart.id

                db.session.delete(guest_cart)

            db.session.commit()

        # remove guest key after merge
        session.pop("user_key", None)

    # =========================
    # GET USER CART
    # =========================
    cart = Cart.query.filter_by(user_id=current_user.id).first()

    if not cart or not cart.items:
        flash("Your cart is empty", "warning")
        return redirect(url_for("cart.view_cart"))

    # =========================
    # CREATE CHECKOUT SESSION
    # =========================
    draft = CheckoutDraft.query.filter_by(user_id=current_user.id).first()

    if not draft:
        draft = CheckoutDraft(
            user_id=current_user.id,
            email=current_user.email
        )
        db.session.add(draft)
        db.session.commit()

    # 🔥 ALWAYS set session (important fix)
    session["checkout_id"] = draft.id

    return redirect(url_for("checkout.details"))