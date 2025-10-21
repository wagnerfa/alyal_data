from flask import Blueprint, render_template, redirect, url_for, request, jsonify, flash
from flask_login import login_required, current_user
from app import db
from app.models.company import Company
from app.models.user import User
from functools import wraps


bp = Blueprint('admin', __name__, url_prefix='/admin')


def gestor_required(f):
    """Decorator para permitir apenas gestores"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_gestor():
            return jsonify({'success': False, 'message': 'Acesso negado. Apenas gestores podem acessar.'}), 403
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    """Decorator para permitir gestores e analistas"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.can_view_all_companies():
            return jsonify({'success': False, 'message': 'Acesso negado.'}), 403
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# ROTAS DE EMPRESAS
# ============================================================================

@bp.route('/companies')
@login_required
@staff_required
def companies_list():
    """Lista todas as empresas"""
    companies = Company.query.order_by(Company.created_at.desc()).all()
    return render_template('admin/companies/list.html', companies=companies)


@bp.route('/companies/new', methods=['GET'])
@login_required
@gestor_required
def companies_new():
    """Formulário para criar nova empresa"""
    return render_template('admin/companies/form.html', company=None)


@bp.route('/companies/create', methods=['POST'])
@login_required
@gestor_required
def companies_create():
    """Cria uma nova empresa"""
    data = request.get_json() if request.is_json else request.form

    name = data.get('name', '').strip()
    cnpj = data.get('cnpj', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()

    # Validações
    if not name:
        return jsonify({'success': False, 'message': 'Nome da empresa é obrigatório'}), 400

    if len(name) < 3:
        return jsonify({'success': False, 'message': 'Nome deve ter pelo menos 3 caracteres'}), 400

    # Verificar se CNPJ já existe (se fornecido)
    if cnpj:
        existing_company = Company.query.filter_by(cnpj=cnpj).first()
        if existing_company:
            return jsonify({'success': False, 'message': 'CNPJ já cadastrado'}), 400

    # Criar empresa
    company = Company(
        name=name,
        cnpj=cnpj if cnpj else None,
        email=email if email else None,
        phone=phone if phone else None
    )

    db.session.add(company)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Empresa criada com sucesso!',
        'company': company.to_dict(),
        'redirect': url_for('admin.companies_detail', company_id=company.id)
    })


@bp.route('/companies/<int:company_id>')
@login_required
@staff_required
def companies_detail(company_id):
    """Detalhes de uma empresa específica"""
    company = Company.query.get_or_404(company_id)
    clients = company.clients.filter_by(is_active=True).all()
    return render_template('admin/companies/detail.html', company=company, clients=clients)


@bp.route('/companies/<int:company_id>/edit', methods=['GET'])
@login_required
@gestor_required
def companies_edit(company_id):
    """Formulário para editar empresa"""
    company = Company.query.get_or_404(company_id)
    return render_template('admin/companies/form.html', company=company)


@bp.route('/companies/<int:company_id>/update', methods=['POST'])
@login_required
@gestor_required
def companies_update(company_id):
    """Atualiza uma empresa"""
    company = Company.query.get_or_404(company_id)
    data = request.get_json() if request.is_json else request.form

    name = data.get('name', '').strip()
    cnpj = data.get('cnpj', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    is_active = data.get('is_active', 'true').lower() == 'true'

    # Validações
    if not name:
        return jsonify({'success': False, 'message': 'Nome da empresa é obrigatório'}), 400

    if len(name) < 3:
        return jsonify({'success': False, 'message': 'Nome deve ter pelo menos 3 caracteres'}), 400

    # Verificar CNPJ duplicado (exceto a própria empresa)
    if cnpj:
        existing = Company.query.filter(Company.cnpj == cnpj, Company.id != company_id).first()
        if existing:
            return jsonify({'success': False, 'message': 'CNPJ já cadastrado em outra empresa'}), 400

    # Atualizar empresa
    company.name = name
    company.cnpj = cnpj if cnpj else None
    company.email = email if email else None
    company.phone = phone if phone else None
    company.is_active = is_active

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Empresa atualizada com sucesso!',
        'company': company.to_dict(),
        'redirect': url_for('admin.companies_detail', company_id=company.id)
    })


@bp.route('/companies/<int:company_id>/delete', methods=['POST'])
@login_required
@gestor_required
def companies_delete(company_id):
    """Desativa uma empresa (soft delete)"""
    company = Company.query.get_or_404(company_id)

    # Verificar se tem clientes ativos
    active_clients = company.clients.filter_by(is_active=True).count()
    if active_clients > 0:
        return jsonify({
            'success': False,
            'message': f'Não é possível desativar. A empresa possui {active_clients} cliente(s) ativo(s).'
        }), 400

    company.is_active = False
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Empresa desativada com sucesso!',
        'redirect': url_for('admin.companies_list')
    })


# ============================================================================
# ROTAS DE CLIENTES (Usuários das Empresas)
# ============================================================================

@bp.route('/companies/<int:company_id>/clients')
@login_required
@staff_required
def clients_list(company_id):
    """Lista clientes de uma empresa"""
    company = Company.query.get_or_404(company_id)
    clients = company.clients.order_by(User.created_at.desc()).all()
    return render_template('admin/companies/clients.html', company=company, clients=clients)


@bp.route('/companies/<int:company_id>/clients/new', methods=['GET'])
@login_required
@gestor_required
def clients_new(company_id):
    """Formulário para adicionar novo cliente"""
    company = Company.query.get_or_404(company_id)
    return render_template('admin/companies/client_form.html', company=company, client=None)


@bp.route('/companies/<int:company_id>/clients/create', methods=['POST'])
@login_required
@gestor_required
def clients_create(company_id):
    """Cria um novo cliente para a empresa"""
    company = Company.query.get_or_404(company_id)
    data = request.get_json() if request.is_json else request.form

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')

    # Validações
    if not username or not email or not password:
        return jsonify({'success': False, 'message': 'Preencha todos os campos obrigatórios'}), 400

    if len(username) < 3:
        return jsonify({'success': False, 'message': 'Nome de usuário deve ter pelo menos 3 caracteres'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Senha deve ter pelo menos 6 caracteres'}), 400

    # Verificar duplicatas
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Nome de usuário já existe'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email já cadastrado'}), 400

    # Criar cliente
    client = User(
        username=username,
        email=email,
        role='cliente',
        company_id=company.id
    )
    client.set_password(password)

    db.session.add(client)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Cliente criado com sucesso!',
        'client': client.to_dict(),
        'redirect': url_for('admin.companies_detail', company_id=company.id)
    })


@bp.route('/companies/<int:company_id>/clients/<int:client_id>/edit', methods=['GET'])
@login_required
@gestor_required
def clients_edit(company_id, client_id):
    """Formulário para editar cliente"""
    company = Company.query.get_or_404(company_id)
    client = User.query.get_or_404(client_id)

    # Verificar se o cliente pertence à empresa
    if client.company_id != company.id:
        flash('Cliente não pertence a esta empresa', 'error')
        return redirect(url_for('admin.companies_detail', company_id=company.id))

    return render_template('admin/companies/client_form.html', company=company, client=client)


@bp.route('/companies/<int:company_id>/clients/<int:client_id>/update', methods=['POST'])
@login_required
@gestor_required
def clients_update(company_id, client_id):
    """Atualiza um cliente"""
    company = Company.query.get_or_404(company_id)
    client = User.query.get_or_404(client_id)

    # Verificar se o cliente pertence à empresa
    if client.company_id != company.id:
        return jsonify({'success': False, 'message': 'Cliente não pertence a esta empresa'}), 400

    data = request.get_json() if request.is_json else request.form

    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    is_active = data.get('is_active', 'true').lower() == 'true'

    # Validações
    if not username or not email:
        return jsonify({'success': False, 'message': 'Preencha todos os campos obrigatórios'}), 400

    # Verificar duplicatas (exceto o próprio cliente)
    if User.query.filter(User.username == username, User.id != client_id).first():
        return jsonify({'success': False, 'message': 'Nome de usuário já existe'}), 400

    if User.query.filter(User.email == email, User.id != client_id).first():
        return jsonify({'success': False, 'message': 'Email já cadastrado'}), 400

    # Atualizar cliente
    client.username = username
    client.email = email
    client.is_active = is_active

    # Atualizar senha se fornecida
    if password and len(password) >= 6:
        client.set_password(password)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Cliente atualizado com sucesso!',
        'client': client.to_dict(),
        'redirect': url_for('admin.companies_detail', company_id=company.id)
    })


@bp.route('/companies/<int:company_id>/clients/<int:client_id>/delete', methods=['POST'])
@login_required
@gestor_required
def clients_delete(company_id, client_id):
    """Desativa um cliente (soft delete)"""
    company = Company.query.get_or_404(company_id)
    client = User.query.get_or_404(client_id)

    # Verificar se o cliente pertence à empresa
    if client.company_id != company.id:
        return jsonify({'success': False, 'message': 'Cliente não pertence a esta empresa'}), 400

    client.is_active = False
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Cliente desativado com sucesso!',
        'redirect': url_for('admin.companies_detail', company_id=company.id)
    })
