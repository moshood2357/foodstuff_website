from flask import redirect, render_template, request, url_for, flash
from app import db
from flask_login import login_required
from app.models import Order, OrderStatus, PaymentStatus
from app.ecommerce.orders import order_bp
from app.utils.decorators import admin_required


# =========================
# ORDER LIST VIEW
# =========================
@order_bp.route("/orders-list")
@login_required
def orders_list():
    page = request.args.get("page", 1, type=int)
    orders = Order.query.order_by(Order.id.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/orders.html", orders=orders)




@order_bp.route("/<int:id>")
@login_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    return render_template("orders/order_detail.html", order=order)
    

@order_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_order(id):
    order = Order.query.get_or_404(id)

    if request.method == 'POST':
        # update address
        order.address.full_name     = request.form.get('full_name', order.address.full_name)
        order.address.phone         = request.form.get('phone', order.address.phone)
        order.address.address_line_1 = request.form.get('address_line_1', order.address.address_line_1)
        order.address.address_line_2 = request.form.get('address_line_2', order.address.address_line_2)
        order.address.city          = request.form.get('city', order.address.city)
        order.address.state         = request.form.get('state', order.address.state)
        order.address.country       = request.form.get('country', order.address.country)
        order.address.postal_code   = request.form.get('postal_code', order.address.postal_code)

        # update order fields
        order.delivery_method  = request.form.get('delivery_method', order.delivery_method)
        order.status           = OrderStatus[request.form.get('status', order.status.value)]
        order.payment_status   = PaymentStatus[request.form.get('payment_status', order.payment_status.value)]

        db.session.commit()
        flash("Order updated successfully", "success")
        return redirect(url_for('admin.orders'))

    return render_template('orders/edit_order.html', order=order)