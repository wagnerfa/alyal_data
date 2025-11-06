from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required
from app.auth import auth_bp
from app.models import User

@auth_bp.route('/login', methods=['GET', 'POST'])
@auth_bp.route('/auth/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            
            # Redirecionar baseado no tipo de usuário
            if user.is_manager():
                return redirect(url_for('dashboard.manager_dashboard'))
            else:
                return redirect(url_for('dashboard.user_dashboard'))
        else:
            flash('Usuário ou senha inválidos', 'error')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@auth_bp.route('/auth/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
