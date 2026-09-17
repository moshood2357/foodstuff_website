from functools import wraps
from flask import flash
from flask_login import current_user

from flask import redirect, url_for

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            # if they have a POS role, send them to POS instead
            if current_user.pos_role in ['cashier', 'manager']:
                return redirect(url_for('pos.index'))
            flash("Admin access required.", "danger")
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated