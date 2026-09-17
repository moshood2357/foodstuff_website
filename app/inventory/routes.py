import uuid
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models import (
    Product, ProductVariant, Supplier, StockMovement,
    PurchaseOrder, PurchaseOrderItem, StockAlert,
    Category, MovementType, POStatus, User, BinLocation
)
from app.utils.decorators import admin_required
from app.utils.helpers import generate_slug
from app.utils.qr import generate_product_qr, generate_product_barcode, generate_variant_barcode, generate_variant_qr

from . import inventory_bp
import os
from werkzeug.utils import secure_filename


# =========================
# INVENTORY DASHBOARD
# =========================
@inventory_bp.route('/')
@login_required
@admin_required
def dashboard():
    total_products  = Product.query.filter_by(is_active=True).count()
    total_variants  = ProductVariant.query.filter_by(is_active=True).count()
    total_suppliers = Supplier.query.filter_by(is_active=True).count()
    total_pos       = PurchaseOrder.query.filter_by(status=POStatus.sent).count()

    # low stock — variants below threshold
    low_stock = ProductVariant.query.filter(
        ProductVariant.stock_quantity <= ProductVariant.low_stock_threshold,
        ProductVariant.is_active == True
    ).all()

    # also check products without variants
    low_stock_products = Product.query.filter(
        Product.has_variants == False,
        Product.stock_quantity <= Product.low_stock_threshold,
        Product.is_active == True
    ).all()

    # recent movements
    recent_movements = StockMovement.query.order_by(
        StockMovement.created_at.desc()
    ).limit(10).all()

    # pending POs
    pending_pos = PurchaseOrder.query.filter(
        PurchaseOrder.status.in_([POStatus.draft, POStatus.sent, POStatus.partial])
    ).order_by(PurchaseOrder.created_at.desc()).limit(5).all()

    # stock value
    stock_value = db.session.query(
        func.coalesce(
            func.sum(Product.cost_price * Product.stock_quantity), 0
        )
    ).filter(Product.has_variants == False).scalar()

    variant_value = db.session.query(
        func.coalesce(
            func.sum(ProductVariant.cost_price * ProductVariant.stock_quantity), 0
        )
    ).scalar()

    total_stock_value = float(stock_value or 0) + float(variant_value or 0)

    return render_template(
        'inventory/dashboard.html',
        total_products=total_products,
        total_variants=total_variants,
        total_suppliers=total_suppliers,
        total_pos=total_pos,
        low_stock=low_stock,
        low_stock_products=low_stock_products,
        recent_movements=recent_movements,
        pending_pos=pending_pos,
        total_stock_value=total_stock_value,
    )


# =========================
# PRODUCTS
# =========================
@inventory_bp.route('/products')
@login_required
@admin_required
def products():
    page     = request.args.get('page', 1, type=int)
    search   = request.args.get('q', '')
    category = request.args.get('category', '')

    query = Product.query

    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    if category:
        query = query.filter(Product.category_id == int(category))

    products    = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=20)
    categories  = Category.query.all()
    suppliers   = Supplier.query.filter_by(is_active=True).all()

    return render_template(
        'inventory/products.html',
        products=products,
        categories=categories,
        suppliers=suppliers,
        search=search,
    )


@inventory_bp.route('/products/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_product():
    categories = Category.query.order_by(Category.name).all()
    suppliers  = Supplier.query.filter_by(is_active=True).all()
    bins       = BinLocation.query.filter_by(is_active=True).order_by(BinLocation.name).all()

    if request.method == 'POST':
        name              = request.form.get('name')
        description       = request.form.get('description', '')
        short_description = request.form.get('short_description', '')
        category_id       = request.form.get('category_id')
        supplier_id       = request.form.get('supplier_id') or None
        price             = request.form.get('price')
        bin_location_id = request.form.get('bin_location_id')
        cost_price        = request.form.get('cost_price') or None
        stock_quantity    = request.form.get('stock_quantity', 0)
        low_stock_threshold = request.form.get('low_stock_threshold', 10)
        has_variants      = request.form.get('has_variants') == 'on'
        brand             = request.form.get('brand', '')

        if not name or not price or not category_id:
            flash("Name, price and category are required.", "danger")
            return redirect(request.url)

        slug = generate_slug(name)

        # image upload
        image          = request.files.get('image')
        image_filename = None
        if image and image.filename:
            filename        = secure_filename(image.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            image.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
            image_filename = unique_filename

        product = Product(
            name=name, slug=slug,
            description=description,
            short_description=short_description,
            category_id=int(category_id),
            supplier_id=int(supplier_id) if supplier_id else None,
            price=price, cost_price=cost_price,
            stock_quantity=int(stock_quantity),
            low_stock_threshold=int(low_stock_threshold),
            has_variants=has_variants,
            brand=brand, image=image_filename,
            is_active=True,
        )

        db.session.add(product)
        db.session.flush()

        # auto SKU
        if not product.sku:
            product.sku = f"JES-{str(product.id).zfill(5)}"

        # generate QR
        try:
            product.qr_code       = generate_product_qr(product)
            product.barcode_image = generate_product_barcode(product)
        except Exception as e:
            print(f"Image generation failed: {e}")

        # record initial stock movement
        if int(stock_quantity) > 0 and not has_variants:
            movement = StockMovement(
                product_id=product.id,
                created_by=current_user.id,
                movement_type=MovementType.adjustment,
                quantity=int(stock_quantity),
                stock_before=0,
                stock_after=int(stock_quantity),
                note="Initial stock"
            )
            db.session.add(movement)

        db.session.commit()
        flash(f"Product '{name}' added to inventory.", "success")
        return redirect(url_for('inventory.product_detail', id=product.id))

    return render_template(
        'inventory/add_product.html',
        categories=categories,
        suppliers=suppliers,
        bins=bins
    )


@inventory_bp.route('/products/<int:id>')
@login_required
@admin_required
def product_detail(id):
    product    = Product.query.get_or_404(id)
    movements  = StockMovement.query.filter_by(
        product_id=id
    ).order_by(StockMovement.created_at.desc()).limit(20).all()

    return render_template(
        'inventory/product_detail.html',
        product=product,
        movements=movements,
    )


@inventory_bp.route('/products/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(id):
    product    = Product.query.get_or_404(id)
    categories = Category.query.order_by(Category.name).all()
    suppliers  = Supplier.query.filter_by(is_active=True).all()
    bins       = BinLocation.query.filter_by(is_active=True).order_by(BinLocation.name).all()

    if request.method == 'POST':
        product.name              = request.form.get('name')
        product.description       = request.form.get('description', '')
        product.short_description = request.form.get('short_description', '')
        bin_location_id = request.form.get('bin_location_id')
        product.bin_location_id = int(bin_location_id) if bin_location_id else None
        product.category_id       = int(request.form.get('category_id'))
        product.supplier_id       = int(request.form.get('supplier_id')) if request.form.get('supplier_id') else None
        product.price             = request.form.get('price')
        product.cost_price        = request.form.get('cost_price') or None
        product.low_stock_threshold = int(request.form.get('low_stock_threshold') or 10)
        product.brand             = request.form.get('brand', '')
        product.is_active         = request.form.get('is_active') == 'on'
        product.is_featured       = request.form.get('is_featured') == 'on'
        product.slug              = generate_slug(product.name)

        image = request.files.get('image')
        if image and image.filename:
            filename        = secure_filename(image.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            image.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
            product.image = unique_filename

        db.session.commit()
        flash("Product updated.", "success")
        return redirect(url_for('inventory.product_detail', id=product.id))

    return render_template(
        'inventory/edit_product.html',
        product=product,
        categories=categories,
        suppliers=suppliers,
        bins=bins
    )


# =========================
# VARIANTS
# =========================
@inventory_bp.route('/products/<int:product_id>/variants/add', methods=['POST'])
@login_required
@admin_required
def add_variant(product_id):
    product = Product.query.get_or_404(product_id)

    name           = request.form.get('name')
    price          = request.form.get('price')
    cost_price     = request.form.get('cost_price') or None
    stock_quantity = int(request.form.get('stock_quantity', 0))
    low_stock_threshold = int(request.form.get('low_stock_threshold') or 10)

    if not name or not price:
        flash("Variant name and price required.", "danger")
        return redirect(url_for('inventory.product_detail', id=product_id))

    variant = ProductVariant(
        product_id=product_id,
        name=name,
        sku=f"{product.sku}-{name.upper().replace(' ', '')}",
        price=price,
        cost_price=cost_price,
        stock_quantity=stock_quantity,
        low_stock_threshold=low_stock_threshold,
        is_active=True,
    )

    db.session.add(variant)
    db.session.flush()

    # generate QR for variant
    try:
        variant.qr_code       = generate_variant_qr(product, variant)
        variant.barcode_image = generate_variant_barcode(variant)
    except Exception as e:
        print(f"Variant image generation failed: {e}")


    # record stock movement
    if stock_quantity > 0:
        movement = StockMovement(
            product_id=product_id,
            variant_id=variant.id,
            created_by=current_user.id,
            movement_type=MovementType.adjustment,
            quantity=stock_quantity,
            stock_before=0,
            stock_after=stock_quantity,
            note=f"Initial stock for variant {name}"
        )
        db.session.add(movement)

    product.has_variants = True
    db.session.commit()

    flash(f"Variant '{name}' added.", "success")
    return redirect(url_for('inventory.product_detail', id=product_id))





# =========================
# STOCK ADJUSTMENT
# =========================
@inventory_bp.route('/adjust', methods=['POST'])
@login_required
@admin_required
def adjust_stock():
    product_id  = request.form.get('product_id')
    variant_id  = request.form.get('variant_id')
    quantity    = int(request.form.get('quantity', 0))
    movement_type = request.form.get('movement_type', 'adjustment')
    note        = request.form.get('note', '')

    if variant_id:
        obj = ProductVariant.query.get_or_404(int(variant_id))
    else:
        obj = Product.query.get_or_404(int(product_id))

    stock_before        = obj.stock_quantity
    obj.stock_quantity  = max(0, stock_before + quantity)

    movement = StockMovement(
        product_id  = int(product_id) if product_id else None,
        variant_id  = int(variant_id) if variant_id else None,
        created_by  = current_user.id,
        movement_type = MovementType[movement_type],
        quantity    = quantity,
        stock_before = stock_before,
        stock_after  = obj.stock_quantity,
        note        = note,
    )
    db.session.add(movement)
    db.session.commit()

    flash(f"Stock adjusted by {quantity:+d}. New stock: {obj.stock_quantity}", "success")
    return redirect(request.referrer or url_for('inventory.dashboard'))


# =========================
# STOCK MOVEMENTS
# =========================
@inventory_bp.route('/movements')
@login_required
@admin_required
def movements():
    page      = request.args.get('page', 1, type=int)
    movements = StockMovement.query.order_by(
        StockMovement.created_at.desc()
    ).paginate(page=page, per_page=30)
    return render_template('inventory/movements.html', movements=movements)


# =========================
# SUPPLIERS
# =========================
@inventory_bp.route('/suppliers')
@login_required
@admin_required
def suppliers():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template('inventory/suppliers.html', suppliers=suppliers)


@inventory_bp.route('/suppliers/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_supplier():
    if request.method == 'POST':
        supplier = Supplier(
            name=request.form.get('name'),
            contact_name=request.form.get('contact_name'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            address=request.form.get('address'),
            website=request.form.get('website'),
            lead_time_days=int(request.form.get('lead_time_days', 7)),
            notes=request.form.get('notes'),
        )
        db.session.add(supplier)
        db.session.commit()
        flash(f"Supplier '{supplier.name}' added.", "success")
        return redirect(url_for('inventory.suppliers'))

    return render_template('inventory/add_supplier.html')


@inventory_bp.route('/suppliers/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_supplier(id):
    supplier = Supplier.query.get_or_404(id)

    if request.method == 'POST':
        supplier.name          = request.form.get('name')
        supplier.contact_name  = request.form.get('contact_name')
        supplier.email         = request.form.get('email')
        supplier.phone         = request.form.get('phone')
        supplier.address       = request.form.get('address')
        supplier.website       = request.form.get('website')
        supplier.lead_time_days = int(request.form.get('lead_time_days', 7))
        supplier.notes         = request.form.get('notes')
        supplier.is_active     = request.form.get('is_active') == 'on'
        db.session.commit()
        flash("Supplier updated.", "success")
        return redirect(url_for('inventory.suppliers'))

    return render_template('inventory/edit_supplier.html', supplier=supplier)


# =========================
# PURCHASE ORDERS
# =========================
@inventory_bp.route('/purchase-orders')
@login_required
@admin_required
def purchase_orders():
    pos = PurchaseOrder.query.order_by(
        PurchaseOrder.created_at.desc()
    ).all()
    return render_template('inventory/purchase_orders.html', pos=pos)



# ===================
# ADD PURCHASE ORDER
# ======================

@inventory_bp.route('/purchase-orders/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_purchase_order():
    suppliers = Supplier.query.filter_by(is_active=True).all()
    products  = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    if request.method == 'POST':
        supplier_id   = request.form.get('supplier_id')
        expected_date = request.form.get('expected_date')
        notes         = request.form.get('notes', '')

        po = PurchaseOrder(
            supplier_id=int(supplier_id),
            created_by=current_user.id,
            po_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
            status=POStatus.draft,
            expected_date=datetime.strptime(expected_date, '%Y-%m-%d') if expected_date else None,
            notes=notes,
        )
        db.session.add(po)
        db.session.flush()

        # add items
        product_ids = request.form.getlist('product_id[]')
        variant_ids = request.form.getlist('variant_id[]')
        quantities  = request.form.getlist('quantity[]')
        unit_costs  = request.form.getlist('unit_cost[]')

        total_cost = 0
        for i in range(len(product_ids)):
            if not product_ids[i] or not quantities[i]:
                continue

            qty       = int(quantities[i])
            cost      = float(unit_costs[i]) if unit_costs[i] else 0
            line_total = qty * cost
            total_cost += line_total

            product = Product.query.get(int(product_ids[i]))
            variant = ProductVariant.query.get(int(variant_ids[i])) if variant_ids[i] else None

            po_item = PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=int(product_ids[i]),
                variant_id=int(variant_ids[i]) if variant_ids[i] else None,
                product_name=product.name if product else '',
                variant_name=variant.name if variant else '',
                quantity_ordered=qty,
                quantity_received=0,
                unit_cost=cost,
                total_cost=line_total,
            )
            db.session.add(po_item)

        po.total_cost = total_cost
        db.session.commit()

        flash(f"Purchase order {po.po_number} created.", "success")
        return redirect(url_for('inventory.purchase_order_detail', id=po.id))

    return render_template(
        'inventory/add_purchase_order.html',
        suppliers=suppliers,
        products=products,
    )

# =========================
# purchase order detail
# ===========================
@inventory_bp.route('/purchase-orders/<int:id>')
@login_required
@admin_required
def purchase_order_detail(id):
    po = PurchaseOrder.query.get_or_404(id)
    return render_template('inventory/purchase_order_detail.html', po=po)



# ====================================
#  RECEIVEE ORDER
# =================================
@inventory_bp.route('/purchase-orders/<int:id>/receive', methods=['POST'])
@login_required
@admin_required
def receive_purchase_order(id):
    po = PurchaseOrder.query.get_or_404(id)

    all_received   = True
    any_received   = False
    received_items = []

    for item in po.items:
        received_qty = int(request.form.get(f'received_{item.id}', 0))
        # cap at outstanding quantity to prevent over-receiving
        max_receivable = item.quantity_ordered - item.quantity_received
        received_qty = max(0, min(received_qty, max_receivable))
        if received_qty > 0:
            item.quantity_received += received_qty
            any_received = True

            if item.variant_id:
                obj = ProductVariant.query.get(item.variant_id)
            else:
                obj = Product.query.get(item.product_id)

            if obj:
                stock_before       = obj.stock_quantity
                obj.stock_quantity += received_qty

                # update cost price from PO unit cost
                if item.unit_cost and item.unit_cost > 0:
                    obj.cost_price = item.unit_cost

                movement = StockMovement(
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    created_by=current_user.id,
                    movement_type=MovementType.purchase,
                    quantity=received_qty,
                    stock_before=stock_before,
                    stock_after=obj.stock_quantity,
                    reference=po.po_number,
                    note=f"Received from PO {po.po_number}"
                )
                db.session.add(movement)
                received_items.append({
                    'name':        item.product_name,
                    'variant':     item.variant_name or '',
                    'qty':         received_qty,
                    'stock_after': obj.stock_quantity,
                })

                # clear low stock alerts if stock now above threshold
                threshold = getattr(obj, 'low_stock_threshold', 10) or 10
                if obj.stock_quantity > threshold:
                    StockAlert.query.filter_by(
                        product_id=item.product_id,
                        variant_id=item.variant_id,
                        is_active=True
                    ).update({'is_active': False})

        if item.quantity_received < item.quantity_ordered:
            all_received = False

    if any_received:
        po.status = POStatus.received if all_received else POStatus.partial
        if all_received:
            po.received_date = datetime.utcnow()

    db.session.commit()

    # notify admin by email
    if any_received:
        try:
            from app.utils.email import send_email
            admin_email = current_app.config.get('ADMIN_EMAIL')
            if admin_email:
                items_html = ''.join([
                    f'<tr><td>{i["name"]} {i["variant"]}</td>'
                    f'<td style="text-align:center;">{i["qty"]}</td>'
                    f'<td style="text-align:center;">{i["stock_after"]}</td></tr>'
                    for i in received_items
                ])
                status_label = 'Fully Received' if all_received else 'Partially Received'
                html = f"""
                <h2 style="color:#16a34a;">PO {po.po_number} — {status_label}</h2>
                <p>Stock has been received from <strong>{po.supplier.name}</strong>
                   by {current_user.first_name} {current_user.last_name}.</p>
                <table border="1" cellpadding="8" cellspacing="0"
                       style="border-collapse:collapse;width:100%;font-size:14px;">
                    <thead>
                        <tr style="background:#f1f5f9;">
                            <th style="text-align:left;">Product</th>
                            <th>Qty Received</th>
                            <th>New Stock Level</th>
                        </tr>
                    </thead>
                    <tbody>{items_html}</tbody>
                </table>
                <p style="margin-top:16px;color:#64748b;font-size:13px;">
                    Received on {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC
                </p>
                """
                send_email(
                    to=admin_email,
                    subject=f"Stock Received — PO {po.po_number} ({status_label})",
                    html_content=html
                )
        except Exception as e:
            print(f"PO receive email failed: {e}")

    flash("Stock received and updated.", "success")
    return redirect(url_for('inventory.purchase_order_detail', id=id))


# ============================
# SEND PURCHASE ORDER
# ================================

@inventory_bp.route('/purchase-orders/<int:id>/send', methods=['POST'])
@login_required
@admin_required
def send_purchase_order(id):
    po        = PurchaseOrder.query.get_or_404(id)
    po.status = POStatus.sent
    db.session.commit()

    send_type = request.form.get('send_type', 'email')

    def do_email():
        if po.supplier.email:
            try:
                from app.utils.email import send_purchase_order_email
                send_purchase_order_email(po)
                return True
            except Exception as e:
                print(f"Email failed: {e}")
        return False

    def do_whatsapp():
        if po.supplier.phone:
            try:
                from app.utils.email import send_purchase_order_whatsapp
                send_purchase_order_whatsapp(po)
                return True
            except Exception as e:
                print(f"WhatsApp failed: {e}")
        return False

    def do_sms():
        if po.supplier.phone:
            try:
                from app.utils.sms import send_order_sms
                # build a simple PO summary message
                items_text = ', '.join([
                    f"{item.product_name} x{item.quantity_ordered}"
                    for item in po.items
                ])
                message = (
                    f"Purchase Order {po.po_number} from Judith Ethnic Store. "
                    f"Items: {items_text}. "
                    f"Total: £{po.total_cost:.2f}. "
                    f"Please confirm receipt."
                )
                from app.models import Order
                # create a mock object with address.phone for send_order_sms
                class MockOrder:
                    def __init__(self, phone, number):
                        self.order_number = number
                        class Addr:
                            pass
                        self.address = Addr()
                        self.address.phone = phone
                mock = MockOrder(po.supplier.phone, po.po_number)
                send_order_sms(mock, message)
                return True
            except Exception as e:
                print(f"SMS failed: {e}")
        return False

    if send_type == 'email':
        if do_email():
            flash(f"PO {po.po_number} emailed to {po.supplier.email}.", "success")
        else:
            flash(f"PO {po.po_number} marked as sent but email failed or supplier has no email.", "warning")

    elif send_type == 'whatsapp':
        if do_whatsapp():
            flash(f"PO {po.po_number} sent via WhatsApp to {po.supplier.phone}.", "success")
        else:
            flash(f"PO {po.po_number} marked as sent but WhatsApp failed or supplier has no phone.", "warning")

    elif send_type == 'sms':
        if do_sms():
            flash(f"PO {po.po_number} sent via SMS to {po.supplier.phone}.", "success")
        else:
            flash(f"PO {po.po_number} marked as sent but SMS failed or supplier has no phone.", "warning")

    elif send_type == 'all':
        results = []
        if do_email():   results.append('Email')
        if do_whatsapp(): results.append('WhatsApp')
        if do_sms():     results.append('SMS')
        if results:
            flash(f"PO {po.po_number} sent via {', '.join(results)}.", "success")
        else:
            flash(f"PO {po.po_number} marked as sent but all notifications failed.", "warning")

    return redirect(url_for('inventory.purchase_order_detail', id=id))


# =========================
# REPORTS
# =========================
@inventory_bp.route('/reports')
@login_required
@admin_required
def reports():
    from sqlalchemy import func

    # stock valuation
    product_value = db.session.query(
        func.coalesce(func.sum(
            Product.cost_price * Product.stock_quantity
        ), 0)
    ).filter(Product.has_variants == False).scalar()

    variant_value = db.session.query(
        func.coalesce(func.sum(
            ProductVariant.cost_price * ProductVariant.stock_quantity
        ), 0)
    ).scalar()

    total_value = float(product_value or 0) + float(variant_value or 0)

    # low stock
    low_stock_variants = ProductVariant.query.filter(
        ProductVariant.stock_quantity <= ProductVariant.low_stock_threshold,
        ProductVariant.is_active == True
    ).all()

    low_stock_products = Product.query.filter(
        Product.has_variants == False,
        Product.stock_quantity <= Product.low_stock_threshold,
        Product.is_active == True
    ).all()

    # top selling from POS
    from app.models import POSOrderItem
    top_pos = db.session.query(
        POSOrderItem.product_name,
        func.sum(POSOrderItem.quantity).label('total_qty'),
        func.sum(POSOrderItem.total_price).label('total_revenue')
    ).group_by(POSOrderItem.product_name)\
     .order_by(func.sum(POSOrderItem.quantity).desc())\
     .limit(10).all()

    # movement summary
    movement_summary = db.session.query(
        StockMovement.movement_type,
        func.count(StockMovement.id).label('count'),
        func.sum(StockMovement.quantity).label('total_qty')
    ).group_by(StockMovement.movement_type).all()

    return render_template(
        'inventory/reports.html',
        total_value=total_value,
        low_stock_variants=low_stock_variants,
        low_stock_products=low_stock_products,
        top_pos=top_pos,
        movement_summary=movement_summary,
    )


# =========================
# API — product variants for PO form
# =========================
@inventory_bp.route('/api/product-variants/<int:product_id>')
@login_required
@admin_required
def get_variants(product_id):
    product  = Product.query.get_or_404(product_id)
    variants = [{'id': v.id, 'name': v.name, 'sku': v.sku} for v in product.variants]
    return jsonify({'has_variants': product.has_variants, 'variants': variants})


#=======================================
# GENERATE FOR EXISTING VARIANTS
#===========================================
@inventory_bp.route('/products/generate-variants-all')
@login_required
@admin_required
def generate_variants_all():
    from app.utils.qr import generate_variant_qr, generate_variant_barcode
    from app.models import ProductVariant
    variants = ProductVariant.query.all()
    count    = 0

    for variant in variants:
        try:
            product               = variant.product
            variant.qr_code       = generate_variant_qr(product, variant)
            variant.barcode_image = generate_variant_barcode(variant)
            count += 1
        except Exception as e:
            print(f"Failed for variant {variant.id}: {e}")

    db.session.commit()
    flash(f"Generated QR codes and barcodes for {count} variants.", "success")
    return redirect(url_for('admin.dashboard'))


# ==============================
# DELETE PRODUCT
# ========================================

@inventory_bp.route('/products/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)

    # delete QR and barcode files
    for filename in [product.qr_code, product.barcode_image]:
        if filename:
            filepath = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes', filename)
            if os.path.exists(filepath):
                os.remove(filepath)

    # delete image file
    if product.image:
        img_path = os.path.join(current_app.root_path, 'static', 'uploads', product.image)
        if os.path.exists(img_path):
            os.remove(img_path)

    db.session.delete(product)
    db.session.commit()

    flash(f"Product '{product.name}' deleted.", "success")
    return redirect(url_for('inventory.products'))



# =========================================
# DELETE VARIANT
# ===========================================

@inventory_bp.route('/variants/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_variant(id):
    variant = ProductVariant.query.get_or_404(id)
    product_id = variant.product_id

    # delete files
    for filename in [variant.qr_code, variant.barcode_image]:
        if filename:
            filepath = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes', filename)
            if os.path.exists(filepath):
                os.remove(filepath)

    db.session.delete(variant)

    # if no more variants, set has_variants to False
    product = Product.query.get(product_id)
    if product and not product.variants:
        product.has_variants = False

    db.session.commit()
    flash(f"Variant deleted.", "success")
    return redirect(url_for('inventory.product_detail', id=product_id))


# ===================================
# EDIT VARIANT
# ===========================

@inventory_bp.route('/variants/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_variant(id):
    variant = ProductVariant.query.get_or_404(id)
    product = Product.query.get_or_404(variant.product_id)

    if request.method == 'POST':
        variant.name                = request.form.get('name')
        variant.price               = request.form.get('price')
        variant.cost_price          = request.form.get('cost_price') or None
        variant.low_stock_threshold = int(request.form.get('low_stock_threshold') or 10)
        variant.is_active           = request.form.get('is_active') == 'on'

        # update SKU if name changed
        variant.sku = f"{product.sku}-{variant.name.upper().replace(' ', '')}"

        db.session.commit()
        flash(f"Variant '{variant.name}' updated.", "success")
        return redirect(url_for('inventory.product_detail', id=variant.product_id))

    return render_template('inventory/edit_variant.html', variant=variant, product=product)

