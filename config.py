import os

class Config:
    # Security
    SECRET_KEY = os.environ.get("SECRET_KEY") or "you-will-never-guess"

    # Database
    # Make sure your database "foodstuff_eccormmerce" exists in MySQL
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
        "mysql+pymysql://root@localhost/ecommerce_website"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Admin credentials (for simplicity, using environment variables)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME") or "admin"
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "admin123"

    # Optional app settings
    BLOG_NAME = "Foodstuff E-commerce"
    SITE_URL = os.environ.get("SITE_URL") or "http://localhost:6000"