// ============================================================================
// GERENCIAMENTO DE EMPRESAS
// ============================================================================

document.addEventListener('DOMContentLoaded', function() {
    // Inicializar funcionalidades da página
    initializeSearch();
    initializeFormValidation();
    initializeAnimations();
});

// ============================================================================
// BUSCA E FILTROS
// ============================================================================

function initializeSearch() {
    const searchInput = document.getElementById('searchInput');
    if (!searchInput) return;

    searchInput.addEventListener('input', function(e) {
        const searchTerm = e.target.value.toLowerCase();
        const rows = document.querySelectorAll('.table-row');

        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            if (text.includes(searchTerm)) {
                row.style.display = '';
                row.style.animation = 'fadeIn 0.3s ease';
            } else {
                row.style.display = 'none';
            }
        });
    });
}

// ============================================================================
// VALIDAÇÃO DE FORMULÁRIO
// ============================================================================

function initializeFormValidation() {
    const companyForm = document.getElementById('companyForm');
    if (!companyForm) return;

    companyForm.addEventListener('submit', handleCompanySubmit);

    // Máscara de CNPJ
    const cnpjInput = document.getElementById('cnpj');
    if (cnpjInput) {
        cnpjInput.addEventListener('input', function(e) {
            let value = e.target.value.replace(/\D/g, '');
            if (value.length <= 14) {
                value = value.replace(/^(\d{2})(\d)/, '$1.$2');
                value = value.replace(/^(\d{2})\.(\d{3})(\d)/, '$1.$2.$3');
                value = value.replace(/\.(\d{3})(\d)/, '.$1/$2');
                value = value.replace(/(\d{4})(\d)/, '$1-$2');
                e.target.value = value;
            }
        });
    }

    // Máscara de Telefone
    const phoneInput = document.getElementById('phone');
    if (phoneInput) {
        phoneInput.addEventListener('input', function(e) {
            let value = e.target.value.replace(/\D/g, '');
            if (value.length <= 11) {
                value = value.replace(/^(\d{2})(\d)/, '($1) $2');
                value = value.replace(/(\d{5})(\d)/, '$1-$2');
                e.target.value = value;
            }
        });
    }

    // Validação em tempo real
    const inputs = companyForm.querySelectorAll('input[required]');
    inputs.forEach(input => {
        input.addEventListener('blur', function() {
            validateField(this);
        });
    });
}

function validateField(field) {
    const value = field.value.trim();

    if (!value && field.hasAttribute('required')) {
        field.style.borderColor = '#ef4444';
        return false;
    } else {
        field.style.borderColor = '#10b981';
        return true;
    }
}

// ============================================================================
// SUBMIT DE FORMULÁRIO DE EMPRESA
// ============================================================================

async function handleCompanySubmit(e) {
    e.preventDefault();

    const form = e.target;
    const button = form.querySelector('.btn-primary');
    const errorMessage = document.getElementById('errorMessage');

    // Validar campos obrigatórios
    const nameInput = document.getElementById('name');
    if (!nameInput.value.trim()) {
        showError('Nome da empresa é obrigatório', errorMessage);
        nameInput.focus();
        return;
    }

    if (nameInput.value.trim().length < 3) {
        showError('Nome deve ter pelo menos 3 caracteres', errorMessage);
        nameInput.focus();
        return;
    }

    // Preparar dados
    const formData = {
        name: document.getElementById('name').value.trim(),
        cnpj: document.getElementById('cnpj').value.trim(),
        email: document.getElementById('email').value.trim(),
        phone: document.getElementById('phone').value.trim()
    };

    // Se estiver editando, incluir status
    const isActiveCheckbox = document.getElementById('is_active');
    if (isActiveCheckbox) {
        formData.is_active = isActiveCheckbox.checked;
    }

    // Determinar URL (criar ou atualizar)
    let url;
    if (typeof companyId !== 'undefined' && companyId) {
        url = `/admin/companies/${companyId}/update`;
    } else {
        url = '/admin/companies/create';
    }

    // Mostrar loading
    button.classList.add('loading');
    button.disabled = true;
    hideError(errorMessage);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (data.success) {
            // Animação de sucesso
            showSuccessAnimation(button);
            showNotification(data.message, 'success');

            setTimeout(() => {
                window.location.href = data.redirect;
            }, 800);
        } else {
            showError(data.message, errorMessage);
            button.classList.remove('loading');
            button.disabled = false;
        }
    } catch (error) {
        console.error('Erro:', error);
        showError('Erro ao processar requisição. Tente novamente.', errorMessage);
        button.classList.remove('loading');
        button.disabled = false;
    }
}

// ============================================================================
// DELETAR EMPRESA
// ============================================================================

async function deleteCompany(companyId, companyName) {
    // Confirmação com estilo
    const confirmed = await showConfirmDialog(
        'Desativar Empresa',
        `Tem certeza que deseja desativar a empresa "${companyName}"? Esta ação pode ser revertida posteriormente.`
    );

    if (!confirmed) return;

    showLoader();

    try {
        const response = await fetch(`/admin/companies/${companyId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        hideLoader();

        if (data.success) {
            showNotification(data.message, 'success');

            // Animar remoção da linha
            const row = document.querySelector(`tr[data-company-id="${companyId}"]`);
            if (row) {
                row.style.animation = 'fadeOut 0.3s ease';
                setTimeout(() => {
                    window.location.href = data.redirect;
                }, 300);
            } else {
                window.location.href = data.redirect;
            }
        } else {
            showNotification(data.message, 'error');
        }
    } catch (error) {
        hideLoader();
        console.error('Erro:', error);
        showNotification('Erro ao desativar empresa. Tente novamente.', 'error');
    }
}

// ============================================================================
// GERENCIAMENTO DE CLIENTES
// ============================================================================

function showAddClientModal() {
    const modal = document.getElementById('clientModal');
    const form = document.getElementById('clientForm');
    const modalTitle = document.getElementById('modalTitle');
    const submitText = document.getElementById('submitText');
    const passwordRequired = document.getElementById('passwordRequired');
    const passwordHelp = document.getElementById('passwordHelp');
    const isActiveGroup = document.getElementById('isActiveGroup');

    // Resetar formulário
    form.reset();
    document.getElementById('clientId').value = '';

    // Configurar modo de criação
    modalTitle.textContent = 'Adicionar Cliente';
    submitText.textContent = 'Adicionar Cliente';
    passwordRequired.style.display = 'inline';
    passwordHelp.style.display = 'none';
    isActiveGroup.style.display = 'none';
    document.getElementById('password').required = true;

    modal.classList.add('show');

    // Adicionar handler de submit
    form.removeEventListener('submit', handleClientSubmit);
    form.addEventListener('submit', handleClientSubmit);
}

function editClient(clientId) {
    // Buscar dados do cliente
    const clientItem = document.querySelector(`[data-client-id="${clientId}"]`);
    if (!clientItem) return;

    const modal = document.getElementById('clientModal');
    const form = document.getElementById('clientForm');
    const modalTitle = document.getElementById('modalTitle');
    const submitText = document.getElementById('submitText');
    const passwordRequired = document.getElementById('passwordRequired');
    const passwordHelp = document.getElementById('passwordHelp');
    const isActiveGroup = document.getElementById('isActiveGroup');

    // Buscar informações do cliente via API ou do DOM
    const username = clientItem.querySelector('.client-info strong').textContent;
    const email = clientItem.querySelector('.client-email').textContent;
    const isActive = clientItem.querySelector('.badge-success') !== null;

    // Preencher formulário
    document.getElementById('clientId').value = clientId;
    document.getElementById('username').value = username;
    document.getElementById('clientEmail').value = email;
    document.getElementById('clientIsActive').checked = isActive;
    document.getElementById('password').value = '';

    // Configurar modo de edição
    modalTitle.textContent = 'Editar Cliente';
    submitText.textContent = 'Salvar Alterações';
    passwordRequired.style.display = 'none';
    passwordHelp.style.display = 'block';
    isActiveGroup.style.display = 'block';
    document.getElementById('password').required = false;

    modal.classList.add('show');

    // Adicionar handler de submit
    form.removeEventListener('submit', handleClientSubmit);
    form.addEventListener('submit', handleClientSubmit);
}

function closeClientModal() {
    const modal = document.getElementById('clientModal');
    modal.classList.remove('show');
}

async function handleClientSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const button = form.querySelector('.btn-primary');
    const errorMessage = document.getElementById('modalErrorMessage');
    const clientId = document.getElementById('clientId').value;

    // Validar campos
    const username = document.getElementById('username').value.trim();
    const email = document.getElementById('clientEmail').value.trim();
    const password = document.getElementById('password').value;

    if (!username || !email) {
        showError('Preencha todos os campos obrigatórios', errorMessage);
        return;
    }

    if (username.length < 3) {
        showError('Nome de usuário deve ter pelo menos 3 caracteres', errorMessage);
        return;
    }

    // Se estiver criando, senha é obrigatória
    if (!clientId && !password) {
        showError('Senha é obrigatória', errorMessage);
        return;
    }

    if (password && password.length < 6) {
        showError('Senha deve ter pelo menos 6 caracteres', errorMessage);
        return;
    }

    // Preparar dados
    const formData = {
        username: username,
        email: email
    };

    if (password) {
        formData.password = password;
    }

    if (clientId) {
        formData.is_active = document.getElementById('clientIsActive').checked;
    }

    // Determinar URL
    let url;
    if (clientId) {
        url = `/admin/companies/${companyId}/clients/${clientId}/update`;
    } else {
        url = `/admin/companies/${companyId}/clients/create`;
    }

    // Mostrar loading
    button.classList.add('loading');
    button.disabled = true;
    hideError(errorMessage);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (data.success) {
            showSuccessAnimation(button);
            showNotification(data.message, 'success');

            setTimeout(() => {
                window.location.reload();
            }, 800);
        } else {
            showError(data.message, errorMessage);
            button.classList.remove('loading');
            button.disabled = false;
        }
    } catch (error) {
        console.error('Erro:', error);
        showError('Erro ao processar requisição. Tente novamente.', errorMessage);
        button.classList.remove('loading');
        button.disabled = false;
    }
}

async function deleteClient(clientId, clientName) {
    const confirmed = await showConfirmDialog(
        'Desativar Cliente',
        `Tem certeza que deseja desativar o cliente "${clientName}"?`
    );

    if (!confirmed) return;

    showLoader();

    try {
        const response = await fetch(`/admin/companies/${companyId}/clients/${clientId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        hideLoader();

        if (data.success) {
            showNotification(data.message, 'success');
            setTimeout(() => {
                window.location.reload();
            }, 500);
        } else {
            showNotification(data.message, 'error');
        }
    } catch (error) {
        hideLoader();
        console.error('Erro:', error);
        showNotification('Erro ao desativar cliente. Tente novamente.', 'error');
    }
}

// ============================================================================
// UTILITÁRIOS DE UI
// ============================================================================

function showError(message, element) {
    if (!element) return;

    element.textContent = message;
    element.classList.add('show');
    element.style.animation = 'shake 0.3s ease';

    // Vibração (se suportado)
    if (navigator.vibrate) {
        navigator.vibrate([100, 50, 100]);
    }
}

function hideError(element) {
    if (!element) return;
    element.classList.remove('show');
}

function showSuccessAnimation(button) {
    button.style.background = 'linear-gradient(135deg, #10b981, #059669)';

    // Criar confete
    createConfetti();
}

function createConfetti() {
    const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#10b981', '#4facfe'];
    const confettiCount = 30;

    for (let i = 0; i < confettiCount; i++) {
        const confetti = document.createElement('div');
        confetti.style.position = 'fixed';
        confetti.style.width = '10px';
        confetti.style.height = '10px';
        confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
        confetti.style.left = Math.random() * window.innerWidth + 'px';
        confetti.style.top = '-10px';
        confetti.style.borderRadius = '50%';
        confetti.style.pointerEvents = 'none';
        confetti.style.zIndex = '9999';
        confetti.style.opacity = '0';
        confetti.style.transition = 'all 2s ease-out';

        document.body.appendChild(confetti);

        setTimeout(() => {
            confetti.style.top = window.innerHeight + 'px';
            confetti.style.left = (parseFloat(confetti.style.left) + (Math.random() - 0.5) * 200) + 'px';
            confetti.style.opacity = '1';
            confetti.style.transform = 'rotate(' + (Math.random() * 360) + 'deg)';
        }, 10);

        setTimeout(() => {
            confetti.remove();
        }, 2000);
    }
}

async function showConfirmDialog(title, message) {
    return new Promise((resolve) => {
        const dialog = document.createElement('div');
        dialog.className = 'confirm-dialog';
        dialog.innerHTML = `
            <div class="confirm-content">
                <h3>${title}</h3>
                <p>${message}</p>
                <div class="confirm-actions">
                    <button class="btn btn-secondary" onclick="this.closest('.confirm-dialog').remove(); window.confirmResolve(false);">
                        Cancelar
                    </button>
                    <button class="btn btn-primary btn-danger" onclick="this.closest('.confirm-dialog').remove(); window.confirmResolve(true);">
                        Confirmar
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(dialog);

        // Armazenar resolve globalmente
        window.confirmResolve = resolve;

        // Adicionar estilo
        const style = document.createElement('style');
        style.textContent = `
            .confirm-dialog {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
                animation: fadeIn 0.2s ease;
            }
            .confirm-content {
                background: white;
                padding: 2rem;
                border-radius: 16px;
                max-width: 400px;
                width: 90%;
                animation: slideUp 0.3s ease;
            }
            .confirm-content h3 {
                margin: 0 0 1rem 0;
                font-size: 1.25rem;
            }
            .confirm-content p {
                margin: 0 0 1.5rem 0;
                color: var(--text-secondary);
            }
            .confirm-actions {
                display: flex;
                gap: 1rem;
                justify-content: flex-end;
            }
            .btn-danger {
                background: linear-gradient(135deg, #ef4444, #dc2626) !important;
            }
        `;
        document.head.appendChild(style);
    });
}

// ============================================================================
// ANIMAÇÕES
// ============================================================================

function initializeAnimations() {
    // Animar cards na entrada
    const cards = document.querySelectorAll('.stat-card, .table-container, .info-card, .clients-card');
    cards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';

        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });

    // Animar botões ao passar o mouse
    const buttons = document.querySelectorAll('.btn-action');
    buttons.forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            this.style.transform = 'scale(1.1)';
        });

        btn.addEventListener('mouseleave', function() {
            this.style.transform = 'scale(1)';
        });
    });
}

// Adicionar estilos de animação
const animationStyles = document.createElement('style');
animationStyles.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }

    @keyframes fadeOut {
        from { opacity: 1; }
        to { opacity: 0; }
    }

    @keyframes slideUp {
        from {
            transform: translateY(50px);
            opacity: 0;
        }
        to {
            transform: translateY(0);
            opacity: 1;
        }
    }

    @keyframes shake {
        0%, 100% { transform: translateX(0); }
        25% { transform: translateX(-10px); }
        75% { transform: translateX(10px); }
    }
`;
document.head.appendChild(animationStyles);
