from datetime import datetime
import enum
from flask_login import UserMixin
from .extensions import db


# =========================
# ENUMS
# =========================
class OrderStatus(enum.Enum):
    new                 = "new"
    payment_confirmed   = "payment_confirmed"
    processing          = "processing"
    picking             = "picking"
    picked              = "picked"
    packed              = "packed"
    ready_for_dispatch  = "ready_for_dispatch"
    dispatched          = "dispatched"
    delivered           = "delivered"
    completed           = "completed"
    payment_failed      = "payment_failed"
    on_hold             = "on_hold"
    out_of_stock        = "out_of_stock"
    partially_fulfilled = "partially_fulfilled"
    cancelled           = "cancelled"
    refunded            = "refunded"
    returned            = "returned"


class PaymentStatus(enum.Enum):
    unpaid = "unpaid"
    paid   = "paid"
    failed = "failed"


class MovementType(enum.Enum):
    purchase   = "purchase"    # stock received from supplier
    sale       = "sale"        # sold online
    pos_sale   = "pos_sale"    # sold via POS
    adjustment = "adjustment"  # manual correction
    damage     = "damage"      # damaged/expired goods
    return_in  = "return_in"   # customer return
    transfer   = "transfer"    # between locations


class POStatus(enum.Enum):
    draft     = "draft"
    sent      = "sent"
    partial   = "partial"    # partially received
    received  = "received"   # fully received
    cancelled = "cancelled"


# =========================
# USERS
# =========================

class User(db.Model, UserMixin):
    __tablename__ = "users"

    id         = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name  = db.Column(db.String(100), nullable=False)
    username   = db.Column(db.String(100), unique=True, nullable=False)
    email      = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone      = db.Column(db.String(20))
    role       = db.Column(db.String(20), default="customer")
    is_admin   = db.Column(db.Boolean, default=False)
    pos_role   = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    addresses     = db.relationship("Address", backref="user", lazy=True)
    orders        = db.relationship("Order", backref="user", lazy=True)
    cart          = db.relationship("Cart", backref="user", uselist=False)
    wishlist_items = db.relationship("Wishlist", backref="user", lazy=True)


# =========================
# ADDRESS
# =========================

class Address(db.Model):
    __tablename__ = "address"

    id             = db.Column(db.Integer, primary_key=True)
    user_id        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    full_name      = db.Column(db.String(150), nullable=False)
    phone          = db.Column(db.String(20), nullable=False)
    address_line_1 = db.Column(db.String(255), nullable=False)
    address_line_2 = db.Column(db.String(255))
    city           = db.Column(db.String(100), nullable=False)
    state          = db.Column(db.String(100), nullable=False)
    country        = db.Column(db.String(100), nullable=False)
    postal_code    = db.Column(db.String(20))
    is_default     = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# SUPPLIER
# =========================

class Supplier(db.Model):
    __tablename__ = "supplier"

    id           = db.Column(db.Integer, primary_key=True)
    name         = db.Column(db.String(200), nullable=False)
    contact_name = db.Column(db.String(150))
    email        = db.Column(db.String(120))
    phone        = db.Column(db.String(30))
    address      = db.Column(db.Text)
    website      = db.Column(db.String(255))
    lead_time_days = db.Column(db.Integer, default=7)  # avg days to deliver
    notes        = db.Column(db.Text)
    is_active    = db.Column(db.Boolean, default=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    products        = db.relationship("Product", backref="supplier", lazy=True)
    purchase_orders = db.relationship("PurchaseOrder", backref="supplier", lazy=True)


# =========================
# CATEGORY
# =========================

class Category(db.Model):
    __tablename__ = "category"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(100), unique=True, nullable=False)
    slug        = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text)
    image       = db.Column(db.String(255))

    products = db.relationship("Product", backref="category", lazy=True)


# =========================
# PRODUCT
# =========================

class Product(db.Model):
    __tablename__ = "product"

    id                = db.Column(db.Integer, primary_key=True)
    category_id       = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    supplier_id       = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=True)

    name              = db.Column(db.String(200), nullable=False)
    slug              = db.Column(db.String(255), unique=True, nullable=False)
    description       = db.Column(db.Text, nullable=False)
    short_description = db.Column(db.String(255))

    price             = db.Column(db.Numeric(10, 2), nullable=False)
    cost_price        = db.Column(db.Numeric(10, 2))       # purchase cost
    discount_price    = db.Column(db.Numeric(10, 2))

    sku               = db.Column(db.String(100), unique=True)
    stock_quantity    = db.Column(db.Integer, default=0)
    low_stock_threshold = db.Column(db.Integer, default=10)  # global fallback

    brand             = db.Column(db.String(100))
    image             = db.Column(db.String(255))
    qr_code           = db.Column(db.String(255))
    barcode_image = db.Column(db.String(255))  

    has_variants      = db.Column(db.Boolean, default=False)

    is_active         = db.Column(db.Boolean, default=True)
    is_featured       = db.Column(db.Boolean, default=False)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    bin_location_id = db.Column(db.Integer, db.ForeignKey("bin_location.id"), nullable=True)
    bin_location    = db.relationship("BinLocation", backref="products")

    variants          = db.relationship(
        "ProductVariant",
        backref="product",
        cascade="all, delete-orphan",
        lazy=True
    )
    stock_movements   = db.relationship("StockMovement", backref="product", lazy=True)


# =========================
# PRODUCT VARIANT
# =========================

class ProductVariant(db.Model):
    __tablename__ = "product_variant"

    id             = db.Column(db.Integer, primary_key=True)
    product_id     = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)

    name           = db.Column(db.String(100), nullable=False)  # e.g. "5kg", "10kg"
    sku            = db.Column(db.String(100), unique=True, nullable=False)
    barcode        = db.Column(db.String(100), unique=True, nullable=True)
    qr_code        = db.Column(db.String(255))
    barcode_image = db.Column(db.String(255))

    price          = db.Column(db.Numeric(10, 2), nullable=False)
    cost_price     = db.Column(db.Numeric(10, 2))
    discount_price = db.Column(db.Numeric(10, 2))

    stock_quantity      = db.Column(db.Integer, default=0)
    low_stock_threshold = db.Column(db.Integer, default=10)

    image          = db.Column(db.String(255))
    is_active      = db.Column(db.Boolean, default=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    stock_movements = db.relationship(
        "StockMovement",
        backref="variant",
        lazy=True,
        foreign_keys="StockMovement.variant_id"
    )
    po_items = db.relationship("PurchaseOrderItem", backref="variant", lazy=True)
    alert    = db.relationship("StockAlert", backref="variant", uselist=False)


# =========================
# STOCK MOVEMENT
# =========================

class StockMovement(db.Model):
    __tablename__ = "stock_movement"

    id          = db.Column(db.Integer, primary_key=True)
    product_id  = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    variant_id  = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=True)
    created_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    movement_type = db.Column(db.Enum(MovementType), nullable=False)
    quantity      = db.Column(db.Integer, nullable=False)  # positive=in, negative=out
    stock_before  = db.Column(db.Integer)
    stock_after   = db.Column(db.Integer)

    reference     = db.Column(db.String(100))  # order number, PO number, etc.
    note          = db.Column(db.Text)

    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    staff = db.relationship("User", backref="stock_movements")


# =========================
# PURCHASE ORDER
# =========================

class PurchaseOrder(db.Model):
    __tablename__ = "purchase_order"

    id           = db.Column(db.Integer, primary_key=True)
    supplier_id  = db.Column(db.Integer, db.ForeignKey("supplier.id"), nullable=False)
    created_by   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    po_number    = db.Column(db.String(100), unique=True, nullable=False)
    status       = db.Column(db.Enum(POStatus), default=POStatus.draft)

    expected_date  = db.Column(db.DateTime)
    received_date  = db.Column(db.DateTime)

    total_cost     = db.Column(db.Numeric(10, 2), default=0)
    notes          = db.Column(db.Text)

    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, onupdate=datetime.utcnow)

    items  = db.relationship(
        "PurchaseOrderItem",
        backref="purchase_order",
        cascade="all, delete-orphan",
        lazy=True
    )
    creator = db.relationship("User", backref="purchase_orders")


# =========================
# PURCHASE ORDER ITEM
# =========================

class PurchaseOrderItem(db.Model):
    __tablename__ = "purchase_order_item"

    id                = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey("purchase_order.id"), nullable=False)
    variant_id        = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=True)
    product_id        = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)

    product_name      = db.Column(db.String(200))  # snapshot
    variant_name      = db.Column(db.String(100))  # snapshot

    quantity_ordered  = db.Column(db.Integer, nullable=False)
    quantity_received = db.Column(db.Integer, default=0)
    unit_cost         = db.Column(db.Numeric(10, 2), nullable=False)
    total_cost        = db.Column(db.Numeric(10, 2))

    created_at        = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# STOCK ALERT
# =========================

class StockAlert(db.Model):
    __tablename__ = "stock_alert"

    id         = db.Column(db.Integer, primary_key=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    threshold  = db.Column(db.Integer, nullable=False, default=10)
    is_active  = db.Column(db.Boolean, default=True)
    last_sent  = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# CART
# =========================

class Cart(db.Model):
    __tablename__ = "cart"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user_key   = db.Column(db.String(100), index=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    items = db.relationship(
        "CartItem",
        backref="cart",
        cascade="all, delete-orphan",
        lazy=True
    )


class CartItem(db.Model):
    __tablename__ = "cart_item"

    id           = db.Column(db.Integer, primary_key=True)
    cart_id      = db.Column(db.Integer, db.ForeignKey("cart.id"), nullable=False)
    product_id   = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    variant_id   = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=True)
    quantity     = db.Column(db.Integer, default=1)
    unit_price   = db.Column(db.Numeric(10, 2))
    product_name = db.Column(db.String(200))
    product_image = db.Column(db.String(255))
    from_wishlist = db.Column(db.Boolean, default=False)

    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")


# =========================
# WISHLIST
# =========================

class Wishlist(db.Model):
    __tablename__ = "wishlist"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    user_key   = db.Column(db.String(100), index=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# ORDER
# =========================

class Order(db.Model):
    __tablename__ = "orders"

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    address_id   = db.Column(db.Integer, db.ForeignKey("address.id"), nullable=False)
    order_number = db.Column(db.String(100), unique=True, nullable=False)

    subtotal     = db.Column(db.Numeric(10, 2), nullable=False)
    shipping_fee = db.Column(db.Numeric(10, 2), default=0)
    tax          = db.Column(db.Numeric(10, 2), default=0)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    delivery_miles = db.Column(db.Numeric(5, 1))
    delivery_fee   = db.Column(db.Numeric(10, 2))

    status         = db.Column(db.Enum(OrderStatus), default=OrderStatus.new, nullable=False)
    payment_status = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.unpaid, nullable=False)

    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    prep_time        = db.Column(db.Integer, nullable=True)
    timer_started_at = db.Column(db.DateTime, nullable=True)
    timer_status     = db.Column(db.String(20), default="pending")

    fulfillment_type = db.Column(db.String(20), default='delivery')
    pickup_date      = db.Column(db.String(20))
    pickup_time      = db.Column(db.String(20))

    guest_email      = db.Column(db.String(120))
    rejection_reason = db.Column(db.Text, nullable=True)
    note             = db.Column(db.Text, nullable=True)

    address = db.relationship("Address", backref="orders")
    items   = db.relationship(
        "OrderItem",
        backref="order",
        cascade="all, delete-orphan",
        lazy=True
    )
    payment = db.relationship("Payment", backref="order", uselist=False)

    @property
    def status_name(self):
        """Safely retrieve status string without blowing up on None."""
        if self.status is None:
            return "new"
        return (
            self.status.value
            if isinstance(self.status, OrderStatus)
            else str(self.status)
        )


# =========================
# ORDER ITEM
# =========================

class OrderItem(db.Model):
    __tablename__ = "order_item"

    id           = db.Column(db.Integer, primary_key=True)
    order_id     = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id   = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    variant_id   = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=True)
    quantity     = db.Column(db.Integer, nullable=False)
    price        = db.Column(db.Numeric(10, 2), nullable=False)
    product_name  = db.Column(db.String(200))
    product_image = db.Column(db.String(255))
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, onupdate=datetime.utcnow)

    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")


# =========================
# PAYMENT
# =========================

class Payment(db.Model):
    __tablename__ = "payment"

    id             = db.Column(db.Integer, primary_key=True)
    order_id       = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    transaction_id = db.Column(db.String(255), unique=True)
    amount         = db.Column(db.Numeric(10, 2), nullable=False)
    status         = db.Column(db.Enum(PaymentStatus), default=PaymentStatus.unpaid, nullable=False)
    reference      = db.Column(db.String(255), unique=True)
    gateway_response = db.Column(db.Text)
    paid_at        = db.Column(db.DateTime)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, onupdate=datetime.utcnow)


# =========================
# REVIEW
# =========================

class Review(db.Model):
    __tablename__ = "review"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    rating     = db.Column(db.Integer, nullable=False)
    comment    = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# COUPON
# =========================

class Coupon(db.Model):
    __tablename__ = "coupon"

    id                   = db.Column(db.Integer, primary_key=True)
    code                 = db.Column(db.String(50), unique=True, nullable=False)
    discount_type        = db.Column(db.String(20), nullable=False)
    discount_value       = db.Column(db.Numeric(10, 2), nullable=False)
    minimum_order_amount = db.Column(db.Numeric(10, 2), default=0)
    expiration_date      = db.Column(db.DateTime)
    is_active            = db.Column(db.Boolean, default=True)


# =========================
# NEWSLETTER
# =========================

class NewsletterSubscriber(db.Model):
    __tablename__ = "newsletter_subscriber"

    id             = db.Column(db.Integer, primary_key=True)
    email          = db.Column(db.String(120), unique=True, nullable=False)
    is_active      = db.Column(db.Boolean, default=True)
    subscribed_at  = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# CHECKOUT DRAFT
# =========================

class CheckoutDraft(db.Model):
    __tablename__ = "checkout_draft"

    id       = db.Column(db.Integer, primary_key=True)
    user_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    user_key = db.Column(db.String(255), index=True)

    full_name = db.Column(db.String(150))
    email     = db.Column(db.String(120))
    phone     = db.Column(db.String(20))

    address_line_1 = db.Column(db.String(255))
    address_line_2 = db.Column(db.String(255))
    country        = db.Column(db.String(100))
    city           = db.Column(db.String(100))
    state          = db.Column(db.String(100))
    postal_code    = db.Column(db.String(20))

    cart_snapshot    = db.Column(db.Text)
    delivery_method  = db.Column(db.String(50))
    fulfillment_type = db.Column(db.String(20), default='delivery')
    pickup_date      = db.Column(db.String(20))
    pickup_time      = db.Column(db.String(20))
    note             = db.Column(db.Text, nullable=True)

    subtotal     = db.Column(db.Numeric(10, 2))
    shipping_fee = db.Column(db.Numeric(10, 2), default=0)
    tax          = db.Column(db.Numeric(10, 2), default=0)
    total        = db.Column(db.Numeric(10, 2))

    billing_address_line_1 = db.Column(db.String(255))
    billing_address_line_2 = db.Column(db.String(255))
    billing_city           = db.Column(db.String(100))
    billing_state          = db.Column(db.String(100))
    billing_postal_code    = db.Column(db.String(20))

    delivery_miles = db.Column(db.Numeric(5, 1))
    delivery_fee   = db.Column(db.Numeric(10, 2))
    same_as_delivery = db.Column(db.Boolean, default=True)

    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed    = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)


# =========================
# POS SESSION
# =========================

class POSSession(db.Model):
    __tablename__ = "pos_session"

    id            = db.Column(db.Integer, primary_key=True)
    staff_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    opened_at     = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at     = db.Column(db.DateTime, nullable=True)
    opening_float = db.Column(db.Numeric(10, 2), default=0)
    closing_float = db.Column(db.Numeric(10, 2), nullable=True)
    is_active     = db.Column(db.Boolean, default=True)

    staff  = db.relationship("User", backref="pos_sessions")
    orders = db.relationship("POSOrder", backref="session", lazy=True)


# =========================
# POS ORDER
# =========================

class POSOrder(db.Model):
    __tablename__ = "pos_order"

    id           = db.Column(db.Integer, primary_key=True)
    session_id   = db.Column(db.Integer, db.ForeignKey("pos_session.id"), nullable=False)
    staff_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    order_number = db.Column(db.String(100), unique=True, nullable=False)

    subtotal        = db.Column(db.Numeric(10, 2), nullable=False)
    discount        = db.Column(db.Numeric(10, 2), default=0)
    total_amount    = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method  = db.Column(db.String(20), default="cash")
    amount_tendered = db.Column(db.Numeric(10, 2), nullable=True)
    change_given    = db.Column(db.Numeric(10, 2), nullable=True)

    payment_intent_id = db.Column(db.String(255), nullable=True)

    customer_name  = db.Column(db.String(150), nullable=True)
    customer_email = db.Column(db.String(120), nullable=True)
    customer_phone = db.Column(db.String(20), nullable=True)

    status     = db.Column(db.String(20), default="completed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    staff = db.relationship("User", backref="pos_orders")
    items = db.relationship(
        "POSOrderItem",
        backref="order",
        cascade="all, delete-orphan",
        lazy=True
    )


# =========================
# POS ORDER ITEM
# =========================

class POSOrderItem(db.Model):
    __tablename__ = "pos_order_item"

    id            = db.Column(db.Integer, primary_key=True)
    order_id      = db.Column(db.Integer, db.ForeignKey("pos_order.id"), nullable=False)
    product_id    = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    variant_id    = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=True)
    quantity      = db.Column(db.Integer, nullable=False)
    unit_price    = db.Column(db.Numeric(10, 2), nullable=False)
    total_price   = db.Column(db.Numeric(10, 2), nullable=False)
    product_name  = db.Column(db.String(200))
    product_image = db.Column(db.String(255))
    product_sku   = db.Column(db.String(100))

    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")




# =========================
# BIN LOCATION
# =========================
class BinLocation(db.Model):
    __tablename__ = "bin_location"

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(50), nullable=False)  # e.g. A1, B3, SHELF-2
    description = db.Column(db.String(200))
    is_active   = db.Column(db.Boolean, default=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)


# =========================
# STOCK RESERVATION
# =========================
class StockReservation(db.Model):
    __tablename__ = "stock_reservation"

    id         = db.Column(db.Integer, primary_key=True)
    order_id   = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    variant_id = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=True)
    quantity   = db.Column(db.Integer, nullable=False)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    order   = db.relationship("Order", backref="reservations")
    product = db.relationship("Product")
    variant = db.relationship("ProductVariant")


# =========================
# ORDER STATUS LOG
# =========================
class OrderStatusLog(db.Model):
    __tablename__ = "order_status_log"

    id          = db.Column(db.Integer, primary_key=True)
    order_id    = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    from_status = db.Column(db.String(50))
    to_status   = db.Column(db.String(50), nullable=False)
    changed_by  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    note        = db.Column(db.Text)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    order  = db.relationship("Order", backref="status_logs")
    staff  = db.relationship("User")


# =========================
# PICKING LIST
# =========================
class PickingList(db.Model):
    __tablename__ = "picking_list"

    id           = db.Column(db.Integer, primary_key=True)
    order_id     = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, unique=True)
    generated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status       = db.Column(db.String(20), default="pending")  # pending, in_progress, completed
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)

    order  = db.relationship("Order", backref=db.backref("picking_list", uselist=False))
    staff  = db.relationship("User")
    items  = db.relationship(
        "PickingListItem",
        backref="picking_list",
        cascade="all, delete-orphan",
        lazy=True
    )


# =========================
# PICKING LIST ITEM
# =========================
class PickingListItem(db.Model):
    __tablename__ = "picking_list_item"

    id               = db.Column(db.Integer, primary_key=True)
    picking_list_id  = db.Column(db.Integer, db.ForeignKey("picking_list.id"), nullable=False)
    order_item_id    = db.Column(db.Integer, db.ForeignKey("order_item.id"), nullable=False)
    product_id       = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    variant_id       = db.Column(db.Integer, db.ForeignKey("product_variant.id"), nullable=True)
    bin_location_id  = db.Column(db.Integer, db.ForeignKey("bin_location.id"), nullable=True)

    product_name     = db.Column(db.String(200))
    variant_name     = db.Column(db.String(100))
    sku              = db.Column(db.String(100))
    barcode_image    = db.Column(db.String(255))

    quantity_to_pick = db.Column(db.Integer, nullable=False)
    quantity_picked  = db.Column(db.Integer, default=0)
    is_picked        = db.Column(db.Boolean, default=False)
    picked_at        = db.Column(db.DateTime, nullable=True)
    picked_by        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    order_item   = db.relationship("OrderItem")
    product      = db.relationship("Product")
    variant      = db.relationship("ProductVariant")
    bin_location = db.relationship("BinLocation")
    picker       = db.relationship("User")


# =========================
# SHIPMENT
# =========================
class Shipment(db.Model):
    __tablename__ = "shipment"

    id              = db.Column(db.Integer, primary_key=True)
    order_id        = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, unique=True)
    driver_name     = db.Column(db.String(150))
    driver_phone    = db.Column(db.String(20))
    tracking_ref    = db.Column(db.String(100))
    notes           = db.Column(db.Text)
    dispatched_at   = db.Column(db.DateTime, nullable=True)
    delivered_at    = db.Column(db.DateTime, nullable=True)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    order = db.relationship("Order", backref=db.backref("shipment", uselist=False))