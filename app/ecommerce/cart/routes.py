from flask import flash, redirect, render_template, jsonify, request, session, session, url_for
from flask_login import login_required, current_user
from . import cart_bp
from app.models import Product, CartItem, Cart, Wishlist, CheckoutDraft
from app.extensions import db


# =========================
# VIEW CART
# =========================
@cart_bp.route('/')
@login_required
def view_cart():

    cart = Cart.query.filter_by(user_id=current_user.id).first()

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
# ADD TO CART (AJAX)
# =========================
@cart_bp.route('/add/<slug>', methods=['POST'])
def add_to_cart(slug):

    product = Product.query.filter_by(slug=slug).first_or_404()

    source = request.form.get("source")

    cart = Cart.query.filter_by(user_id=current_user.id).first()

    if not cart:
        cart = Cart(user_id=current_user.id)
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

    Wishlist.query.filter_by(
        user_id=current_user.id,
        product_id=product.id
    ).delete()

    db.session.commit()

    cart_count = db.session.query(
        db.func.coalesce(db.func.sum(CartItem.quantity), 0)
    ).filter_by(cart_id=cart.id).scalar() or 0

    wishlist_count = Wishlist.query.filter_by(
        user_id=current_user.id
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

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        Cart.user_id == current_user.id
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

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        Cart.user_id == current_user.id
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
@login_required
def decrease_qty(item_id):

    item = CartItem.query.join(Cart).filter(
        CartItem.id == item_id,
        Cart.user_id == current_user.id
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

@cart_bp.route("/checkout/start")
@login_required
def start_checkout():

    cart = Cart.query.filter_by(user_id=current_user.id).first()

    if not cart or not cart.items:
        flash("Your cart is empty", "warning")
        return redirect(url_for("cart.view_cart"))

    # check existing draft
    draft = CheckoutDraft.query.filter_by(user_id=current_user.id).first()

    if not draft:
        draft = CheckoutDraft(
            user_id=current_user.id,
            email=current_user.email
        )
        db.session.add(draft)
        db.session.commit()

        session["checkout_id"] = draft.id

    return redirect(url_for("checkout.details"))        