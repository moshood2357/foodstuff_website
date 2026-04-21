from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.auth import auth_bp
from app.extensions import db
from app.models import User
from werkzeug.security import generate_password_hash, check_password_hash


# =========================
# REGISTER
# =========================
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')

        # check if user exists
        existing_user = User.query.filter(
            (User.email == email) | (User.username == username)
        ).first()

        if existing_user:
            flash("User with email or username already exists", "danger")
            return redirect(url_for('auth.register'))

        new_user = User(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            role="customer"   # default role
        )

        db.session.add(new_user)
        db.session.commit()

        flash("Account created successfully!", "success")
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


# =========================
# LOGIN
# =========================
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        login_input = request.form.get('login')  # username or email
        password = request.form.get('password')

        # allow login with username OR email
        user = User.query.filter(
            (User.username == login_input) | (User.email == login_input)
        ).first()

        if user and check_password_hash(user.password_hash, password):

            login_user(user)
            flash("Login successful", "success")

            # =========================
            # ROLE-BASED REDIRECT
            # =========================
            if user.role == "admin":
                return redirect(url_for('admin.dashboard'))

            return redirect(url_for('main.home'))

        flash("Invalid credentials", "danger")

    return render_template('auth/login.html')


# =========================
# LOGOUT
# =========================
@auth_bp.route('/logout')
@login_required
def logout():

    logout_user()
    flash("Logged out successfully", "info")
    return redirect(url_for('auth.login'))


# =========================
# PROFILE
# =========================
@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():

    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')
        current_user.phone = request.form.get('phone')

        db.session.commit()

        flash("Profile updated successfully!", "success")
        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html', user=current_user)