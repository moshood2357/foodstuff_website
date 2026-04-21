from flask import jsonify, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Wishlist, Product
from . import wishlist_bp


from sqlalchemy import join



@wishlist_bp.route('/wishlist')
@login_required
def view_wishlist():

    wishlist_items = (
        db.session.query(Wishlist, Product)
        .join(Product, Wishlist.product_id == Product.id)
        .filter(Wishlist.user_id == current_user.id)
        .all()
    )

    return render_template(
        "wishlist/wishlist.html",
        wishlist_items=wishlist_items
    )

@wishlist_bp.route('/add/<slug>', methods=['POST'])
@login_required
def add_to_wishlist(slug):

    product = Product.query.filter_by(slug=slug).first_or_404()

    item = Wishlist.query.filter_by(
        user_id=current_user.id,
        product_id=product.id
    ).first()

    if item:
        db.session.delete(item)
        action = "removed"
    else:
        db.session.add(Wishlist(
            user_id=current_user.id,
            product_id=product.id
        ))
        action = "added"

    db.session.commit()

    wishlist_count = Wishlist.query.filter_by(
        user_id=current_user.id
    ).count()

    return jsonify({
        "success": True,
        "action": action,
        "wishlist_count": wishlist_count
    })




@wishlist_bp.route('/remove/<slug>', methods=['POST'])
@login_required
def remove_from_wishlist(slug):

    product = Product.query.filter_by(slug=slug).first_or_404()

    item = Wishlist.query.filter_by(
        user_id=current_user.id,
        product_id=product.id
    ).first()

    if item:
        db.session.delete(item)
        db.session.commit()

    wishlist_count = Wishlist.query.filter_by(
        user_id=current_user.id
    ).count()

    return jsonify({"success": True, "message": "Item removed from wishlist", "wishlist_count": wishlist_count})