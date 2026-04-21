import os
import uuid
from werkzeug.utils import secure_filename

from flask import render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime, timedelta

from app.forms import DeleteForm
from app.utils.decorators import admin_required
from app.utils.helpers import generate_slug

from . import admin_bp
from app.extensions import db
from app.models import CartItem, Product, Category, Order, Wishlist

from werkzeug.utils import secure_filename
from slugify import slugify


# =========================
# ADMIN DASHBOARD
# =========================

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():

    # =========================
    # STATS (NUMBERS ONLY)
    # =========================
    total_products = Product.query.count()
    total_categories = Category.query.count()
    total_orders = Order.query.count()

    total_sales = db.session.query(
        func.sum(Order.total_amount)
    ).scalar() or 0

    delete_form = DeleteForm()

    # =========================
    # DISPLAY DATA (LISTS ONLY)
    # =========================
    recent_products = Product.query.order_by(Product.created_at.desc()).limit(12).all()

    recent_orders = Order.query.order_by(Order.id.desc()).limit(20).all()

    categories_available = Category.query.order_by(Category.id.desc()).all()

    return render_template(
        'admin/dashboard.html',

        # stats
        products=total_products,
        categories=total_categories,
        orders=total_orders,
        total_sales=total_sales,

        # display data
        recent_products=recent_products,
        recent_orders=recent_orders,
        categories_available=categories_available,
        delete_form=delete_form
    )

# =========================
# PRODUCTS LIST
# =========================
@admin_bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@admin_required 
def add_product():

    #GET categories for dropdown
    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':

        name = request.form.get('name')
        description = request.form.get('description')
        short_description = request.form.get('short_description')
        category_id = request.form.get('category_id')
        price = request.form.get('price')
        stock_quantity = request.form.get('stock_quantity')


        if not category_id:
            flash("Please select a category", "danger")
            return redirect(request.url)

        if not name or not price:
            flash("Name and price are required", "danger")
            return redirect(request.url)

        # convert category_id to int
        category_id = int(category_id)

        # slug auto generation
        slug = generate_slug(name)

        # image upload
        image = request.files.get('image')
        image_filename = None

        if image and image.filename != "":
            filename = secure_filename(image.filename)

            # prevent overwrite (IMPORTANT)
           
            unique_filename = f"{uuid.uuid4().hex}_{filename}"

            upload_path = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                unique_filename
            )

            image.save(upload_path)
            image_filename = unique_filename

        # create product
        product = Product(
            name=name,
            slug=slug,
            description=description,
            short_description=short_description,
            price=price,
            category_id=category_id,
            stock_quantity=stock_quantity,
            image=image_filename
        )

        db.session.add(product)
        db.session.commit()

        flash("Product added successfully!", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template(
        'admin/add_product.html',
        categories=categories
    )

# =========================
# EDIT PRODUCT
# =========================
@admin_bp.route('/products/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    categories = Category.query.all()

    if request.method == 'POST':
        product.name = request.form.get('name')
        product.price = request.form.get('price')
        product.description = request.form.get('description')
        product.category_id = request.form.get('category_id')

        db.session.commit()

        flash("Product updated successfully!", "success")
        return redirect(url_for('admin.products'))

    return render_template(
        'admin/edit_product.html',
        product=product,
        categories=categories
    )


# =========================
# DELETE PRODUCT
# =========================
@admin_bp.route('/product/delete/<slug>', methods=['POST'])
def delete_product(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()


    # manually clean dependencies
    CartItem.query.filter_by(product_id=product.id).delete()
    Wishlist.query.filter_by(product_id=product.id).delete()


    db.session.delete(product)
    db.session.commit()

    flash("Product deleted successfully", "success")
    return redirect(url_for('admin.dashboard'))


# =========================
# ORDERS VIEW
# =========================
@admin_bp.route('/orders')
@login_required
def orders():
    orders = Order.query.order_by(Order.id.desc()).all()
    return render_template('admin/orders.html', orders=orders)


# =========================
# VIEW SINGLE ORDER
# =========================
@admin_bp.route('/orders/<int:id>')
@login_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    return render_template('admin/order_detail.html', order=order)



# =========================
# UPDATE ORDER STATUS
# =========================
@admin_bp.route('/orders/update/<int:id>', methods=['POST'])
@login_required
def update_order_status(id):
    order = Order.query.get_or_404(id)

    new_status = request.form.get('status')
    order.status = new_status

    db.session.commit()
    flash("Order status updated!", "success")

    return redirect(url_for('admin.orders'))




@admin_bp.route('/category/add', methods=['GET', 'POST'])
def add_category():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        image_file = request.files.get('image')

        if not name:
            flash("Category name is required", "danger")
            return redirect(url_for('admin.add_category'))

        slug = slugify(name)

        # prevent duplicates
        if Category.query.filter_by(slug=slug).first():
            flash("Category already exists", "warning")
            return redirect(url_for('admin.add_category'))

        filename = None

        # handle image upload
        if image_file and image_file.filename != "":
            ext = image_file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"

            upload_path = os.path.join(current_app.root_path, 'static/uploads/categories')
            os.makedirs(upload_path, exist_ok=True)

            image_file.save(os.path.join(upload_path, filename))

        category = Category(
            name=name,
            slug=slug,
            description=description,
            image=filename
        )

        db.session.add(category)
        db.session.commit()

        flash("Category created successfully", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/add_category.html')


@admin_bp.route('/category/delete/<int:id>', methods=['POST'])
def delete_category(id):

    
    category = Category.query.get_or_404(id)

    # OPTIONAL SAFETY: prevent deleting categories with products
    if Product.query.filter_by(category_id=id).first():
        flash("Cannot delete category with existing products", "danger")
        return redirect(url_for('admin.dashboard'))

    db.session.delete(category)
    db.session.commit()

    flash("Category deleted successfully", "success")
    return redirect(url_for('admin.dashboard'))