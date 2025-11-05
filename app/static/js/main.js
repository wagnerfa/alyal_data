// Animações e interatividade

document.addEventListener('DOMContentLoaded', function() {

    // Tema claro/escuro
    const body = document.body;
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeToggleIcon');

    const applyTheme = (theme) => {
        const normalizedTheme = theme === 'dark' ? 'dark' : 'light';
        body.setAttribute('data-theme', normalizedTheme);
        if (themeToggle) {
            themeToggle.setAttribute('aria-pressed', normalizedTheme === 'dark');
            themeToggle.setAttribute('aria-label', normalizedTheme === 'dark' ? 'Ativar tema claro' : 'Ativar tema escuro');
        }
        if (themeIcon) {
            themeIcon.textContent = normalizedTheme === 'dark' ? '🌙' : '🌞';
        }
    };

    const storedTheme = localStorage.getItem('preferredTheme');
    applyTheme(storedTheme || 'light');

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = body.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
            const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
            applyTheme(nextTheme);
            localStorage.setItem('preferredTheme', nextTheme);
        });
    }

    // Auto-fechar alertas após 5 segundos
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.animation = 'slideDown 0.3s ease reverse';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
    
    // Validação de formulário de login
    const loginForm = document.querySelector('form');
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            const username = document.querySelector('input[name="username"]');
            const password = document.querySelector('input[name="password"]');
            
            if (!username.value.trim() || !password.value.trim()) {
                e.preventDefault();
                showAlert('Por favor, preencha todos os campos', 'error');
            }
        });
    }
    
    // Adicionar efeito de ripple nos botões
    const buttons = document.querySelectorAll('.btn');
    buttons.forEach(button => {
        button.addEventListener('click', function(e) {
            const ripple = document.createElement('span');
            const rect = button.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            ripple.classList.add('ripple');
            
            button.appendChild(ripple);
            
            setTimeout(() => ripple.remove(), 600);
        });
    });
    
    // Animação de entrada dos cards do dashboard
    const dashboardCards = document.querySelectorAll('.dashboard-card');
    dashboardCards.forEach((card, index) => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, index * 100);
    });
    
    // Contador animado para estatísticas
    const animateCounter = (element, target) => {
        let current = 0;
        const increment = target / 50;
        const timer = setInterval(() => {
            current += increment;
            if (current >= target) {
                element.textContent = target;
                clearInterval(timer);
            } else {
                element.textContent = Math.floor(current);
            }
        }, 20);
    };
    
    const counters = document.querySelectorAll('.counter');
    counters.forEach(counter => {
        const target = parseInt(counter.getAttribute('data-target'));
        animateCounter(counter, target);
    });
    
    // Filtro de busca na tabela (para dashboard do gestor)
    const searchInput = document.querySelector('#userSearch');
    if (searchInput) {
        searchInput.addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const tableRows = document.querySelectorAll('tbody tr');
            
            tableRows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(searchTerm) ? '' : 'none';
            });
        });
    }
    
    // Confirmação de logout
    const logoutBtn = document.querySelector('.btn-logout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function(e) {
            if (!confirm('Tem certeza que deseja sair?')) {
                e.preventDefault();
            }
        });
    }
    
});

// Função auxiliar para mostrar alertas
function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    
    const form = document.querySelector('form');
    form.parentNode.insertBefore(alertDiv, form);
    
    setTimeout(() => {
        alertDiv.style.animation = 'slideDown 0.3s ease reverse';
        setTimeout(() => alertDiv.remove(), 300);
    }, 5000);
}

// CSS adicional para o efeito ripple
const style = document.createElement('style');
style.textContent = `
    .btn {
        position: relative;
        overflow: hidden;
    }
    
    .ripple {
        position: absolute;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: scale(0);
        animation: rippleEffect 0.6s ease-out;
        pointer-events: none;
    }
    
    @keyframes rippleEffect {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);
