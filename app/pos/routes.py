import uuid
from datetime import datetime
from flask import render_template, redirect, url_for, request, flash, session, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps

from app.extensions import db

from app import csrf


from app.models import Product, POSSession, POSOrder, POSOrderItem, StockMovement, MovementType, User

from . import pos_bp

# =========================
# POS ACCESS DECORATOR
# =========================
def pos_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.pos_role and not current_user.is_admin:
            flash("You don't have POS access.", "danger")
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated


def manager_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.pos_role != 'manager' and not current_user.is_admin:
            flash("Manager access required.", "danger")
            return redirect(url_for('pos.till'))
        return f(*args, **kwargs)
    return decorated


# =========================
# POS HOME — open session
# =========================
@pos_bp.route('/')
@login_required
@pos_required
def index():
    active_session = POSSession.query.filter_by(
        staff_id=current_user.id, is_active=True
    ).first()

    if active_session:
        return redirect(url_for('pos.till'))

    return render_template('pos/open_session.html')


@pos_bp.route('/session/open', methods=['POST'])
@login_required
@pos_required
def open_session():
    opening_float = request.form.get('opening_float', 0)

    pos_session = POSSession(
        staff_id=current_user.id,
        opening_float=opening_float,
        is_active=True
    )
    db.session.add(pos_session)
    db.session.commit()

    session['pos_session_id'] = pos_session.id
    return redirect(url_for('pos.till'))


@pos_bp.route('/session/close', methods=['POST'])
@login_required
@pos_required
def close_session():
    closing_float = request.form.get('closing_float', 0)
    pos_session   = POSSession.query.filter_by(
        staff_id=current_user.id, is_active=True
    ).first()

    if pos_session:
        pos_session.is_active    = False
        pos_session.closed_at    = datetime.utcnow()
        pos_session.closing_float = closing_float
        db.session.commit()
        session.pop('pos_session_id', None)

    # flash("Session closed successfully.", "success")
    return redirect(url_for('pos.index'))


# =========================
# TILL
# =========================
@pos_bp.route('/till')
@login_required
@pos_required
def till():
    pos_session = POSSession.query.filter_by(
        staff_id=current_user.id, is_active=True
    ).first()

    if not pos_session:
        return redirect(url_for('pos.index'))

    return render_template('pos/till.html', pos_session=pos_session)


## =========================
# PRODUCT LOOKUP (barcode/SKU/search)
# =========================
@pos_bp.route('/api/product-lookup')
@login_required
@pos_required
def product_lookup():
    from app.models import Category
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify([])

    # search by SKU (exact-ish match)
    sku_products = Product.query.filter(
        Product.sku.ilike(f'%{query}%'),
        Product.is_active == True
    ).limit(40).all()

    # search by product name
    name_products = Product.query.filter(
        Product.name.ilike(f'%{query}%'),
        Product.is_active == True
    ).all()

    # search by category name — return all products in matching categories
    matching_categories = Category.query.filter(
        Category.name.ilike(f'%{query}%')
    ).all()
    category_ids = [c.id for c in matching_categories]
    category_products = Product.query.filter(
        Product.category_id.in_(category_ids),
        Product.is_active == True
    ).all() if category_ids else []

    # merge and deduplicate by id
    seen = set()
    results = []
    for p in sku_products + name_products + category_products:
        if p.id not in seen:
            seen.add(p.id)
            results.append(p)

    return jsonify([{
        'id':    p.id,
        'name':  p.name,
        'sku':   p.sku or '',
        'price': float(p.price),
        'stock': p.stock_quantity,
        'image': p.image or '',
    } for p in results])


# =========================
# RECEIPT
# =========================
@pos_bp.route('/receipt/<int:order_id>')
@login_required
@pos_required
def receipt(order_id):
    order = POSOrder.query.get_or_404(order_id)
    return render_template('pos/receipt.html', order=order)


# =========================
# REPORTS (manager only)
# =========================
@pos_bp.route('/reports')
@login_required
@manager_required
def reports():
    from sqlalchemy import func

    today = datetime.utcnow().date()

    daily_total = db.session.query(
        func.coalesce(func.sum(POSOrder.total_amount), 0)
    ).filter(
        db.func.date(POSOrder.created_at) == today
    ).scalar()

    daily_orders = POSOrder.query.filter(
        db.func.date(POSOrder.created_at) == today
    ).count()

    recent_orders = POSOrder.query.order_by(
        POSOrder.created_at.desc()
    ).limit(20).all()

    return render_template(
        'pos/reports.html',
        daily_total=daily_total,
        daily_orders=daily_orders,
        recent_orders=recent_orders
    )


# =========================
# STAFF MANAGEMENT (manager and admin only)
# =========================
@pos_bp.route('/staff')
@login_required
@manager_required
def staff_list():
    staff = User.query.filter(
        db.or_(
            User.pos_role != None,
            User.is_admin == True
        )
    ).all()
    return render_template('pos/staff.html', staff=staff)


@pos_bp.route('/staff/update/<int:user_id>', methods=['POST'])
@login_required
@manager_required
def update_staff(user_id):
    user     = User.query.get_or_404(user_id)
    pos_role = request.form.get('pos_role')
    is_admin = request.form.get('is_admin', '0') == '1'

    # prevent removing own admin access
    if user.id == current_user.id and not is_admin:
        flash("You cannot remove your own admin access.", "warning")
        return redirect(url_for('pos.staff_list'))

    user.pos_role = pos_role if pos_role else None
    user.is_admin = is_admin
    db.session.commit()
    flash(f"Updated {user.first_name}'s access.", "success")
    return redirect(url_for('pos.staff_list'))


@pos_bp.route('/staff/delete/<int:user_id>', methods=['POST'])
@login_required
@manager_required
def delete_staff(user_id):
    user = User.query.get_or_404(user_id)

    # prevent deleting yourself
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('pos.staff_list'))

    user.pos_role = None
    user.is_admin = False
    db.session.commit()
    flash(f"{user.first_name} {user.last_name}'s access has been revoked.", "success")
    return redirect(url_for('pos.staff_list'))



# ==============================
# PROCESS SALE (with Dojo card)
# ==============================

@pos_bp.route('/sale/process', methods=['POST'])
@csrf.exempt
@login_required
@pos_required
def process_sale():
    pos_session = POSSession.query.filter_by(
        staff_id=current_user.id, is_active=True
    ).first()

    if not pos_session:
        return jsonify({'success': False, 'error': 'No active session'}), 400

    data            = request.get_json()
    items           = data.get('items', [])
    payment_method  = data.get('payment_method', 'cash')
    amount_tendered = float(data.get('amount_tendered', 0))
    discount        = float(data.get('discount', 0))
    customer_name   = data.get('customer_name', '')
    customer_email  = data.get('customer_email', '')
    customer_phone  = data.get('customer_phone', '')
    payment_intent_id = data.get('payment_intent_id', None)

    if not items:
        return jsonify({'success': False, 'error': 'No items in basket'}), 400

    try:
        subtotal = sum(float(item['price']) * int(item['quantity']) for item in items)
        total    = max(0, subtotal - discount)

        # cash validation
        if payment_method == 'cash':
            if amount_tendered < total:
                return jsonify({
                    'success': False,
                    'error':   f'Amount tendered (£{amount_tendered:.2f}) is less than total (£{total:.2f})'
                }), 200

        # card — set amount tendered to total
        if payment_method == 'card':
            amount_tendered = total

        change = max(0, amount_tendered - total) if payment_method == 'cash' else 0

        order = POSOrder(
            session_id        = pos_session.id,
            staff_id          = current_user.id,
            order_number      = f"POS-{uuid.uuid4().hex[:8].upper()}",
            subtotal          = subtotal,
            discount          = discount,
            total_amount      = total,
            payment_method    = payment_method,
            amount_tendered   = amount_tendered,
            change_given      = change,
            customer_name     = customer_name,
            customer_email    = customer_email,
            customer_phone    = customer_phone,
            status            = 'completed'
        )
        db.session.add(order)
        db.session.flush()

        for item in items:
            product = Product.query.get(item['product_id'])
            if not product:
                continue

            order_item = POSOrderItem(
                order_id      = order.id,
                product_id    = product.id,
                quantity      = int(item['quantity']),
                unit_price    = float(item['price']),
                total_price   = float(item['price']) * int(item['quantity']),
                product_name  = product.name,
                product_image = product.image or '',
                product_sku   = product.sku or '',
            )
            db.session.add(order_item)

            # deduct stock + record movement
            if product.stock_quantity is not None:
                stock_before           = product.stock_quantity
                product.stock_quantity = max(0, stock_before - int(item['quantity']))

                movement = StockMovement(
                    product_id    = product.id,
                    created_by    = current_user.id,
                    movement_type = MovementType.pos_sale,
                    quantity      = -int(item['quantity']),
                    stock_before  = stock_before,
                    stock_after   = product.stock_quantity,
                    reference     = order.order_number,
                    note          = f"POS sale"
                )
                db.session.add(movement)

        db.session.commit()

        return jsonify({
            'success':        True,
            'order_number':   order.order_number,
            'total':          float(total),
            'change':         float(change),
            'order_id':       order.id,
            'payment_method': payment_method,
        })

    except Exception as e:
        db.session.rollback()
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500



@pos_bp.route('/api/order-lookup')
@csrf.exempt
@login_required
@pos_required
def order_lookup_for_return():
    from app.models import POSOrder, Order
    order_number = request.args.get('order_number', '').strip().upper()

    # check POS orders first
    pos_order = POSOrder.query.filter_by(order_number=order_number).first()
    if pos_order:
        return jsonify({
            'found':        True,
            'order_number': pos_order.order_number,
            'total':        float(pos_order.total_amount),
            'payment_method': pos_order.payment_method,
            'items': [{
                'name':        item.product_name,
                'quantity':    item.quantity,
                'total_price': float(item.total_price),
            } for item in pos_order.items]
        })

    # check online orders
    online_order = Order.query.filter_by(order_number=order_number).first()
    if online_order:
        return jsonify({
            'found':        True,
            'order_number': online_order.order_number,
            'total':        float(online_order.total_amount),
            'payment_method': 'online',
            'items': [{
                'name':        item.product_name,
                'quantity':    item.quantity,
                'total_price': float(item.price * item.quantity),
            } for item in online_order.items]
        })

    return jsonify({'found': False})


@pos_bp.route('/api/process-return', methods=['POST'])
@csrf.exempt
@login_required
@pos_required
def process_return():
    from app.models import StockMovement, MovementType, POSOrder, Order
    data          = request.get_json()
    order_number  = data.get('order_number', '').strip().upper()
    reason        = data.get('reason', '')
    refund_method = data.get('refund_method', 'cash')
    refund_amount = float(data.get('refund_amount', 0))

    try:
        # find order
        pos_order    = POSOrder.query.filter_by(order_number=order_number).first()
        online_order = None if pos_order else Order.query.filter_by(order_number=order_number).first()

        order = pos_order or online_order
        if not order:
            return jsonify({'success': False, 'error': 'Order not found'})

        # restock items
        items = pos_order.items if pos_order else online_order.items
        for item in items:
            product = Product.query.get(item.product_id)
            if product and product.stock_quantity is not None:
                stock_before           = product.stock_quantity
                product.stock_quantity += item.quantity

                movement = StockMovement(
                    product_id    = product.id,
                    created_by    = current_user.id,
                    movement_type = MovementType.return_in,
                    quantity      = item.quantity,
                    stock_before  = stock_before,
                    stock_after   = product.stock_quantity,
                    reference     = order_number,
                    note          = f"Return — {reason} — {refund_method} refund £{refund_amount:.2f}"
                )
                db.session.add(movement)

        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})




@pos_bp.route('/sale/card/initiate', methods=['POST'])
@csrf.exempt
@login_required
@pos_required
def initiate_card_payment():
    """Send payment to Dojo terminal."""
    from app.services.dojo import create_terminal_payment

    data      = request.get_json()
    amount    = float(data.get('amount', 0))
    reference = data.get('reference', f"POS-{uuid.uuid4().hex[:8].upper()}")

    if amount <= 0:
        return jsonify({'success': False, 'error': 'Invalid amount'})

    try:
        result = create_terminal_payment(
            amount_pence=int(amount * 100),
            currency="GBP",
            reference=reference,
        )
        return jsonify({'success': True, 'intent_id': result['intent_id']})
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})


@pos_bp.route('/sale/card/status', methods=['GET'])
@login_required
@pos_required
def card_payment_status():
    """Poll terminal payment status."""
    from app.services.dojo import get_payment_intent_status
    intent_id = request.args.get('intent_id', '')
    if not intent_id:
        return jsonify({'status': 'Unknown'})
    try:
        status = get_payment_intent_status(intent_id)
        return jsonify({'status': status})
    except Exception as e:
        return jsonify({'status': 'Error', 'error': str(e)})




@pos_bp.route('/sale/card/cancel', methods=['POST'])
@csrf.exempt
@login_required
@pos_required
def cancel_card_payment():
    from app.services.dojo import cancel_terminal_session
    data      = request.get_json()
    intent_id = data.get('intent_id', '')
    terminal_id = current_app.config.get('DOJO_TERMINAL_ID', '')

    try:
        # get session id from intent
        api_key = current_app.config.get('DOJO_API_KEY')
        resp = __import__('requests').get(
            f"{current_app.config['DOJO_API_BASE']}/payment-intents/{intent_id}",
            headers={
                'version': '2024-02-05',
                'Authorization': f'Basic {api_key}'
            },
            timeout=10
        )
        data = resp.json()
        history = data.get('terminalSessionHistory', [])
        if history:
            session_id = history[-1].get('terminalSessionId', '')
            cancel_terminal_session(terminal_id, session_id)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# =====================================
# PRINT DATA
# =======================================

@pos_bp.route('/receipt-data/<int:order_id>')
@login_required
def receipt_data(order_id):
    order = POSOrder.query.get_or_404(order_id)
    return jsonify({
        'order_number':   order.order_number,
        'date':           order.created_at.strftime('%d/%m/%Y %H:%M'),
        'cashier':        f"{current_user.first_name} {current_user.last_name}",
        'payment_method': order.payment_method,
        'subtotal':       float(order.subtotal),
        'discount':       float(order.discount or 0),
        'total':          float(order.total_amount),
        'change':         float(order.change_given or 0),
        'items': [{
            'name':        item.product_name,
            'quantity':    item.quantity,
            'unit_price':  float(item.unit_price),
            'total_price': float(item.total_price),
        } for item in order.items]
    })