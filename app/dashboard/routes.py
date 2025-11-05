from flask import redirect, render_template, url_for
from flask_login import current_user, login_required

from app.dashboard import dashboard_bp


def _redirect_to_role_dashboard():
    if current_user.is_authenticated and current_user.is_manager():
        return redirect(url_for('dashboard.manager_dashboard'))
    return redirect(url_for('dashboard.user_dashboard'))


@dashboard_bp.route('/')
@login_required
def dashboard_index():
    return _redirect_to_role_dashboard()


@dashboard_bp.route('/manager')
@login_required
def manager_dashboard():
    if not current_user.is_manager():
        return _redirect_to_role_dashboard()
    return render_template('dashboard_manager.html')


@dashboard_bp.route('/user')
@login_required
def user_dashboard():
    if current_user.is_manager():
        return _redirect_to_role_dashboard()
    return render_template('dashboard_user.html')
