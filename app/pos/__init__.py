from flask import Blueprint

pos_bp = Blueprint('pos', __name__, template_folder='templates')

from . import routes