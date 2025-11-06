from flask import Blueprint

data_bp = Blueprint('data', __name__, url_prefix='/data')

from app.data import routes  # noqa: E402,F401
