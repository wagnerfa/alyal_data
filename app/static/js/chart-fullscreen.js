/**
 * Chart Fullscreen Functionality
 * Permite visualizar gráficos em tela cheia
 */

(function () {
    'use strict';

    // Estado do fullscreen
    let fullscreenState = {
        isOpen: false,
        originalCanvas: null,
        chartInstance: null,
        chartConfig: null
    };

    /**
     * Cria o modal de fullscreen
     */
    function createFullscreenModal() {
        if (document.getElementById('chart-fullscreen-modal')) {
            return;
        }

        const modal = document.createElement('div');
        modal.id = 'chart-fullscreen-modal';
        modal.className = 'chart-fullscreen-modal';
        modal.innerHTML = `
            <div class="chart-fullscreen-overlay"></div>
            <div class="chart-fullscreen-content">
                <div class="chart-fullscreen-header">
                    <h3 id="chart-fullscreen-title"></h3>
                    <button type="button" class="chart-fullscreen-close" aria-label="Fechar">
                        <span aria-hidden="true">×</span>
                    </button>
                </div>
                <div class="chart-fullscreen-body">
                    <canvas id="chart-fullscreen-canvas"></canvas>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Event listeners
        modal.querySelector('.chart-fullscreen-close').addEventListener('click', closeFullscreen);
        modal.querySelector('.chart-fullscreen-overlay').addEventListener('click', closeFullscreen);

        // ESC key to close
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && fullscreenState.isOpen) {
                closeFullscreen();
            }
        });
    }

    /**
     * Abre o gráfico em fullscreen
     */
    function openFullscreen(canvasId, title) {
        const originalCanvas = document.getElementById(canvasId);
        if (!originalCanvas) {
            console.error('Canvas não encontrado:', canvasId);
            return;
        }

        // Buscar a instância do Chart.js
        const chartInstance = Chart.getChart(originalCanvas);
        if (!chartInstance) {
            console.error('Instância do Chart.js não encontrada para:', canvasId);
            return;
        }

        createFullscreenModal();

        const modal = document.getElementById('chart-fullscreen-modal');
        const fullscreenCanvas = document.getElementById('chart-fullscreen-canvas');
        const titleElement = document.getElementById('chart-fullscreen-title');

        // Configurar título
        titleElement.textContent = title || 'Gráfico';

        // Salvar estado
        fullscreenState.isOpen = true;
        fullscreenState.originalCanvas = originalCanvas;

        // Criar novo gráfico no modal
        const ctx = fullscreenCanvas.getContext('2d');

        // Clonar configuração do gráfico de forma segura
        const originalConfig = chartInstance.config;
        const config = {
            type: originalConfig.type,
            data: {
                labels: originalConfig.data.labels ? [...originalConfig.data.labels] : [],
                datasets: originalConfig.data.datasets.map(dataset => ({
                    ...dataset,
                    data: dataset.data ? [...dataset.data] : []
                }))
            },
            options: {
                ...originalConfig.options,
                maintainAspectRatio: false,
                responsive: true
            }
        };

        fullscreenState.chartInstance = new Chart(ctx, config);

        // Mostrar modal
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    /**
     * Fecha o fullscreen
     */
    function closeFullscreen() {
        if (!fullscreenState.isOpen) return;

        const modal = document.getElementById('chart-fullscreen-modal');

        // Destruir gráfico fullscreen
        if (fullscreenState.chartInstance) {
            fullscreenState.chartInstance.destroy();
            fullscreenState.chartInstance = null;
        }

        // Esconder modal
        modal.classList.remove('active');
        document.body.style.overflow = '';

        // Limpar estado
        fullscreenState.isOpen = false;
        fullscreenState.originalCanvas = null;
        fullscreenState.chartConfig = null;
    }

    /**
     * Inicializa botões de fullscreen
     */
    function initFullscreenButtons() {
        document.querySelectorAll('[data-chart-fullscreen]').forEach(button => {
            button.addEventListener('click', function () {
                const canvasId = this.getAttribute('data-chart-canvas');
                const title = this.getAttribute('data-chart-title');
                openFullscreen(canvasId, title);
            });
        });
    }

    // Inicializar quando o DOM estiver pronto
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFullscreenButtons);
    } else {
        initFullscreenButtons();
    }

    // Expor funções globalmente se necessário
    window.ChartFullscreen = {
        open: openFullscreen,
        close: closeFullscreen,
        init: initFullscreenButtons
    };
})();
