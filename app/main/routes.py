from flask import redirect, render_template, url_for
from flask_login import current_user

from app.main import main_bp


def _redirect_to_dashboard():
    if current_user.is_authenticated:
        if current_user.is_manager():
            return redirect(url_for('dashboard.manager_dashboard'))
        return redirect(url_for('dashboard.user_dashboard'))
    return None


@main_bp.route('/')
def home():
    redirect_response = _redirect_to_dashboard()
    if redirect_response:
        return redirect_response
    return render_template('home.html')
