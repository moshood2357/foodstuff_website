from flask import jsonify, redirect, render_template, request, flash, url_for
from flask_login import login_required
from . import main
from app.models import Category, Product, NewsletterSubscriber
from app.extensions import db

from app.extensions import limiter
import re
import socket

def is_valid_email_domain(email):
    """Check the domain has valid MX or A records"""
    try:
        domain = email.split('@')[1]
        socket.getaddrinfo(domain, None)
        return True
    except (IndexError, socket.gaierror):
        return False

    
@main.route('/')
def home():
    featured_products = Product.query.order_by(Product.created_at.desc()).limit(8).all()
    categories = Category.query.limit(12).all()

    return render_template(
        'main/index.html',
        featured_products=featured_products,
        categories=categories
    )

@main.route('/shop')
def shop():
    page = request.args.get('page', 1, type=int)
    category_id = request.args.get('category', type=int)
    sort = request.args.get('sort')

    categories = Category.query.all()

    query = Product.query

    #  FILTER BY CATEGORY
    if category_id:
        query = query.filter(Product.category_id == category_id)

    #  SORTING
    if sort == "newest":
        query = query.order_by(Product.created_at.desc())

    elif sort == "low_high":
        query = query.order_by(Product.price.asc())

    elif sort == "high_low":
        query = query.order_by(Product.price.desc())

    
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.paginate(page=page, per_page=12)

    return render_template(
        'main/shop.html',
        products=products,
        categories=categories,
        selected_category=category_id,
        selected_sort=sort
    )



@main.route('/product/<slug>')
def product_details(slug):
    product = Product.query.filter_by(slug=slug).first_or_404()

    related_products = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id
    ).limit(4).all()

    return render_template(
        'main/product_details.html',
        product=product,
        related_products=related_products
    )


@main.route('/search')
def search():
    query = request.args.get('q', '')

    products = Product.query.filter(
        Product.name.ilike(f'%{query}%')
    ).all()

    return render_template(
        'main/search_results.html',
        products=products,
        query=query
    )


@main.route('/about-us')
def about():
    return render_template('main/about.html')


@main.route('/contact-us')
def contact():
    return render_template('main/contact.html')


@main.route('/subscribe', methods=['POST'])
@limiter.limit("3 per minute; 10 per hour")
def subscribe():
    # honeypot
    if request.form.get('website'):
        flash("Subscribed successfully!", "success")
        return redirect(url_for('main.home'))

    email = request.form.get('email', '').strip().lower()

    # basic format check
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        flash("Please enter a valid email address.", "danger")
        return redirect(url_for('main.home'))

    # domain check
    if not is_valid_email_domain(email):
        flash("Please enter a valid email address.", "danger")
        return redirect(url_for('main.home'))

    # check already subscribed
    existing = NewsletterSubscriber.query.filter_by(email=email).first()
    if existing:
        flash("You're already subscribed!", "info")
        return redirect(url_for('main.home'))

    subscriber = NewsletterSubscriber(email=email, is_active=True)
    db.session.add(subscriber)
    db.session.commit()

    flash("Thanks for subscribing!", "success")
    return redirect(url_for('main.home'))  



@main.route("/api/search")
def api_search():
    q           = request.args.get("q", "").strip()
    category_id = request.args.get("category", "")
    limit       = int(request.args.get("limit", 30))

    query = Product.query.filter(Product.is_active == True)

    if q:
        # search by product name OR by category name
        from app.models import Category
        matching_cats = Category.query.filter(
            Category.name.ilike(f"%{q}%")
        ).all()
        cat_ids = [c.id for c in matching_cats]

        if cat_ids:
            query = query.filter(
                db.or_(
                    Product.name.ilike(f"%{q}%"),
                    Product.category_id.in_(cat_ids)
                )
            )
        else:
            query = query.filter(Product.name.ilike(f"%{q}%"))

    if category_id:
        query = query.filter(Product.category_id == int(category_id))

    products = query.limit(limit).all()

    return jsonify([{
        "id":          p.id,
        "name":        p.name,
        "slug":        p.slug,
        "price":       str(p.price),
        "image":       p.image or "",
        "category":    p.category.name if p.category else "",
        "category_id": p.category_id,
    } for p in products])



@main.route("/api/categories")
def get_categories():
    from app.models import Category
    categories = Category.query.order_by(Category.name).all()
    return jsonify([{"id": c.id, "name": c.name} for c in categories])


@main.route('/category/<slug>')
def category_products(slug):

    page = request.args.get('page', 1, type=int)
    per_page = 12

    category = Category.query.filter_by(slug=slug).first_or_404()

    products = Product.query.filter_by(category_id=category.id)\
        .paginate(page=page, per_page=per_page)

    return render_template(
        "main/category_products.html",
        category=category,
        products=products.items,
        pagination=products
    )


@main.route('/faq')
def faq():
    return render_template('main/faq.html')


@main.route('/gift-card-policy')
def gift_card_policy():
    return render_template('main/gift_card_policy.html')



@main.route('/acceptable-use-policy')
def acceptable_use_policy():
    return render_template('main/acceptable_use_policy.html')

@main.route('/environmental-statement')
def environmental_statement():
    return render_template('main/environmental_statement.html')

@main.route('/privacy-policy')
def privacy_policy():
    return render_template('main/privacy_policy.html')

@main.route('/accessibility-statement')
def accessibility_statement():
    return render_template('main/accessibility_statement.html')

@main.route('/allergy-policy')
def allergy_policy():
    return render_template('main/allergy_policy.html')

@main.route('/click-and-collect-policy')
def click_and_collect_policy():
    return render_template('main/click_and_collect_policy.html')

# @main.route('/sitemap.xml')
# def sitemap():  
#     return render_template('main/sitemap.xml'), 200, {'Content-Type': 'application/xml'}

# @main.route('/robots.txt')
# def robots():                   
#     return render_template('main/robots.txt'), 200, {'Content-Type': 'text/plain'}

@main.route('/complaints-procedure')
def complaints_procedure():
    return render_template('main/complaints_procedure.html')

@main.route('/cookie-policy')
def cookie_policy():
    return render_template('main/cookie_policy.html')

@main.route('/data-protection-rights-policy')
def data_protection_rights_policy():
    return render_template('main/data_protection_rights_policy.html')

@main.route('/delivery-policy')
def delivery_policy():
    return render_template('main/delivery_policy.html')

@main.route('/legal-notices')
def legal_notices():
    return render_template('main/legal_notices.html')

@main.route('/loyalty-programme-policy')
def loyalty_programme_policy():
    return render_template('main/loyalty_programme_policy.html')

@main.route('/modern-slavery-statement')
def modern_slavery_statement():
    return render_template('main/modern_slavery_statement.html')

@main.route('/payment-policy')
def payment_policy():
    return render_template('main/payment_policy.html')

@main.route('/returns-and-refunds-policy')
def returns_and_refund_policy():
    return render_template('main/returns_and_refund_policy.html')

@main.route('/social-media-policy')
def social_media_policy():
    return render_template('main/social_media_policy.html')


@main.route('/supplier-and-product-responsibility')
def supplier_and_product_responsibility():
    return render_template('main/supplier_and_product_responsibility.html')

@main.route('/terms-and-conditions')
def terms_and_conditions():
    return render_template('main/terms_and_conditions.html')

@main.route('/terms-of-sale')
def terms_of_sale():
    return render_template('main/terms_of_sale.html')

@main.route('/website-legal-disclaimer')
def website_legal_disclaimer():
    return render_template('main/website_legal_disclaimer.html')
# @main.route('/terms')
# def terms():
#     return render_template('main/terms.html')