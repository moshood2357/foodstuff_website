import os
import uuid

from dotenv import load_dotenv

from flask import Flask, send_from_directory, session
from flask_ckeditor import CKEditor
from flask_compress import Compress
from flask_login import current_user
from flask_wtf import CSRFProtect

from .extensions import db, migrate, login_manager
from app.models import Cart, CartItem, Wishlist, User

load_dotenv()

ckeditor = CKEditor()
csrf = CSRFProtect()


def create_app(config_class="config.Config"):
    app = Flask(__name__)

    app.config.from_object(config_class)

    
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-key")

    # =========================
    # FILE UPLOAD CONFIG
    # =========================
    upload_folder = os.path.join(app.root_path, "static", "uploads")
    app.config['UPLOAD_FOLDER'] = upload_folder
    os.makedirs(upload_folder, exist_ok=True)

    # =========================
    # INIT EXTENSIONS
    # =========================
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    ckeditor.init_app(app)
    csrf.init_app(app)
    Compress(app)

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    # =========================
    # USER LOADER
    # =========================
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # =========================
    # CONTEXT PROCESSOR
    # =========================
    @app.context_processor
    def inject_counts():
        cart_count = 0
        wishlist_count = 0

        if current_user.is_authenticated:
            cart = Cart.query.filter_by(user_id=current_user.id).first()

            if cart:
                cart_count = (
                    db.session.query(db.func.coalesce(db.func.count(CartItem.id), 0))
                    .filter_by(cart_id=cart.id)
                    .scalar()
                )

            wishlist_count = Wishlist.query.filter_by(
                user_id=current_user.id
            ).count()

        return dict(
            cart_count=cart_count,
            wishlist_count=wishlist_count
        )


    @app.before_request
    def create_guest_session():
        if "guest_id" not in session:
            session["guest_id"] = str(uuid.uuid4())

    @app.context_processor
    def inject_cart_data():
        if current_user.is_authenticated:
            cart = Cart.query.filter_by(user_id=current_user.id).first()

            if cart:
                cart_items = db.session.query(CartItem.product_id)\
                    .filter_by(cart_id=cart.id).all()

                cart_product_ids = [item[0] for item in cart_items]
            else:
                cart_product_ids = []

            return dict(cart_product_ids=cart_product_ids)

        return dict(cart_product_ids=[])

    # =========================
    # FAVICON
    # =========================
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, 'static'),
            'favicon.ico',
            mimetype='image/vnd.microsoft.icon'
        )

    # =========================
    # IMPORT MODELS
    # =========================
    from app.models import (
        User, Address, Category, Product,
        Cart, CartItem, Wishlist,
        Order, OrderItem, Payment,
        Review, Coupon, NewsletterSubscriber
    )

    # =========================
    # BLUEPRINTS
    # =========================
    from .main import main as main_bp
    from .admin import admin_bp
    from .auth import auth_bp
    from app.ecommerce.cart import cart_bp
    from app.ecommerce.wishlist import wishlist_bp
    from app.ecommerce.checkout import checkout_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(checkout_bp, url_prefix="/checkout")

    print(app.url_map)

    return app