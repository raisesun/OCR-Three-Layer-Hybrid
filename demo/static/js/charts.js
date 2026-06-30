/**
 * OCR演示 - Chart.js图表渲染
 */

// 图表颜色方案
const COLORS = {
    primary: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1', '#14b8a6'],
    success: '#10b981',
    danger: '#ef4444',
    warning: '#f59e0b',
    info: '#3b82f6',
};

// 文档类型到颜色的映射
const TYPE_COLORS = {
    '身份证': '#3b82f6',
    '户口本': '#10b981',
    '结婚证': '#ec4899',
    '离婚证': '#f472b6',
    '不动产权证书': '#8b5cf6',
    '发票': '#f59e0b',
    '购房合同': '#ef4444',
    '存量房合同': '#f97316',
    '资金监管协议': '#06b6d4',
    '离婚协议': '#14b8a6',
    '未知': '#6b7280',
};

// 存储图表实例以便销毁
let chartInstances = {};

function destroyChart(id) {
    if (chartInstances[id]) {
        chartInstances[id].destroy();
        delete chartInstances[id];
    }
}

/**
 * 渲染基线对比图表
 */
function renderCompareCharts() {
    const app = document.querySelector('[x-data]').__x;
    if (!app) return;
    const data = app.$data.compareResult;
    if (!data) return;

    const typeAccuracy = data.type_accuracy || {};
    const labels = Object.keys(typeAccuracy);
    const accuracies = labels.map(l => typeAccuracy[l].accuracy);
    const colors = labels.map(l => TYPE_COLORS[l] || '#6b7280');

    // 准确率条形图
    destroyChart('compareAccuracyChart');
    const ctx = document.getElementById('compareAccuracyChart');
    if (ctx) {
        chartInstances['compareAccuracyChart'] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: '准确率 (%)',
                    data: accuracies,
                    backgroundColor: colors.map(c => c + '33'),
                    borderColor: colors,
                    borderWidth: 2,
                    borderRadius: 6,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: { callback: v => v + '%' },
                    },
                    x: {
                        ticks: { font: { size: 11 } },
                    }
                }
            }
        });
    }
}

/**
 * 渲染统计面板图表
 */
function renderDashboardCharts() {
    const app = document.querySelector('[x-data]').__x;
    if (!app) return;
    const data = app.$data.dashboardData;
    if (!data) return;

    // 1. 文档类型分布饼图
    destroyChart('typeDistChart');
    const typeCtx = document.getElementById('typeDistChart');
    if (typeCtx) {
        const typeDist = data.type_distribution || {};
        const typeLabels = Object.keys(typeDist);
        const typeValues = Object.values(typeDist);
        const typeColors = typeLabels.map(l => TYPE_COLORS[l] || '#6b7280');

        chartInstances['typeDistChart'] = new Chart(typeCtx, {
            type: 'doughnut',
            data: {
                labels: typeLabels,
                datasets: [{
                    data: typeValues,
                    backgroundColor: typeColors,
                    borderWidth: 2,
                    borderColor: '#fff',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { font: { size: 11 }, padding: 12 },
                    },
                },
            }
        });
    }

    // 2. 处理层使用比例环形图
    destroyChart('layerDistChart');
    const layerCtx = document.getElementById('layerDistChart');
    if (layerCtx) {
        const layerDist = data.layer_distribution || {};
        const layerLabels = Object.keys(layerDist);
        const layerValues = Object.values(layerDist);
        const layerColors = {
            'rule': '#10b981',
            'vlm': '#3b82f6',
            'llm': '#8b5cf6',
        };

        chartInstances['layerDistChart'] = new Chart(layerCtx, {
            type: 'doughnut',
            data: {
                labels: layerLabels.map(l => l.toUpperCase()),
                datasets: [{
                    data: layerValues,
                    backgroundColor: layerLabels.map(l => layerColors[l] || '#6b7280'),
                    borderWidth: 2,
                    borderColor: '#fff',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: { font: { size: 12 }, padding: 15 },
                    },
                },
            }
        });
    }

    // 3. 处理耗时分布直方图
    destroyChart('timingDistChart');
    const timingCtx = document.getElementById('timingDistChart');
    if (timingCtx) {
        const timingDist = data.timing_distribution || {};
        const timingLabels = Object.keys(timingDist);
        const timingValues = Object.values(timingDist);

        chartInstances['timingDistChart'] = new Chart(timingCtx, {
            type: 'bar',
            data: {
                labels: timingLabels,
                datasets: [{
                    label: '图片数量',
                    data: timingValues,
                    backgroundColor: '#3b82f633',
                    borderColor: '#3b82f6',
                    borderWidth: 2,
                    borderRadius: 6,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 10 },
                    }
                }
            }
        });
    }
}
