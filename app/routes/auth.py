from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user
from app import db
from app.models.user import User
import re

bp = Blueprint('auth', __name__)


def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    return len(password) >= 6


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').strip()
        password = data.get('password', '')
        remember = data.get('remember', False)

        if not email or not password:
            return jsonify({'success': False, 'message': 'Preencha todos os campos'}), 400

        user = User.query.filter_by(email=email).first()

        if user is None or not user.check_password(password):
            return jsonify({'success': False, 'message': 'Email ou senha incorretos'}), 401

        login_user(user, remember=remember)
        return jsonify({'success': True, 'redirect': url_for('main.dashboard')})

    return render_template('auth/login.html')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')

        # Validações
        if not username or not email or not password or not confirm_password:
            return jsonify({'success': False, 'message': 'Preencha todos os campos'}), 400

        if len(username) < 3:
            return jsonify({'success': False, 'message': 'Nome de usuário deve ter pelo menos 3 caracteres'}), 400

        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Email inválido'}), 400

        if not validate_password(password):
            return jsonify({'success': False, 'message': 'Senha deve ter pelo menos 6 caracteres'}), 400

        if password != confirm_password:
            return jsonify({'success': False, 'message': 'As senhas não coincidem'}), 400

        # Verificar se usuário já existe
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Nome de usuário já existe'}), 400

        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Email já cadastrado'}), 400

        # Criar novo usuário
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        return jsonify({'success': True, 'redirect': url_for('main.dashboard')})

    return render_template('auth/register.html')


@bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))