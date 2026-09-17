
import os
import uuid
from werkzeug.utils import secure_filename

from flask import render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime
from app import csrf

from app.forms import DeleteForm
from app.utils.decorators import admin_required
from app.utils.helpers import generate_slug
from app.utils.qr import generate_product_qr, generate_product_barcode


from . import admin_bp
from app.extensions import db
from app.models import CartItem, OrderStatus, PaymentStatus, Product, Category, Order, Wishlist

from werkzeug.utils import secure_filename
from slugify import slugify


import json
import time
from flask import Response, stream_with_context


# ====================
# AJAX ENDPOINT TO GET LATEST ORDER ID
# ====================
@admin_bp.route("/orders/latest-id")
@login_required
@admin_required
def latest_order_id():
    from flask import jsonify
    order = Order.query.order_by(Order.id.desc()).first()
    total = Order.query.count()
    return jsonify({
        "latest_id":    order.id if order else 0,
        "total_orders": total
    })


# =========================
# ADMIN DASHBOARD
# =========================
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_products   = Product.query.count()
    total_categories = Category.query.count()
    total_orders     = Order.query.count()

    total_sales = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.payment_status == PaymentStatus.paid
    ).scalar()

    delete_form      = DeleteForm()
    recent_products  = Product.query.order_by(Product.created_at.desc()).limit(12).all()
    categories_available = Category.query.order_by(Category.id.desc()).all()

    return render_template(
        'admin/dashboard.html',
        products=total_products,
        categories=total_categories,
        orders=total_orders,
        total_sales=total_sales,
        recent_products=recent_products,
        categories_available=categories_available,
        delete_form=delete_form
    )


# =========================
# ADD PRODUCT
# =========================
@admin_bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':
        name              = request.form.get('name')
        description       = request.form.get('description')
        short_description = request.form.get('short_description')
        category_id       = request.form.get('category_id')
        price             = request.form.get('price')
        stock_quantity    = request.form.get('stock_quantity')

        if not category_id:
            flash("Please select a category", "danger")
            return redirect(request.url)

        if not name or not price:
            flash("Name and price are required", "danger")
            return redirect(request.url)

        category_id = int(category_id)
        slug        = generate_slug(name)

        image          = request.files.get('image')
        image_filename = None

        if image and image.filename != "":
            filename        = secure_filename(image.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            upload_path     = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            image.save(upload_path)
            image_filename = unique_filename

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
        db.session.flush()  # get product.id and slug before generating QR

                
        # auto-generate SKU if not provided
        if not product.sku:
            product.sku = f"JES-{str(product.id).zfill(5)}"
        try:
            product.qr_code       = generate_product_qr(product)
            product.barcode_image = generate_product_barcode(product)
        except Exception as e:
            print(f"Image generation failed: {e}")

        db.session.commit()

        flash("Product added successfully!", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/add_product.html', categories=categories)


# =========================
# DELETE PRODUCT
# =========================
@admin_bp.route('/product/delete/<slug>', methods=['POST'])
def delete_product(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()

    CartItem.query.filter_by(product_id=product.id).delete()
    Wishlist.query.filter_by(product_id=product.id).delete()

    # delete QR file
    if product.qr_code:
        qr_path = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes', product.qr_code)
        if os.path.exists(qr_path):
            os.remove(qr_path)

    # delete barcode file
    if product.barcode_image:
        bc_path = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes', product.barcode_image)
        if os.path.exists(bc_path):
            os.remove(bc_path)

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
    page   = request.args.get('page', 1, type=int)
    orders = Order.query.order_by(Order.id.desc()).paginate(page=page, per_page=20)
    return render_template('admin/orders.html', orders=orders)


# =========================
# UPDATE ORDER STATUS
# =========================
@admin_bp.route("/orders/update/<int:id>", methods=["POST"])
@csrf.exempt
@login_required
def update_order_status(id):
    from flask import jsonify
    from app.utils.email import send_order_confirmation_customer, send_order_rejected_customer

    order     = Order.query.get_or_404(id)
    data      = request.get_json()
    status    = data.get("status")
    prep_time = data.get("prep_time")
    reason    = data.get("rejection_reason", "").strip()

    print(f"update_order_status called: order={id}, status={status}, prep_time={prep_time}")

    try:
        order.status = OrderStatus[status]

        if prep_time:
            order.prep_time = int(prep_time)

        if status in ["cancelled", "on_hold", "refunded", "returned"] and reason:
            order.rejection_reason = reason

        db.session.commit()

        # send notifications based on new status
        if status == "payment_confirmed":
            try:
                send_order_confirmation_customer(order)
            except Exception as e:
                print(f"Confirmation email failed: {e}")

        elif status == "accepted":
            try:
                send_order_confirmation_customer(order)
            except Exception as e:
                print(f"Customer email failed: {e}")

        elif status == "dispatched":
            try:
                from app.utils.sms import send_sms
                phone = order.address.phone if order.address else None
                if phone:
                    send_sms(phone,
                        f"Hi {order.address.full_name}, your order {order.order_number} "
                        f"from Judith Ethnic Food Store is on its way!"
                    )
            except Exception as e:
                print(f"Dispatch SMS failed: {e}")

        elif status == "ready_for_dispatch" and order.fulfillment_type == "pickup":
            try:
                from app.utils.sms import send_sms
                phone = order.address.phone if order.address else None
                if phone:
                    send_sms(phone,
                        f"Hi {order.address.full_name}, your order {order.order_number} "
                        f"is ready for collection at 311 High Street, Cheltenham."
                    )
            except Exception as e:
                print(f"Collection SMS failed: {e}")

        elif status == "cancelled" and reason:
            try:
                send_order_rejected_customer(order, reason)
            except Exception as e:
                print(f"Rejection email failed: {e}")

        return jsonify({"success": True})

    except KeyError:
        return jsonify({"success": False, "error": f"Invalid status: {status}"}), 400

    except Exception as e:
        db.session.rollback()
        print(f"update_order_status error: {e}")
        import traceback
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)}), 500


# =========================
# ADD CATEGORY
# =========================
@admin_bp.route('/category/add', methods=['GET', 'POST'])
def add_category():
    if request.method == 'POST':
        name        = request.form.get('name')
        description = request.form.get('description')
        image_file  = request.files.get('image')

        if not name:
            flash("Category name is required", "danger")
            return redirect(url_for('admin.add_category'))

        slug = slugify(name)

        if Category.query.filter_by(slug=slug).first():
            flash("Category already exists", "warning")
            return redirect(url_for('admin.add_category'))

        filename = None

        if image_file and image_file.filename != "":
            ext      = image_file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            upload_path = os.path.join(current_app.root_path, 'static/uploads/categories')
            os.makedirs(upload_path, exist_ok=True)
            image_file.save(os.path.join(upload_path, filename))

        category = Category(name=name, slug=slug, description=description, image=filename)
        db.session.add(category)
        db.session.commit()

        flash("Category created successfully", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/add_category.html')


# =========================
# DELETE CATEGORY
# =========================
@admin_bp.route('/category/delete/<int:id>', methods=['POST'])
def delete_category(id):
    category = Category.query.get_or_404(id)

    if Product.query.filter_by(category_id=id).first():
        flash("Cannot delete category with existing products", "danger")
        return redirect(url_for('admin.dashboard'))

    db.session.delete(category)
    db.session.commit()

    flash("Category deleted successfully", "success")
    return redirect(url_for('admin.dashboard'))


# =========================
# EDIT CATEGORY
# =========================
@admin_bp.route('/category/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(id):
    category = Category.query.get_or_404(id)

    if request.method == 'POST':
        name        = request.form.get('name')
        description = request.form.get('description')
        image_file  = request.files.get('image')

        if not name:
            flash("Category name is required", "danger")
            return redirect(request.url)

        category.name        = name
        category.slug        = slugify(name)
        category.description = description

        if image_file and image_file.filename != "":
            ext      = image_file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            upload_path = os.path.join(current_app.root_path, 'static/uploads/categories')
            os.makedirs(upload_path, exist_ok=True)
            image_file.save(os.path.join(upload_path, filename))
            category.image = filename

        db.session.commit()
        flash("Category updated successfully", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/edit_category.html', category=category)


# =========================
# EDIT PRODUCT
# =========================
@admin_bp.route('/products/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(id):
    product    = Product.query.get_or_404(id)
    categories = Category.query.order_by(Category.name).all()

    if request.method == 'POST':
        name              = request.form.get('name')
        description       = request.form.get('description')
        short_description = request.form.get('short_description')
        category_id       = request.form.get('category_id')
        price             = request.form.get('price')
        stock_quantity    = request.form.get('stock_quantity')

        if not name or not price:
            flash("Name and price are required", "danger")
            return redirect(request.url)

        if not category_id:
            flash("Please select a category", "danger")
            return redirect(request.url)

        old_slug     = product.slug
        product.name = name
        product.slug = generate_slug(name)
        product.description       = description
        product.short_description = short_description
        product.price             = price
        product.category_id       = int(category_id)
        product.stock_quantity    = stock_quantity

        image = request.files.get('image')
        if image and image.filename != "":
            filename        = secure_filename(image.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            upload_path     = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            image.save(upload_path)

            if product.image:
                old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], product.image)
                if os.path.exists(old_path):
                    os.remove(old_path)

            product.image = unique_filename

        
       # regenerate QR and barcode if slug changed or either is missing
        if product.slug != old_slug or not product.qr_code or not product.barcode_image:
            try:
                # delete old files
                for old_file in [product.qr_code, product.barcode_image]:
                    if old_file:
                        old_path = os.path.join(
                            current_app.root_path, 'static', 'uploads', 'qrcodes', old_file
                        )
                        if os.path.exists(old_path):
                            os.remove(old_path)

                product.qr_code       = generate_product_qr(product)
                product.barcode_image = generate_product_barcode(product)
            except Exception as e:
                print(f"Image generation failed: {e}")
        db.session.commit()
        flash("Product updated successfully!", "success")
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/edit_product.html', product=product, categories=categories)


# =========================
# PRODUCT LABEL (PRINTABLE - BARCODE)
# =========================
@admin_bp.route('/products/label/<int:id>')
@login_required
@admin_required
def product_label(id):
    product = Product.query.get_or_404(id)

    # generate barcode if missing
    if not product.barcode_image:
        try:
            # product.qr_code = generate_product_qr(product)
            product.barcode_image = generate_product_barcode(product)
            db.session.commit()
        except Exception as e:
            print(f"QR generation failed: {e}")

    return render_template('admin/product_label.html', product=product)


# =========================
# BULK GENERATE QR CODE AND BARCODE (for existing products)
# =========================
@admin_bp.route('/products/generate-both-all')
@login_required
@admin_required
def generate_both_all():
    from app.utils.qr import generate_product_qr, generate_product_barcode
    products = Product.query.all()
    count    = 0

    for product in products:
        try:
            product.qr_code       = generate_product_qr(product)
            product.barcode_image = generate_product_barcode(product)
            count += 1
        except Exception as e:
            print(f"Failed for {product.name}: {e}")

    db.session.commit()
    flash(f"Generated QR codes and barcodes for {count} products.", "success")
    return redirect(url_for('admin.dashboard'))

# ======================
# QR LABEL (PRINTABLE)
# ======================
@admin_bp.route('/products/qr-label/<int:id>')
@login_required
@admin_required
def product_qr_label(id):
    product = Product.query.get_or_404(id)

    if not product.qr_code:
        try:
            product.qr_code = generate_product_qr(product)
            db.session.commit()
        except Exception as e:
            print(f"QR generation failed: {e}")

    return render_template('admin/product_qr_label.html', product=product)



# ========================
# ORDER STREAM (SSE)
# ========================

@admin_bp.route('/orders/stream')
@login_required
@admin_required
def order_stream():
    """Server-Sent Events endpoint for real-time order notifications."""
    def generate():
        last_id = Order.query.order_by(Order.id.desc()).first()
        last_id = last_id.id if last_id else 0

        while True:
            time.sleep(5)  # check every 5 seconds

            latest = Order.query.order_by(Order.id.desc()).first()
            latest_id    = latest.id if latest else 0
            total_orders = Order.query.count()
            new_orders   = Order.query.filter(
                db.cast(Order.status, db.Text) == 'new'
            ).count()

            if latest_id > last_id:
                last_id = latest_id
                data = json.dumps({
                    'new_order':    True,
                    'total_orders': total_orders,
                    'new_orders':   new_orders,
                    'order_number': latest.order_number,
                })
            else:
                data = json.dumps({
                    'new_order':    False,
                    'total_orders': total_orders,
                    'new_orders':   new_orders,
                })

            yield f"data: {data}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control':               'no-cache',
            'X-Accel-Buffering':           'no',
            'Access-Control-Allow-Origin': '*',
        }
    )