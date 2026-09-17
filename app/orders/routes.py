import uuid
from datetime import datetime
from functools import wraps
from flask import render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (
    Order, OrderItem, OrderStatus, PaymentStatus,
    OrderStatusLog, PickingList, PickingListItem,
    Shipment, StockReservation, StockMovement, MovementType,
    Product, ProductVariant, User, BinLocation
)
from app.utils.decorators import admin_required
from app import csrf
from . import orders_bp

from app.utils.sms import send_order_sms

# ================================
# DECORATOR
# ======================================
def manager_or_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_admin and not current_user.pos_role:
            flash("Access required.", "danger")
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated


# =========================
# HELPERS
# =========================
def log_status_change(order, to_status, note=None):
    log = OrderStatusLog(
        order_id    = order.id,
        from_status = order.status.value if order.status else None,
        to_status   = to_status,
        changed_by  = current_user.id,
        note        = note,
    )
    db.session.add(log)




def send_order_email_notification(order, subject, body_html):
    """Send email via Brevo."""
    try:
        from app.utils.email import send_email
        email = order.user.email if order.user else order.guest_email
        if email:
            send_email(
                to_email=email,
                to_name=order.address.full_name if order.address else "Customer",
                subject=subject,
                html_content=body_html,
            )
    except Exception as e:
        current_app.logger.error(f"Email notification failed: {e}")


def reserve_stock(order):
    """Reserve stock for all items in an order. Returns True if successful, False if out of stock."""
    out_of_stock_items = []

    # check stock availability first before reserving anything
    for item in order.items:
        if item.variant_id:
            variant = ProductVariant.query.get(item.variant_id)
            if not variant or variant.stock_quantity < item.quantity:
                available = variant.stock_quantity if variant else 0
                out_of_stock_items.append(
                    f"{item.product_name} (need {item.quantity}, have {available})"
                )
        else:
            product = Product.query.get(item.product_id)
            if not product or product.stock_quantity < item.quantity:
                available = product.stock_quantity if product else 0
                out_of_stock_items.append(
                    f"{item.product_name} (need {item.quantity}, have {available})"
                )

    # if any item is out of stock, move order to out_of_stock status
    if out_of_stock_items:
        log_status_change(
            order,
            "out_of_stock",
            f"Insufficient stock: {', '.join(out_of_stock_items)}"
        )
        order.status = OrderStatus.out_of_stock
        db.session.commit()
        return False

    # all stock available — proceed with reservation
    for item in order.items:
        reservation = StockReservation(
            order_id   = order.id,
            product_id = item.product_id,
            variant_id = item.variant_id,
            quantity   = item.quantity,
            is_active  = True,
        )
        db.session.add(reservation)

        if item.variant_id:
            variant = ProductVariant.query.get(item.variant_id)
            if variant:
                variant.stock_quantity = max(0, variant.stock_quantity - item.quantity)
        else:
            product = Product.query.get(item.product_id)
            if product:
                product.stock_quantity = max(0, product.stock_quantity - item.quantity)

    return True


def release_stock(order):
    """Release reserved stock back to inventory (on cancel/hold)."""
    for reservation in order.reservations:
        if not reservation.is_active:
            continue

        if reservation.variant_id:
            variant = ProductVariant.query.get(reservation.variant_id)
            if variant:
                stock_before           = variant.stock_quantity
                variant.stock_quantity += reservation.quantity
                movement = StockMovement(
                    product_id    = reservation.product_id,
                    variant_id    = reservation.variant_id,
                    created_by    = current_user.id,
                    movement_type = MovementType.return_in,
                    quantity      = reservation.quantity,
                    stock_before  = stock_before,
                    stock_after   = variant.stock_quantity,
                    reference     = order.order_number,
                    note          = "Stock released — order cancelled"
                )
                db.session.add(movement)
        else:
            product = Product.query.get(reservation.product_id)
            if product:
                stock_before            = product.stock_quantity
                product.stock_quantity += reservation.quantity
                movement = StockMovement(
                    product_id    = reservation.product_id,
                    created_by    = current_user.id,
                    movement_type = MovementType.return_in,
                    quantity      = reservation.quantity,
                    stock_before  = stock_before,
                    stock_after   = product.stock_quantity,
                    reference     = order.order_number,
                    note          = "Stock released — order cancelled"
                )
                db.session.add(movement)

        reservation.is_active = False


# =========================
# ORDER LIST
# =========================
@orders_bp.route('/')
@login_required
@manager_or_admin_required
def order_list():
    from sqlalchemy import text
    status_filter = request.args.get('status', '')
    page          = request.args.get('page', 1, type=int)

    if status_filter:
        # use raw SQL filter to bypass enum comparison issues
        order_ids = db.session.execute(
            text("SELECT id FROM orders WHERE status = :s ORDER BY created_at DESC"),
            {"s": status_filter}
        ).fetchall()
        ids = [r[0] for r in order_ids]
        query = Order.query.filter(Order.id.in_(ids)).options(
            db.joinedload(Order.address),
            db.joinedload(Order.user)
        ).order_by(Order.created_at.desc())
    else:
        query = Order.query.options(
            db.joinedload(Order.address),
            db.joinedload(Order.user)
        ).order_by(Order.created_at.desc())

    orders = query.paginate(page=page, per_page=25)

    status_counts = {}
    for s in OrderStatus:
        count = db.session.execute(
            text("SELECT COUNT(*) FROM orders WHERE status = :val"),
            {"val": s.value}
        ).scalar()
        status_counts[s.value] = count or 0

    total_orders = db.session.execute(
        text("SELECT COUNT(*) FROM orders")
    ).scalar()

    return render_template(
        'orders/order_list.html',
        orders=orders,
        status_filter=status_filter,
        status_counts=status_counts,
        total_orders=total_orders,
        OrderStatus=OrderStatus,
    )


# =========================
# ORDER DETAIL
# =========================
@orders_bp.route('/<int:id>')
@login_required
@manager_or_admin_required
def order_detail(id):
    order = Order.query.options(
        db.joinedload(Order.address),
        db.joinedload(Order.user),
        db.joinedload(Order.items),
    ).get_or_404(id)

    status_logs  = OrderStatusLog.query.filter_by(order_id=id).order_by(OrderStatusLog.created_at.desc()).all()
    bin_locations = BinLocation.query.filter_by(is_active=True).order_by(BinLocation.name).all()

    return render_template(
        'orders/manage_order_detail.html',
        order=order,
        status_logs=status_logs,
        bin_locations=bin_locations,
        OrderStatus=OrderStatus,
    )


# =========================
# CONFIRM PAYMENT
# =========================
@orders_bp.route('/<int:id>/confirm', methods=['POST'])
@login_required
@manager_or_admin_required
def confirm_payment(id):
    order = Order.query.get_or_404(id)

    if order.status not in [OrderStatus.new, OrderStatus.payment_failed]:
        flash("Order cannot be confirmed from its current status.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    log_status_change(order, "payment_confirmed", "Payment manually confirmed by staff")
    order.status         = OrderStatus.payment_confirmed
    order.payment_status = PaymentStatus.paid

    # reserve stock — may move order to out_of_stock if insufficient
    success = reserve_stock(order)
    db.session.commit()

    if not success:
        flash(
            f"Order {order.order_number} moved to OUT OF STOCK — insufficient inventory.",
            "danger"
        )
        return redirect(url_for('orders.order_detail', id=id))

    # notify customer
    send_order_sms(order,
        f"Hi {order.address.full_name if order.address else 'there'}, "
        f"your order {order.order_number} from Judith Ethnic Food Store "
        f"has been confirmed. We'll update you when it's on its way."
    )


    # email notification
    try:
        from app.utils.email import send_order_confirmation_customer
        send_order_confirmation_customer(order)
    except Exception as e:
        current_app.logger.error(f"Confirmation email failed: {e}")

    flash(f"Order {order.order_number} confirmed. Stock reserved.", "success")
    return redirect(url_for('orders.order_detail', id=id))


# =========================
# PROCESS ORDER
# =========================
@orders_bp.route('/<int:id>/process', methods=['POST'])
@login_required
@manager_or_admin_required
def process_order(id):
    order = Order.query.get_or_404(id)

    if order.status != OrderStatus.payment_confirmed:
        flash("Order must be payment confirmed before processing.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    log_status_change(order, "processing")
    order.status = OrderStatus.processing
    db.session.commit()

    flash(f"Order {order.order_number} is now processing.", "success")
    return redirect(url_for('orders.order_detail', id=id))


# =========================
# START PICKING
# =========================
@orders_bp.route('/<int:id>/pick', methods=['POST'])
@login_required
@manager_or_admin_required
def start_picking(id):
    order = Order.query.get_or_404(id)

    if order.status != OrderStatus.processing:
        flash("Order must be processing before picking.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    if order.picking_list:
        flash("Picking list already generated.", "info")
        return redirect(url_for('orders.picking_interface', id=id))

    picking_list = PickingList(
        order_id     = order.id,
        generated_by = current_user.id,
        status       = "pending",
    )
    db.session.add(picking_list)
    db.session.flush()

    for item in order.items:
        product = Product.query.get(item.product_id)
        variant = ProductVariant.query.get(item.variant_id) if item.variant_id else None

        pl_item = PickingListItem(
            picking_list_id  = picking_list.id,
            order_item_id    = item.id,
            product_id       = item.product_id,
            variant_id       = item.variant_id,
            bin_location_id = product.bin_location_id,
            product_name     = item.product_name or (product.name if product else ''),
            variant_name     = variant.name if variant else '',
            sku              = (variant.sku if variant else (product.sku if product else '')) or '',
            barcode_image    = (variant.barcode_image if variant else (product.barcode_image if product else '')) or '',
            quantity_to_pick = item.quantity,
            quantity_picked  = 0,
            is_picked        = False,
        )
        db.session.add(pl_item)

    log_status_change(order, "picking", "Picking list generated")
    order.status = OrderStatus.picking
    db.session.commit()

    flash(f"Picking list generated for {order.order_number}.", "success")
    return redirect(url_for('orders.picking_interface', id=id))


# =========================
# PICKING INTERFACE (mobile)
# =========================
@orders_bp.route('/<int:id>/picking')
@login_required
def picking_interface(id):
    order        = Order.query.get_or_404(id)
    picking_list = order.picking_list

    if not picking_list:
        flash("No picking list found.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    return render_template(
        'orders/picking.html',
        order=order,
        picking_list=picking_list,
    )


# =========================
# SCAN ITEM (barcode confirm)
# =========================
@orders_bp.route('/picking-item/<int:item_id>/scan', methods=['POST'])
@csrf.exempt
@login_required
def scan_item(item_id):
    pl_item     = PickingListItem.query.get_or_404(item_id)
    scanned_sku = request.get_json().get('sku', '').strip()

    # if no SKU stored on picking item, mark as picked directly
    if not pl_item.sku:
        pl_item.is_picked       = True
        pl_item.quantity_picked = pl_item.quantity_to_pick
        pl_item.picked_at       = datetime.utcnow()
        pl_item.picked_by       = current_user.id

        picking_list = pl_item.picking_list
        all_picked   = all(i.is_picked for i in picking_list.items)

        if all_picked:
            picking_list.status       = "completed"
            picking_list.completed_at = datetime.utcnow()
            order = picking_list.order
            log_status_change(order, "picked", "All items confirmed")
            order.status = OrderStatus.picked

        db.session.commit()
        return jsonify({'success': True, 'all_picked': all_picked, 'item_name': pl_item.product_name})

    if scanned_sku != pl_item.sku:
        return jsonify({'success': False, 'error': f'Wrong item scanned. Expected {pl_item.sku}'})

    pl_item.is_picked       = True
    pl_item.quantity_picked = pl_item.quantity_to_pick
    pl_item.picked_at       = datetime.utcnow()
    pl_item.picked_by       = current_user.id

    picking_list = pl_item.picking_list
    all_picked   = all(i.is_picked for i in picking_list.items)

    if all_picked:
        picking_list.status       = "completed"
        picking_list.completed_at = datetime.utcnow()
        order = picking_list.order
        log_status_change(order, "picked", "All items scanned and confirmed")
        order.status = OrderStatus.picked

    db.session.commit()
    return jsonify({'success': True, 'all_picked': all_picked, 'item_name': pl_item.product_name})


# =========================
# MARK PACKED
# =========================
@orders_bp.route('/<int:id>/pack', methods=['POST'])
@login_required
@manager_or_admin_required
def pack_order(id):
    order = Order.query.get_or_404(id)

    if order.status != OrderStatus.picked:
        flash("Order must be picked before packing.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    # deduct stock now (picking confirmed all items)
    for item in order.items:
        movement = StockMovement(
            product_id    = item.product_id,
            variant_id    = item.variant_id,
            created_by    = current_user.id,
            movement_type = MovementType.sale,
            quantity      = -item.quantity,
            stock_before  = 0,  # already reserved
            stock_after   = 0,
            reference     = order.order_number,
            note          = f"Packed"
        )
        db.session.add(movement)

    log_status_change(order, "packed")
    order.status = OrderStatus.packed
    db.session.commit()

    flash(f"Order {order.order_number} packed.", "success")
    return redirect(url_for('orders.order_detail', id=id))


# =========================
# READY FOR DISPATCH
# =========================
@orders_bp.route('/<int:id>/ready', methods=['POST'])
@login_required
@manager_or_admin_required
def ready_for_dispatch(id):
    order = Order.query.get_or_404(id)

    if order.status != OrderStatus.packed:
        flash("Order must be packed first.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    log_status_change(order, "ready_for_dispatch")
    order.status = OrderStatus.ready_for_dispatch
    db.session.commit()

    customer_name  = order.address.full_name if order.address else 'there'
    customer_email = order.user.email if order.user else order.guest_email

    if order.fulfillment_type == 'pickup':
        send_order_sms(order,
            f"Hi {customer_name}, "
            f"your order {order.order_number} from Judith Ethnic Food Store "
            f"is ready for collection at 311 High Street, Cheltenham, GL50 3HW "
            f"Please bring your order confirmation."
        )
        if customer_email:
            try:
                from app.utils.email import _send_email, _build_order_html
                _send_email(
                    to_email=customer_email,
                    to_name=customer_name,
                    subject=f"Your Order {order.order_number} is Ready for Collection",
                    html_content=_build_order_html(
                        order,
                        heading="Your Order is Ready for Collection!",
                        intro=(
                            f"Hi {customer_name}, your order is packed and ready. "
                            f"Please collect it from our store at "
                            f"311 High Street, Cheltenham GL50 3HW. "
                            f"Bring your order confirmation when you visit."
                        )
                    )
                )
            except Exception as e:
                current_app.logger.error(f"Collection ready email failed: {e}")

        flash(f"Order {order.order_number} ready. Customer notified.", "success")

    else:
        if customer_email:
            try:
                from app.utils.email import _send_email, _build_order_html
                _send_email(
                    to_email=customer_email,
                    to_name=customer_name,
                    subject=f"Your Order {order.order_number} is Ready for Dispatch",
                    html_content=_build_order_html(
                        order,
                        heading="Your Order is Ready for Dispatch!",
                        intro=(
                            f"Hi {customer_name}, your order is packed and ready "
                            f"to be dispatched. We will notify you once it is on its way."
                        )
                    )
                )
            except Exception as e:
                current_app.logger.error(f"Ready for dispatch email failed: {e}")

        flash(f"Order {order.order_number} ready for dispatch.", "success")

    return redirect(url_for('orders.order_detail', id=id))


# =========================
# DISPATCH
# =========================
@orders_bp.route('/<int:id>/dispatch', methods=['POST'])
@login_required
@manager_or_admin_required
def dispatch_order(id):
    order = Order.query.get_or_404(id)

    if order.status != OrderStatus.ready_for_dispatch:
        flash("Order must be ready for dispatch first.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    driver_name  = request.form.get('driver_name', '')
    driver_phone = request.form.get('driver_phone', '')
    tracking_ref = request.form.get('tracking_ref', '')
    notes        = request.form.get('notes', '')

    shipment = Shipment(
        order_id      = order.id,
        driver_name   = driver_name,
        driver_phone  = driver_phone,
        tracking_ref  = tracking_ref,
        notes         = notes,
        dispatched_at = datetime.utcnow(),
    )
    db.session.add(shipment)

    log_status_change(order, "dispatched", f"Driver: {driver_name}")
    order.status = OrderStatus.dispatched
    db.session.commit()

    customer_name  = order.address.full_name if order.address else 'there'
    customer_email = order.user.email if order.user else order.guest_email

       # SMS only for delivery
    if order.fulfillment_type != 'pickup':
        send_order_sms(order,
            f"Hi {customer_name}, "
            f"your order {order.order_number} from Judith Ethnic Food Store "
            f"is on its way! "
            f"{'Driver: ' + driver_name if driver_name else ''} "
            f"{'Ref: ' + tracking_ref if tracking_ref else ''}".strip()
        )


 # email only for delivery orders — pickup customers already notified at 'ready for collection'
    if order.fulfillment_type != 'pickup' and customer_email:
        try:
            from app.utils.email import _send_email, _build_order_html
            driver_info = f"Driver: {driver_name}" if driver_name else ""
            ref_info    = f"Reference: {tracking_ref}" if tracking_ref else ""
            extra       = " | ".join(filter(None, [driver_info, ref_info]))
            _send_email(
                to_email=customer_email,
                to_name=customer_name,
                subject=f"Your Order {order.order_number} is On Its Way!",
                html_content=_build_order_html(
                    order,
                    heading="Your Order is On Its Way!",
                    intro=(
                        f"Hi {customer_name}, your order has been dispatched and is on its way to you. "
                        f"{'<strong>' + extra + '</strong>. ' if extra else ''}"
                        f"You will receive another notification once it has been delivered."
                    )
                )
            )
        except Exception as e:
            current_app.logger.error(f"Dispatch email failed: {e}")


        flash(f"Order {order.order_number} dispatched.", "success")
        return redirect(url_for('orders.order_detail', id=id))

# =========================
# MARK DELIVERED
# =========================
@orders_bp.route('/<int:id>/deliver', methods=['POST'])
@login_required
@manager_or_admin_required
def deliver_order(id):
    order = Order.query.get_or_404(id)

    if order.status not in [OrderStatus.dispatched, OrderStatus.ready_for_dispatch]:
        flash("Order must be dispatched or ready for collection.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    if order.shipment:
        order.shipment.delivered_at = datetime.utcnow()

    log_status_change(order, "delivered")
    order.status = OrderStatus.delivered
    db.session.commit()

    customer_name  = order.address.full_name if order.address else 'there'
    customer_email = order.user.email if order.user else order.guest_email

      # SMS and email only for delivery orders
    if order.fulfillment_type != 'pickup':
        send_order_sms(order,
            f"Hi {customer_name}, "
            f"your order {order.order_number} from Judith Ethnic Food Store "
            f"has been delivered. Thank you for shopping with us!"
        )

        if customer_email:
            try:
                from app.utils.email import _send_email, _build_order_html
                _send_email(
                    to_email=customer_email,
                    to_name=customer_name,
                    subject=f"Your Order {order.order_number} Has Been Delivered",
                    html_content=_build_order_html(
                        order,
                        heading="Your Order Has Been Delivered!",
                        intro=(
                            f"Hi {customer_name}, your order has been successfully delivered. "
                            f"Thank you for shopping with Judith Ethnic Food Store. "
                            f"We hope you enjoy your products!"
                        )
                    )
                )
            except Exception as e:
                current_app.logger.error(f"Delivered email failed: {e}")

    flash(f"Order {order.order_number} marked as delivered.", "success")
    return redirect(url_for('orders.order_detail', id=id))


# =========================
# COMPLETE
# =========================
@orders_bp.route('/<int:id>/complete', methods=['POST'])
@login_required
@manager_or_admin_required
def complete_order(id):
    order = Order.query.get_or_404(id)

    if order.status != OrderStatus.delivered:
        flash("Order must be delivered before completing.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    log_status_change(order, "completed")
    order.status = OrderStatus.completed
    db.session.commit()

    flash(f"Order {order.order_number} completed.", "success")
    return redirect(url_for('orders.order_detail', id=id))


# =========================
# HOLD
# =========================
@orders_bp.route('/<int:id>/hold', methods=['POST'])
@login_required
@manager_or_admin_required
def hold_order(id):
    order  = Order.query.get_or_404(id)
    reason = request.form.get('reason', '')

    log_status_change(order, "on_hold", reason)
    order.status = OrderStatus.on_hold
    db.session.commit()

    flash(f"Order {order.order_number} placed on hold.", "warning")
    return redirect(url_for('orders.order_detail', id=id))

# =================
# CANCEL  ORDER
# ===================
@orders_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@manager_or_admin_required
def cancel_order(id):
    order  = Order.query.get_or_404(id)
    reason = request.form.get('reason', '')

    # release reserved stock
    release_stock(order)

    log_status_change(order, "cancelled", reason)
    order.status = OrderStatus.cancelled
    db.session.commit()

    customer_name  = order.address.full_name if order.address else 'there'
    customer_email = order.user.email if order.user else order.guest_email

    send_order_sms(order,
        f"Hi {customer_name}, "
        f"your order {order.order_number} from Judith Ethnic Food Store "
        f"has been cancelled. "
        f"{'Reason: ' + reason if reason else ''} "
        f"Please contact us if you have any questions."
    )

    if customer_email:
        try:
            from app.utils.email import _send_email, _build_order_html
            _send_email(
                to_email=customer_email,
                to_name=customer_name,
                subject=f"Your Order {order.order_number} Has Been Cancelled",
                html_content=_build_order_html(
                    order,
                    heading="Your Order Has Been Cancelled",
                    intro=(
                        f"Hi {customer_name}, unfortunately your order has been cancelled. "
                        f"{'Reason: ' + reason + '. ' if reason else ''}"
                        f"If you have any questions please contact us at "
                        f"311 High Street, Cheltenham GL50 3HW or call +44 7306 011093."
                    )
                )
            )
        except Exception as e:
            current_app.logger.error(f"Cancellation email failed: {e}")

    flash(f"Order {order.order_number} cancelled. Stock released.", "success")
    return redirect(url_for('orders.order_detail', id=id))

# =========================
# BIN LOCATIONS
# =========================
@orders_bp.route('/bins')
@login_required
@manager_or_admin_required
def bin_locations():
    bins = BinLocation.query.order_by(BinLocation.name).all()
    return render_template('orders/bins.html', bins=bins)


@orders_bp.route('/bins/add', methods=['POST'])
@login_required
@manager_or_admin_required
def add_bin():
    name        = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()

    if not name:
        flash("Bin name is required.", "danger")
        return redirect(url_for('orders.bin_locations'))

    existing = BinLocation.query.filter_by(name=name).first()
    if existing:
        flash(f"Bin '{name}' already exists.", "warning")
        return redirect(url_for('orders.bin_locations'))

    bin_loc = BinLocation(name=name, description=description)
    db.session.add(bin_loc)
    db.session.commit()

    flash(f"Bin '{name}' added.", "success")
    return redirect(url_for('orders.bin_locations'))


@orders_bp.route('/bins/<int:id>/assign', methods=['POST'])
@login_required
@manager_or_admin_required
def assign_bin(id):
    """Assign a bin location to a picking list item."""
    pl_item_id  = request.form.get('picking_item_id')
    bin_id      = request.form.get('bin_id')
    pl_item     = PickingListItem.query.get_or_404(int(pl_item_id))
    pl_item.bin_location_id = int(bin_id) if bin_id else None
    db.session.commit()
    return jsonify({'success': True})

# ================
# REFUND
# ===============
@orders_bp.route('/<int:id>/refund', methods=['POST'])
@login_required
@manager_or_admin_required
def refund_order(id):
    order  = Order.query.get_or_404(id)
    reason = request.form.get('reason', '')
    amount = float(request.form.get('amount', order.total_amount))

    # release stock
    release_stock(order)

    log_status_change(order, "refunded", f"Refund: £{amount:.2f} — {reason}")
    order.status = OrderStatus.refunded
    db.session.commit()

    customer_name  = order.address.full_name if order.address else 'there'
    customer_email = order.user.email if order.user else order.guest_email

    send_order_sms(order,
        f"Hi {customer_name}, "
        f"your refund of £{amount:.2f} for order {order.order_number} "
        f"has been processed. It will appear in 3-5 working days."
    )

    if customer_email:
        try:
            from app.utils.email import _send_email, _build_order_html
            _send_email(
                to_email=customer_email,
                to_name=customer_name,
                subject=f"Your Refund for Order {order.order_number}",
                html_content=_build_order_html(
                    order,
                    heading="Your Refund Has Been Processed",
                    intro=(
                        f"Hi {customer_name}, your refund of £{amount:.2f} for order "
                        f"{order.order_number} has been processed. "
                        f"{'Reason: ' + reason + '. ' if reason else ''}"
                        f"It will appear in your account within 3-5 working days."
                    )
                )
            )
        except Exception as e:
            current_app.logger.error(f"Refund email failed: {e}")

    flash(f"Order {order.order_number} refunded.", "success")
    return redirect(url_for('orders.order_detail', id=id))




# ================================
# RETURN ORDER
# ================================
@orders_bp.route('/<int:id>/return', methods=['POST'])
@login_required
@manager_or_admin_required
def return_order(id):
    order  = Order.query.get_or_404(id)
    reason = request.form.get('reason', '')

    # restock items
    for item in order.items:
        product = Product.query.get(item.product_id)
        if product:
            stock_before            = product.stock_quantity
            product.stock_quantity += item.quantity
            movement = StockMovement(
                product_id    = item.product_id,
                created_by    = current_user.id,
                movement_type = MovementType.return_in,
                quantity      = item.quantity,
                stock_before  = stock_before,
                stock_after   = product.stock_quantity,
                reference     = order.order_number,
                note          = f"Return — {reason}"
            )
            db.session.add(movement)

    log_status_change(order, "returned", reason)
    order.status = OrderStatus.returned
    db.session.commit()

    flash(f"Order {order.order_number} marked as returned. Stock restocked.", "success")
    return redirect(url_for('orders.order_detail', id=id))





# ============================
# DELETE BIN
# ================================

@orders_bp.route('/bins/<int:id>/delete', methods=['POST'])
@login_required
@manager_or_admin_required
def delete_bin(id):
    bin_loc = BinLocation.query.get_or_404(id)

    # check if any products are using this bin
    from app.models import Product
    products_using = Product.query.filter_by(bin_location_id=id).count()

    if products_using > 0:
        flash(f"Cannot delete bin '{bin_loc.name}' — {products_using} product(s) are assigned to it. Reassign them first.", "danger")
        return redirect(url_for('orders.bin_locations'))

    db.session.delete(bin_loc)
    db.session.commit()
    flash(f"Bin '{bin_loc.name}' deleted.", "success")
    return redirect(url_for('orders.bin_locations'))


# =========================
# EDIT BIN
# ========================
@orders_bp.route('/bins/<int:id>/edit', methods=['POST'])
@login_required
@manager_or_admin_required
def edit_bin(id):
    bin_loc             = BinLocation.query.get_or_404(id)
    bin_loc.name        = request.form.get('name', '').strip()
    bin_loc.description = request.form.get('description', '').strip()
    db.session.commit()
    flash(f"Bin '{bin_loc.name}' updated.", "success")
    return redirect(url_for('orders.bin_locations'))



# ==========================
# EDT ORDERS
# ========================
@orders_bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@manager_or_admin_required
def edit_order(id):
    order    = Order.query.get_or_404(id)
    products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

    # only allow editing on active orders
    if order.status.value in ['completed', 'cancelled', 'refunded', 'returned']:
        flash("Completed or cancelled orders cannot be edited.", "warning")
        return redirect(url_for('orders.order_detail', id=id))

    if request.method == 'POST':
        # update address
        if order.address:
            order.address.full_name      = request.form.get('full_name', '')
            order.address.phone          = request.form.get('phone', '')
            order.address.address_line_1 = request.form.get('address_line_1', '')
            order.address.address_line_2 = request.form.get('address_line_2', '')
            order.address.city           = request.form.get('city', '')
            order.address.state          = request.form.get('state', '')
            order.address.postal_code    = request.form.get('postal_code', '')

        # update email
        if not order.user:
            order.guest_email = request.form.get('email', '')

        # update fulfilment details
        order.pickup_date      = request.form.get('pickup_date', '')
        order.pickup_time      = request.form.get('pickup_time', '')
        order.note             = request.form.get('note', '')
        order.fulfillment_type = request.form.get('fulfillment_type', 'delivery')

        # update existing items
        item_ids        = request.form.getlist('item_id[]')
        item_quantities = request.form.getlist('item_quantity[]')

        for i, item_id in enumerate(item_ids):
            if not item_id:
                continue
            item = OrderItem.query.get(int(item_id))
            if item and item.order_id == order.id:
                new_qty = int(item_quantities[i]) if item_quantities[i] else 0
                if new_qty <= 0:
                    db.session.delete(item)
                else:
                    item.quantity = new_qty

        # add new items
        new_product_ids = request.form.getlist('new_product_id[]')
        new_quantities  = request.form.getlist('new_quantity[]')

        for i, product_id in enumerate(new_product_ids):
            if not product_id:
                continue
            qty     = int(new_quantities[i]) if new_quantities[i] else 0
            product = Product.query.get(int(product_id))
            if product and qty > 0:
                new_item = OrderItem(
                    order_id      = order.id,
                    product_id    = product.id,
                    quantity      = qty,
                    price         = product.price,
                    product_name  = product.name,
                    product_image = product.image or '',
                )
                db.session.add(new_item)

        # recalculate totals
        db.session.flush()
        subtotal           = sum(float(i.price) * i.quantity for i in order.items)
        delivery_fee       = float(order.delivery_fee or 0)
        order.subtotal     = subtotal
        order.total_amount = subtotal + delivery_fee

        db.session.commit()
        flash(f"Order {order.order_number} updated.", "success")
        return redirect(url_for('orders.order_detail', id=id))

    return render_template(
        'orders/manage_edit_order.html',
        order=order,
        products=products,
    )