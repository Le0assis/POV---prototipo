/**
 * Lógica principal da página routes.html
 * Lista de rotas, criação, modo teste com bússola
 */

import { insertTopNav } from '/static/js/nav.js';
import { Compass } from '/static/js/compass.js';

const API_BASE_URL = (() => {
    const isLocalhost = window.location.hostname === 'localhost' ||
                        window.location.hostname === '127.0.0.1' ||
                        window.location.hostname === '[::1]';
    return isLocalhost ? 'http://127.0.0.1:8000' : 'https://api.pov-unimar.com';
})();

// Estado global
let allRoutes = [];
let allNodes = [];
let currentTestRoute = null;
let testCompass = null;
let testPollingInterval = null;

// Inicialização
document.addEventListener('DOMContentLoaded', async () => {
    insertTopNav('routes');
    await loadNodes();
    await loadRoutes();
    setupEventListeners();
    restoreStartPoint();
});

async function loadNodes() {
    try {
        const res = await fetch(`${API_BASE_URL}/api/map`);
        const data = await res.json();
        if (data.status === 'success' && Array.isArray(data.nodes)) {
            allNodes = data.nodes;
            populateNodeSelects();
        }
    } catch (err) {
        console.error('Erro ao carregar nós:', err);
    }
}

function populateNodeSelects() {
    const selects = [
        'start-point-select',
        'new-route-start',
        'new-route-end'
    ];

    selects.forEach(selectId => {
        const select = document.getElementById(selectId);
        if (!select) return;

        const currentValue = select.value;
        select.innerHTML = '<option value="">-- Selecione --</option>';

        allNodes.forEach(n => {
            select.innerHTML += `<option value="${n.id}">${n.label}</option>`;
        });

        // Restaurar valor se ainda válido
        if (currentValue && allNodes.some(n => n.id === currentValue)) {
            select.value = currentValue;
        }
    });
}

async function loadRoutes() {
    try {
        const res = await fetch(`${API_BASE_URL}/api/routes`);
        const data = await res.json();
        if (data.status === 'success') {
            allRoutes = data.routes || [];
            renderRoutesList();
        }
    } catch (err) {
        console.error('Erro ao carregar rotas:', err);
    }
}

function renderRoutesList() {
    const container = document.getElementById('routes-list');
    if (!container) return;

    if (allRoutes.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>Nenhuma rota salva ainda.</p>
                <button class="btn-primary" onclick="openNewRouteModal()">+ Criar Primeira Rota</button>
            </div>
        `;
        return;
    }

    container.innerHTML = allRoutes.map(route => `
        <div class="route-card" data-id="${route.id}">
            <div class="route-header">
                <h3>${escapeHtml(route.name)}</h3>
                <span class="route-id">#${route.id}</span>
            </div>
            <div class="route-details">
                <div class="route-path">
                    <span class="route-node start">${escapeHtml(route.start_node)}</span>
                    <span class="route-arrow">→</span>
                    <span class="route-node end">${escapeHtml(route.end_node)}</span>
                </div>
                <div class="route-meta">
                    <span class="meta-item">
                        <span class="meta-icon">📏</span>
                        <span>${route.total_distance_m.toFixed(1)}m</span>
                    </span>
                    <span class="meta-item">
                        <span class="meta-icon">👣</span>
                        <span>${route.total_steps_estimated} passos</span>
                    </span>
                </div>
            </div>
            <div class="route-actions">
                <button class="btn-test" onclick="enterTestMode(${route.id})">🧪 Testar</button>
                <button class="btn-delete" onclick="deleteRoute(${route.id})">🗑️ Excluir</button>
            </div>
        </div>
    `).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function setupEventListeners() {
    // Seletor de ponto de partida
    const startSelect = document.getElementById('start-point-select');
    if (startSelect) {
        startSelect.addEventListener('change', (e) => {
            localStorage.setItem('pov_start_point', e.target.value);
            updateStartPointHint(e.target.value);
        });
    }

    // Botão nova rota
    const btnNewRoute = document.getElementById('btn-new-route');
    if (btnNewRoute) {
        btnNewRoute.addEventListener('click', openNewRouteModal);
    }

    // Modal
    const modal = document.getElementById('modal-new-route');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }

    // Botão sair do teste
    const btnExitTest = document.getElementById('btn-exit-test');
    if (btnExitTest) {
        btnExitTest.addEventListener('click', exitTestMode);
    }
}

function restoreStartPoint() {
    const saved = localStorage.getItem('pov_start_point');
    const select = document.getElementById('start-point-select');
    if (saved && select) {
        select.value = saved;
        updateStartPointHint(saved);
    }
}

function updateStartPointHint(nodeId) {
    const hint = document.getElementById('start-point-hint');
    if (!hint) return;

    const node = allNodes.find(n => n.id === nodeId);
    if (node) {
        hint.textContent = `Partida definida: ${node.label}`;
        hint.style.color = '#22c55e';
    } else {
        hint.textContent = 'Usado como origem ao criar/testar rotas';
        hint.style.color = '#94a3b8';
    }
}

function openNewRouteModal() {
    const modal = document.getElementById('modal-new-route');
    if (modal) {
        modal.classList.remove('hidden');
        // Pré-selecionar ponto de partida salvo
        const savedStart = localStorage.getItem('pov_start_point');
        const startSelect = document.getElementById('new-route-start');
        if (savedStart && startSelect) {
            startSelect.value = savedStart;
        }
    }
}

window.closeModal = function() {
    const modal = document.getElementById('modal-new-route');
    if (modal) {
        modal.classList.add('hidden');
        document.getElementById('new-route-name').value = '';
    }
}

window.createRoute = async function() {
    const start = document.getElementById('new-route-start').value;
    const end = document.getElementById('new-route-end').value;
    const name = document.getElementById('new-route-name').value.trim();

    if (!start || !end) {
        alert('Selecione origem e destino.');
        return;
    }
    if (start === end) {
        alert('Origem e destino devem ser diferentes.');
        return;
    }

    try {
        const res = await fetch(`${API_BASE_URL}/api/routes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_node: start, end_node: end, name: name || null })
        });

        const data = await res.json();
        if (data.status === 'success') {
            alert(`Rota "${data.route.name}" salva com sucesso!`);
            closeModal();
            await loadRoutes();
        } else {
            alert(`Erro: ${data.detail || 'Falha ao criar rota'}`);
        }
    } catch (err) {
        console.error('Erro ao criar rota:', err);
        alert('Erro de conexão ao criar rota.');
    }
}

window.deleteRoute = async function(routeId) {
    if (!confirm('Tem certeza que deseja excluir esta rota?')) return;

    try {
        const res = await fetch(`${API_BASE_URL}/api/routes/${routeId}`, {
            method: 'DELETE'
        });

        const data = await res.json();
        if (data.status === 'success') {
            await loadRoutes();
        } else {
            alert('Erro ao excluir rota.');
        }
    } catch (err) {
        console.error('Erro ao excluir rota:', err);
        alert('Erro de conexão.');
    }
}

window.enterTestMode = async function(routeId) {
    // Verificar ponto de partida
    const startPoint = document.getElementById('start-point-select').value;
    if (!startPoint) {
        alert('Selecione seu ponto de partida atual no seletor acima.');
        return;
    }

    try {
        // Resetar PDR com ponto de partida selecionado
        await fetch(`${API_BASE_URL}/api/reset`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ start_node: startPoint })
        });

        // Carregar rota completa
        const res = await fetch(`${API_BASE_URL}/api/routes/${routeId}`);
        const data = await res.json();

        if (data.status !== 'success' || !data.route) {
            alert('Erro ao carregar rota para teste.');
            return;
        }

        currentTestRoute = data.route;
        startTestMode(currentTestRoute);

    } catch (err) {
        console.error('Erro ao entrar no modo teste:', err);
        alert('Erro ao iniciar teste.');
    }
}

function startTestMode(route) {
    // Mostrar overlay
    const overlay = document.getElementById('test-mode-overlay');
    if (overlay) {
        overlay.classList.remove('hidden');
    }

    // Atualizar header
    document.getElementById('test-route-name').textContent = `Rota: ${route.name}`;

    // Configurar estatísticas totais
    document.getElementById('test-steps-total').textContent = route.total_steps_estimated;
    document.getElementById('test-dist-total').textContent = route.total_distance_m.toFixed(1);

    // Inicializar bússola
    testCompass = new Compass('test-compass', {
        onSegmentChange: (currentIndex, total) => {
            updateTestSegmentInfo(currentIndex, total, route);
        },
        onDestinationReached: () => {
            onTestDestinationReached();
        },
        onProgressUpdate: (info) => {
            // Atualizar UI de progresso se necessário
        }
    });

    testCompass.setRoute(route.segments);

    // Iniciar polling de localização
    startLocationPolling(route);
}

function updateTestSegmentInfo(currentIndex, total, route) {
    if (currentIndex >= route.segments.length) return;

    const segment = route.segments[currentIndex];
    document.getElementById('test-current-segment').textContent = `${segment.source} → ${segment.target}`;
    document.getElementById('test-segment-distance').textContent = `Distância: ${segment.distance_m.toFixed(1)}m`;

    // Atualizar progresso total (segmentos completos + atual)
    const completedSegments = currentIndex;
    const totalSegments = route.segments.length;
    const progressPercent = (completedSegments / totalSegments) * 100;
    document.getElementById('test-progress-fill').style.width = `${progressPercent}%`;
}

function onTestDestinationReached() {
    document.getElementById('test-direction-label').textContent = '🎯 Chegou ao destino!';
    document.getElementById('test-progress-fill').style.width = '100%';

    setTimeout(() => {
        if (confirm('Destino alcançado! Deseja finalizar o teste?')) {
            exitTestMode();
        }
    }, 1000);
}

function startLocationPolling(route) {
    // Parar polling anterior se houver
    if (testPollingInterval) {
        clearInterval(testPollingInterval);
    }

    let lastNode = null;

    testPollingInterval = setInterval(async () => {
        try {
            const res = await fetch(`${API_BASE_URL}/api/current_location`);
            const data = await res.json();

            const currentNode = data.current_node;
            const accumulatedDist = data.accumulated_distance_m || 0;
            const visitedPath = data.visited_path || [];

            // Atualizar bússola
            if (testCompass) {
                testCompass.update(currentNode);
            }

            // Atualizar status PDR
            const pdrStatus = document.getElementById('test-pdr-status');
            if (pdrStatus) {
                pdrStatus.textContent = `👣 PDR: ${currentNode || 'Aguardando...'} (${accumulatedDist.toFixed(1)}m)`;
            }

            // Atualizar contadores de passos/distância
            updateTestCounters(route, accumulatedDist, visitedPath);

            // Detectar mudança de nó para feedback visual
            if (lastNode && currentNode && currentNode !== lastNode) {
                console.log(`Mudança de nó: ${lastNode} → ${currentNode}`);
            }
            lastNode = currentNode;

        } catch (err) {
            console.error('Erro no polling:', err);
        }
    }, 500);
}

function updateTestCounters(route, accumulatedDist, visitedPath) {
    // Calcular passos estimados percorridos
    const avgStepLength = 0.75;
    const stepsWalked = Math.round(accumulatedDist / avgStepLength);
    const totalSteps = route.total_steps_estimated;

    document.getElementById('test-steps-count').textContent = Math.min(stepsWalked, totalSteps);
    document.getElementById('test-dist-current').textContent = accumulatedDist.toFixed(1);

    // Progresso baseado na distância acumulada total da rota
    // Nota: accumulatedDist zera a cada nó, então somamos segmentos completos
    let totalWalked = 0;
    for (let i = 0; i < route.segments.length; i++) {
        if (i < testCompass.currentSegmentIndex) {
            totalWalked += route.segments[i].distance_m;
        } else if (i === testCompass.currentSegmentIndex) {
            totalWalked += accumulatedDist;
        }
    }

    const progressPercent = Math.min(100, (totalWalked / route.total_distance_m) * 100);
    document.getElementById('test-progress-fill').style.width = `${progressPercent}%`;
}

function exitTestMode() {
    // Parar polling
    if (testPollingInterval) {
        clearInterval(testPollingInterval);
        testPollingInterval = null;
    }

    // Esconder overlay
    const overlay = document.getElementById('test-mode-overlay');
    if (overlay) {
        overlay.classList.add('hidden');
    }

    // Resetar estado
    currentTestRoute = null;
    testCompass = null;

    // Resetar PDR para estado padrão
    fetch(`${API_BASE_URL}/api/reset`, { method: 'POST' }).catch(() => {});
}