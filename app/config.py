import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "you-will-never-guess"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or \
     "mysql+pymysql://root@localhost/ecommerce_website"
        # "mysql+pymysql://edkrlist_blog_user:Ayinde%40123456789@localhost/edkrlist_r2_blog"
        # 
   
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # BLOG_NAME = "R2 System Solution Ltd Blog"
    SITE_URL = "http://127.0.0.1:5000"
    # SITE_URL = "https://blog.r2systemsolution.co.uk"
    # Admin credentials (for simplicity, using environment variables)
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME") or "admin"