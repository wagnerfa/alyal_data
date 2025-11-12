/**
 * Analytics.js - Advanced Chart Functions and Utilities
 * =====================================================
 */

// Configurações globais Chart.js
if (window.Chart) {
    Chart.defaults.font.family = "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif";
    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(31, 35, 54, 0.95)';
    Chart.defaults.plugins.tooltip.padding = 14;
    Chart.defaults.plugins.tooltip.cornerRadius = 10;
    Chart.defaults.plugins.tooltip.titleFont = { size: 13, weight: '600' };
    Chart.defaults.plugins.tooltip.bodyFont = { size: 12 };
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.padding = 16;
}

// Paleta de cores do tema
const THEME_COLORS = {
    primary: '#F2BBC9',
    secondary: '#AFA9D9',
    accent: '#8082A6',
    warning: '#F2A172',
    dark: '#282E40',
    success: '#34BFA3',
    danger: '#E74A3B',
    info: '#5B9BD5',
    purple: '#8082A6',
    yellow: '#F6C23E',
    orange: '#ED7D31',
};

// Paleta estendida para gráficos
const CHART_PALETTE = [
    '#8082A6', '#34BFA3', '#5B9BD5', '#F6C23E', '#F2A172',
    '#AFA9D9', '#ED7D31', '#F2BBC9', '#36A2EB', '#F9A8D4'
];

/**
 * Criar gradiente vertical para área de gráficos
 */
function createVerticalGradient(ctx, color1, color2, height = 400) {
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, color1);
    gradient.addColorStop(1, color2);
    return gradient;
}

/**
 * Criar gradiente horizontal para gráficos de barras
 */
function createHorizontalGradient(ctx, color1, color2, width = 600) {
    const gradient = ctx.createLinearGradient(0, 0, width, 0);
    gradient.addColorStop(0, color1);
    gradient.addColorStop(1, color2);
    return gradient;
}

/**
 * Formatar valor em moeda brasileira
 */
function formatBRL(value) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(value);
}

/**
 * Formatar número com separadores
 */
function formatNumber(value, decimals = 0) {
    return new Intl.NumberFormat('pt-BR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(value);
}

/**
 * Formatar percentual
 */
function formatPercent(value, decimals = 1) {
    return `${formatNumber(value, decimals)}%`;
}

/**
 * Exportar gráfico como PNG
 */
function exportChart(chartId, filename = null) {
    const canvas = document.getElementById(chartId);
    if (!canvas) {
        console.error(`Chart ${chartId} not found`);
        return;
    }

    const url = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.download = filename || `${chartId}-${new Date().toISOString().split('T')[0]}.png`;
    link.href = url;
    link.click();
}

/**
 * Exportar dados do gráfico como CSV
 */
function exportChartData(chartInstance, filename = null) {
    if (!chartInstance || !chartInstance.data) {
        console.error('Invalid chart instance');
        return;
    }

    const { labels, datasets } = chartInstance.data;
    let csv = 'Rótulo';

    // Cabeçalhos
    datasets.forEach(dataset => {
        csv += `,${dataset.label || 'Valor'}`;
    });
    csv += '\n';

    // Dados
    labels.forEach((label, index) => {
        csv += `${label}`;
        datasets.forEach(dataset => {
            csv += `,${dataset.data[index] || 0}`;
        });
        csv += '\n';
    });

    // Download
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename || `dados-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
}

/**
 * Configurações padrão para gráficos responsivos
 */
const RESPONSIVE_OPTIONS = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
        mode: 'index',
        intersect: false,
    },
    plugins: {
        legend: {
            display: true,
            position: 'bottom',
            labels: {
                padding: 15,
                usePointStyle: true,
                font: {
                    size: 12,
                    weight: '600'
                }
            }
        },
        tooltip: {
            backgroundColor: 'rgba(31, 35, 54, 0.95)',
            titleColor: '#fff',
            bodyColor: '#f0f0f0',
            padding: 12,
            cornerRadius: 8,
            displayColors: true,
        }
    },
    animation: {
        duration: 750,
        easing: 'easeInOutQuart'
    }
};

/**
 * Criar heatmap de cohort com cores dinâmicas
 */
function createCohortHeatmap(matrixData, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const { cohort_labels, period_labels, retention_matrix, cohort_sizes } = matrixData;

    let html = '<div class="cohort-heatmap"><table class="cohort-table">';

    // Cabeçalho
    html += '<thead><tr><th>Cohort</th><th>Tamanho</th>';
    period_labels.forEach(period => {
        html += `<th>${period}</th>`;
    });
    html += '</tr></thead><tbody>';

    // Linhas de dados
    retention_matrix.forEach((row, i) => {
        html += `<tr><td><strong>${cohort_labels[i]}</strong></td>`;
        html += `<td>${cohort_sizes[i]}</td>`;

        row.forEach(value => {
            const intensity = value / 100;
            const bgColor = value > 0
                ? `rgba(52, 191, 163, ${intensity * 0.8})`
                : 'transparent';
            const textColor = value >= 50 ? '#fff' : 'var(--text-primary)';
            const fontWeight = value >= 80 ? '700' : '400';

            html += `<td class="cohort-cell" style="background: ${bgColor}; color: ${textColor}; font-weight: ${fontWeight}">`;
            html += value > 0 ? `${formatNumber(value, 1)}%` : '—';
            html += '</td>';
        });

        html += '</tr>';
    });

    html += '</tbody></table></div>';
    container.innerHTML = html;
}

/**
 * Aplicar badge colorido baseado em segmento RFM
 */
function getRFMBadgeClass(segment) {
    const classMap = {
        'Champions': 'champions',
        'Loyal Customers': 'loyal',
        'Potential Loyalists': 'potential',
        'New Customers': 'new',
        'At Risk': 'at-risk',
        'Cannot Lose Them': 'critical',
        'Lost': 'lost',
        'Others': 'others'
    };
    return classMap[segment] || 'others';
}

/**
 * Obter cor baseada no tema (claro/escuro)
 */
function getThemedColor(variable) {
    const styles = getComputedStyle(document.documentElement);
    return (styles.getPropertyValue(variable) || '#2c3e50').trim();
}

/**
 * Mostrar loading state em um chart
 */
function showChartLoading(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = getThemedColor('--text-muted');
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Carregando dados...', width / 2, height / 2);
}

/**
 * Mostrar empty state em um chart
 */
function showChartEmpty(canvasId, message = 'Nenhum dado disponível') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = getThemedColor('--text-muted');
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(message, width / 2, height / 2);
}

/**
 * Animar counter para métricas
 */
function animateCounter(element, targetValue, duration = 1000, formatter = null) {
    const start = 0;
    const increment = targetValue / (duration / 16);
    let current = start;

    const timer = setInterval(() => {
        current += increment;
        if (current >= targetValue) {
            current = targetValue;
            clearInterval(timer);
        }
        element.textContent = formatter ? formatter(current) : Math.round(current);
    }, 16);
}

/**
 * Criar skeleton loader para cards
 */
function createSkeletonLoader(count = 4) {
    let html = '';
    for (let i = 0; i < count; i++) {
        html += `
            <div class="skeleton-card">
                <div class="skeleton-header"></div>
                <div class="skeleton-body"></div>
                <div class="skeleton-footer"></div>
            </div>
        `;
    }
    return html;
}

// Exportar funções globalmente
window.ChartUtils = {
    createVerticalGradient,
    createHorizontalGradient,
    formatBRL,
    formatNumber,
    formatPercent,
    exportChart,
    exportChartData,
    createCohortHeatmap,
    getRFMBadgeClass,
    getThemedColor,
    showChartLoading,
    showChartEmpty,
    animateCounter,
    createSkeletonLoader,
    THEME_COLORS,
    CHART_PALETTE,
    RESPONSIVE_OPTIONS
};
