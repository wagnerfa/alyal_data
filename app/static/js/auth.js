document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');

    if (loginForm) {
        loginForm.addEventListener('submit', handleLogin);
    }

    if (registerForm) {
        registerForm.addEventListener('submit', handleRegister);
    }

    // Adicionar animação de foco nos inputs
    const inputs = document.querySelectorAll('input');
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.parentElement.style.transform = 'scale(1.02)';
        });

        input.addEventListener('blur', function() {
            this.parentElement.style.transform = 'scale(1)';
        });
    });
});

async function handleLogin(e) {
    e.preventDefault();

    const form = e.target;
    const button = form.querySelector('.btn-primary');
    const errorMessage = document.getElementById('errorMessage');

    const formData = {
        email: form.email.value,
        password: form.password.value,
        remember: form.remember.checked
    };

    // Mostrar loading
    button.classList.add('loading');
    hideError();

    try {
        const response = await fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (data.success) {
            // Animação de sucesso
            showSuccess();
            setTimeout(() => {
                window.location.href = data.redirect;
            }, 800);
        } else {
            showError(data.message);
            button.classList.remove('loading');
        }
    } catch (error) {
        showError('Erro ao fazer login. Tente novamente.');
        button.classList.remove('loading');
    }
}

async function handleRegister(e) {
    e.preventDefault();

    const form = e.target;
    const button = form.querySelector('.btn-primary');

    const formData = {
        username: form.username.value,
        email: form.email.value,
        password: form.password.value,
        confirm_password: form.confirm_password.value
    };

    // Mostrar loading
    button.classList.add('loading');
    hideError();

    try {
        const response = await fetch('/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(formData)
        });

        const data = await response.json();

        if (data.success) {
            // Animação de sucesso
            showSuccess();
            setTimeout(() => {
                window.location.href = data.redirect;
            }, 800);
        } else {
            showError(data.message);
            button.classList.remove('loading');
        }
    } catch (error) {
        showError('Erro ao criar conta. Tente novamente.');
        button.classList.remove('loading');
    }
}

function showError(message) {
    const errorElement = document.getElementById('errorMessage');
    errorElement.textContent = message;
    errorElement.classList.add('show');

    // Adicionar vibração (se suportado)
    if (navigator.vibrate) {
        navigator.vibrate([100, 50, 100]);
    }
}

function hideError() {
    const errorElement = document.getElementById('errorMessage');
    errorElement.classList.remove('show');
}

function showSuccess() {
    const button = document.querySelector('.btn-primary');
    button.style.background = 'linear-gradient(135deg, #10b981, #059669)';

    // Criar efeito de confete (simplificado)
    createConfetti();
}

function createConfetti() {
    const colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c'];
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

// Animação de digitação no placeholder
function animatePlaceholder(input, text) {
    let index = 0;
    const speed = 100;

    function type() {
        if (index < text.length) {
            input.placeholder += text.charAt(index);
            index++;
            setTimeout(type, speed);
        }
    }

    input.placeholder = '';
    type();
}