/**
 * panel.js — AgentOffice Side Panel Manager
 * Controls the dual-mode interaction panel (Chat | Logs | Files tabs).
 * Supports:
 *   1. General Project Mode (when no agent is selected)
 *   2. Agent-Specific Mode (when an agent is selected)
 * @module panel
 */

import API from './api.js';
import { AGENTS } from './office.js';

// ── State ─────────────────────────────────────────────────────────────────

/**
 * @typedef {{
 *   id: string, name: string, fullName: string,
 *   icon: string, color: string, description: string
 * }} AgentDef
 */

/** @type {AgentDef|null} Active agent, or null for General Project Mode */
let _currentAgent = null;

/** @type {string|null} */
let _currentProjectId = null;

/** @type {Record<string, string>} Cache session UUID per agent ID. */
const _agentSessions = {};

/** @param {string} agentId @returns {string} */
function _getSessionId(agentId) {
  if (!_agentSessions[agentId]) {
    _agentSessions[agentId] = crypto.randomUUID();
  }
  return _agentSessions[agentId];
}

/** @type {string} Current active session ID. */
let _sessionId = crypto.randomUUID();

/** @type {string} */
let _activeTab = 'files';

/** Cache for workspace files to enable fast instant filtering without refetching */
let _cachedWorkspaceFiles = [];
let _cachedDeliverables = {};
let _filesFilterText = '';

// ── DOM helpers ───────────────────────────────────────────────────────────

/** @param {string} id @returns {HTMLElement|null} */
const $id = (id) => document.getElementById(id);

/**
 * Get effective active project ID from local state, global window, or dropdown.
 * @returns {string|null}
 */
function _getEffectiveProjectId() {
  if (_currentProjectId) return _currentProjectId;
  if (typeof window !== 'undefined' && window._activeProjectId) return window._activeProjectId;
  const select = /** @type {HTMLSelectElement|null} */ ($id('project-select'));
  if (select && select.value) return select.value;
  return null;
}

// ── Helpers ───────────────────────────────────────────────────────────────

/** @param {string} s @returns {string} */
function _esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** @param {string} s @param {number} max @returns {string} */
function _truncate(s, max) {
  const str = String(s ?? '');
  return str.length > max ? `${str.slice(0, max)}\u2026` : str;
}

/**
 * Minimal markdown-to-safe-HTML for agent responses.
 * @param {string} text @returns {string}
 */
function _md(text) {
  return _esc(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`\n]+)`/g,   '<code>$1</code>')
    .replace(/^#{1,3}\s+(.+)$/gm, '<span class="md-heading">$1</span>')
    .replace(/\n/g, '<br>');
}

/** @param {HTMLElement} el @param {string} icon @param {string} text @param {string} [hint=''] */
function _setPlaceholder(el, icon, text, hint = '') {
  el.innerHTML = `
    <div class="chat-placeholder">
      <div class="placeholder-icon">${icon}</div>
      <div>${_esc(text)}</div>
      ${hint ? `<div class="placeholder-hint">${_esc(hint)}</div>` : ''}
    </div>`;
}

/**
 * Return file type icon based on extension or path.
 * @param {string} path
 * @returns {string}
 */
function _getFileIcon(path) {
  const lower = (path || '').toLowerCase();
  if (lower.endsWith('.php')) return '🐘';
  if (lower.endsWith('.py')) return '⚡';
  if (lower.endsWith('.js') || lower.endsWith('.ts')) return '🟨';
  if (lower.endsWith('.html') || lower.endsWith('.css')) return '🎨';
  if (lower.endsWith('.json') || lower.endsWith('.yml') || lower.endsWith('.yaml') || lower.includes('.env')) return '⚙️';
  if (lower.endsWith('.md') || lower.endsWith('.txt')) return '📝';
  if (lower.includes('docker') || lower.endsWith('dockerfile')) return '🐳';
  return '📄';
}

/**
 * Automatically determine the most qualified agent to edit a given file.
 * @param {string} filePath
 * @returns {AgentDef|null}
 */
function _detectBestAgentForFile(filePath) {
  if (!filePath) return AGENTS[0] || null;
  const lower = filePath.toLowerCase();
  if (lower.endsWith('.php') || lower.includes('laravel')) {
    return AGENTS.find((a) => a.id === 'agente_03_laravel') || AGENTS[0];
  }
  if (lower.endsWith('.py') || lower.includes('fastapi')) {
    return AGENTS.find((a) => a.id === 'agente_04_fastapi') || AGENTS[0];
  }
  if (lower.endsWith('.html') || lower.endsWith('.css') || lower.endsWith('.js') || lower.includes('ui')) {
    return AGENTS.find((a) => a.id === 'agente_11_ui_ux') || AGENTS[0];
  }
  if (lower.includes('docker') || lower.endsWith('.yml') || lower.endsWith('.yaml') || lower.includes('.env') || lower.includes('ci-cd')) {
    return AGENTS.find((a) => a.id === 'agente_07_devops') || AGENTS[0];
  }
  if (lower.includes('ciso') || lower.includes('security') || lower.includes('dictamen')) {
    return AGENTS.find((a) => a.id === 'agente_10_ciso') || AGENTS[0];
  }
  if (lower.endsWith('.md') || lower.endsWith('.txt') || lower.includes('doc')) {
    return AGENTS.find((a) => a.id === 'agente_08_docs') || AGENTS[0];
  }
  return AGENTS[0] || null;
}

// ── Deliverables Specifications ───────────────────────────────────────────

/** @type {Array<{key: string, label: string, agentId: string, agentName: string}>} */
const _DELIVERABLE_SECTIONS = [
  { key: 'ceo_charter',            label: '📄 CEO Charter',         agentId: 'agente_00_ceo',            agentName: 'CEO' },
  { key: 'pre_sdd_doc',            label: '📄 Pre-SDD',             agentId: 'agente_02_architect',      agentName: 'Architect' },
  { key: 'sdd_arquitectura',       label: '🏛 SDD Arquitectura',    agentId: 'agente_02_architect',      agentName: 'Architect' },
  { key: 'ui_ux_spec',             label: '🎨 UI/UX Spec',          agentId: 'agente_11_ui_ux',          agentName: 'UI/UX' },
  { key: 'codigo_php',             label: '🐘 Código PHP',          agentId: 'agente_03_laravel',        agentName: 'PHP Dev' },
  { key: 'codigo_python',          label: '⚡ Código Python',       agentId: 'agente_04_fastapi',        agentName: 'Python Dev' },
  { key: 'reporte_qa_php',         label: '🔬 Reporte QA PHP',      agentId: 'agente_05_qa_php',         agentName: 'QA PHP' },
  { key: 'reporte_qa_python',      label: '🐍 Reporte QA Python',   agentId: 'agente_06_qa_python',      agentName: 'QA Python' },
  { key: 'infraestructura_docker', label: '⚙ Docker Infra',        agentId: 'agente_07_devops',         agentName: 'DevOps' },
  { key: 'dictamen_ciso',          label: '🛡 Dictamen CISO',       agentId: 'agente_10_ciso',           agentName: 'CISO' },
  { key: 'documentacion_rag',      label: '📚 Docs & RAG',          agentId: 'agente_08_docs',           agentName: 'Docs' },
  { key: 'estrategia_growth',      label: '📈 Growth Strategy',     agentId: 'agente_09_growth',         agentName: 'Growth' },
  { key: 'marketing_spec',         label: '📣 Marketing Spec',      agentId: 'agente_12_marketing',      agentName: 'Marketing' },
  { key: 'sales_analytics_spec',   label: '💹 Sales Analytics',     agentId: 'agente_13_sales_analytics',agentName: 'Sales' },
  { key: 'ceo_signoff',            label: '✅ CEO Sign-off',        agentId: 'agente_00_ceo',            agentName: 'CEO' },
];

// ── Header Renderer ───────────────────────────────────────────────────────

/**
 * Update panel header based on current mode (Agent Specific vs General Project).
 */
function _updatePanelHeader() {
  const panel = $id('side-panel');
  const iconEl = $id('panel-agent-icon');
  const nameEl = $id('panel-agent-name');
  const roleEl = $id('panel-agent-role');
  let switchBtn = $id('btn-switch-to-general');

  const effPid = _getEffectiveProjectId();

  if (_currentAgent) {
    // ── Agent Specific Mode ───────────────────────────────────────────────
    if (iconEl) iconEl.textContent = _currentAgent.icon;
    if (nameEl) nameEl.textContent = _currentAgent.fullName.toUpperCase();
    if (roleEl) roleEl.textContent = _currentAgent.description ?? '';
    if (panel) panel.style.setProperty('--panel-accent', _currentAgent.color || '#06b6d4');

    // Button to switch to General Project View
    if (!switchBtn && $id('panel-header')) {
      switchBtn = document.createElement('button');
      switchBtn.id = 'btn-switch-to-general';
      switchBtn.className = 'pixel-btn secondary';
      switchBtn.style.cssText = 'font-size:7px;padding:3px 7px;margin-left:auto;margin-right:6px;border-color:#06b6d4;color:#06b6d4;white-space:nowrap;';
      switchBtn.innerHTML = '🏢 TODO EL PROYECTO';
      switchBtn.title = 'Cambiar a vista general del proyecto (todos los entregables y logs)';
      switchBtn.addEventListener('click', () => {
        _openGeneralPanel(_activeTab);
      });
      const closeBtn = $id('btn-close-panel');
      if (closeBtn && closeBtn.parentNode) {
        closeBtn.parentNode.insertBefore(switchBtn, closeBtn);
      }
    }
    if (switchBtn) {
      switchBtn.style.display = 'inline-block';
    }
  } else {
    // ── General Project Mode ──────────────────────────────────────────────
    if (iconEl) iconEl.textContent = '🏢';
    if (nameEl) {
      nameEl.textContent = effPid ? `PROYECTO: ${effPid.toUpperCase()}` : 'PROYECTO GENERAL';
    }
    if (roleEl) {
      roleEl.textContent = effPid ? 'WORKSPACE & TELEMETRÍA GLOBAL DEL PROYECTO' : 'SELECCIONA UN PROYECTO ACTIVO';
    }
    if (panel) panel.style.setProperty('--panel-accent', '#06b6d4');
    if (switchBtn) {
      switchBtn.style.display = 'none';
    }
  }
}

// ── Panel Open / Close ────────────────────────────────────────────────────

/**
 * Open the side panel for a specific selected agent.
 * @param {AgentDef} agent
 * @param {string|null} [projectId=null]
 */
function _openPanel(agent, projectId = null) {
  _currentAgent = agent;
  _currentProjectId = projectId || _getEffectiveProjectId();
  _sessionId = _getSessionId(agent.id);

  _updatePanelHeader();

  const panel = $id('side-panel');
  if (panel) {
    panel.classList.remove('hidden');
    panel.classList.add('open');
  }

  // Activate tab (default to marketing for growth & marketing agents)
  if (agent && (agent.id === 'agente_12_marketing' || agent.id === 'agente_09_growth')) {
    _switchTab('marketing');
  } else {
    _switchTab(_activeTab || 'chat');
  }
}

/**
 * Open the side panel in General Project Mode (no specific agent).
 * @param {string} [tabName='files']
 */
function _openGeneralPanel(tabName = 'files') {
  _currentAgent = null;
  _currentProjectId = _getEffectiveProjectId();

  // Clear agent canvas highlights
  document.querySelectorAll('.workstation').forEach((el) => el.classList.remove('selected'));
  document.querySelectorAll('.agent-avatar').forEach((el) => el.classList.remove('selected'));

  _updatePanelHeader();

  const panel = $id('side-panel');
  if (panel) {
    panel.classList.remove('hidden');
    panel.classList.add('open');
  }

  _switchTab(tabName);
}

function _closePanel() {
  const panel = $id('side-panel');
  if (panel) {
    panel.classList.remove('open');
    panel.classList.add('hidden');
  }
  document.querySelectorAll('.workstation').forEach((el) => el.classList.remove('selected'));
  document.querySelectorAll('.agent-avatar').forEach((el) => el.classList.remove('selected'));
  _currentAgent = null;
}

// ── Tabs ──────────────────────────────────────────────────────────────────

/** @param {string} tabName */
function _switchTab(tabName) {
  _activeTab = tabName;

  document.querySelectorAll('.tab-btn').forEach((btn) => {
    const isActive = /** @type {HTMLElement} */ (btn).dataset.tab === tabName;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', String(isActive));
  });
  document.querySelectorAll('.tab-content').forEach((el) => {
    el.classList.toggle('active', el.id === `tab-${tabName}`);
  });

  _loadTabContent(tabName);
}

/** @param {string} tabName */
function _loadTabContent(tabName) {
  if (tabName === 'chat')  _loadChatHistory();
  if (tabName === 'logs')  _loadLogs();
  if (tabName === 'files') _loadFiles();
  if (tabName === 'models') _loadModelsTab();
  if (tabName === 'marketing') _loadMarketingTab();
}

// ── Chat Tab ──────────────────────────────────────────────────────────────

function _loadChatHistory() {
  const chatEl = $id('chat-messages');
  if (!chatEl) return;

  const effPid = _getEffectiveProjectId();

  // ── General Project Chat Mode ───────────────────────────────────────────
  if (!_currentAgent) {
    chatEl.innerHTML = `
      <div class="chat-message system" style="background:rgba(6,182,212,0.1);border:1px dashed #06b6d4;padding:10px;border-radius:6px;">
        <div class="msg-role" style="color:#06b6d4;">🏢 CANAL DE DIRECCIÓN GENERAL DEL PROYECTO</div>
        <div class="msg-content" style="color:#e2e8f0;font-size:10.5px;line-height:1.4;">
          Estás en el <strong>Canal Central del Proyecto</strong>${effPid ? ` (<code>${_esc(effPid)}</code>)` : ''}.<br>
          Cualquier directiva, pregunta o instrucción que envíes aquí será atendida por la <strong>Dirección Ejecutiva (CEO)</strong> para orquestar o reportar sobre todo el equipo.
        </div>
      </div>
    `;

    if (!effPid) {
      const el = document.createElement('div');
      el.className = 'chat-message system';
      el.innerHTML = '<div class="msg-content">💡 Selecciona un proyecto en la barra superior para interactuar con la fábrica.</div>';
      chatEl.appendChild(el);
      return;
    }

    // Load recent general conversations from project if available
    API.getConversations(effPid)
      .then((convs) => {
        if (convs && convs.length > 0) {
          const sep = document.createElement('div');
          sep.style.cssText = 'font-size:7px;color:#64748b;text-align:center;margin:8px 0;letter-spacing:1px;';
          sep.textContent = '── ACTIVIDAD RECIENTE EN PIPELINE ──';
          chatEl.appendChild(sep);

          convs.slice(-3).forEach((conv) => {
            if (conv.prompt) {
              const pEl = document.createElement('div');
              pEl.className = 'chat-message system';
              pEl.innerHTML = `
                <div class="msg-role">📤 PROMPT (${_esc(conv.agent_id)})</div>
                <pre class="msg-content" style="white-space:pre-wrap;font-size:9.5px;">${_esc(_truncate(conv.prompt, 400))}</pre>`;
              chatEl.appendChild(pEl);
            }
            if (conv.response) {
              const rEl = document.createElement('div');
              rEl.className = 'chat-message agent';
              rEl.innerHTML = `
                <div class="msg-role" style="color:#06b6d4">🤖 ${_esc(conv.agent_id.toUpperCase())}</div>
                <div class="msg-content">${_md(_truncate(conv.response, 600))}</div>`;
              chatEl.appendChild(rEl);
            }
          });
          chatEl.scrollTop = chatEl.scrollHeight;
        }
      })
      .catch(() => {});
    return;
  }

  // ── Agent-Specific 1-on-1 Chat Mode ─────────────────────────────────────
  chatEl.innerHTML = '<div class="loading-pixel">CARGANDO HISTORIAL...</div>';

  API.getChatHistory(_currentAgent.id, _sessionId)
    .then((hist) => {
      const turns = hist?.turns ?? [];
      if (turns.length > 0) {
        chatEl.innerHTML = '';
        turns.forEach((turn) => {
          const el = document.createElement('div');
          if (turn.role === 'user') {
            el.className = 'chat-message user';
            el.innerHTML = `
              <div class="msg-role">👤 TÚ</div>
              <div class="msg-content">${_esc(turn.content)}</div>`;
          } else {
            el.className = 'chat-message agent';
            el.innerHTML = `
              <div class="msg-role" style="color:var(--panel-accent)">${_currentAgent?.icon ?? ''} ${_currentAgent?.name.toUpperCase() ?? ''}</div>
              <div class="msg-content">${_md(turn.content)}</div>`;
          }
          chatEl.appendChild(el);
        });
        chatEl.scrollTop = chatEl.scrollHeight;
        return;
      }

      // If no direct chat turns exist yet, check pipeline conversations if project is active
      if (effPid) {
        return API.getConversations(effPid, _currentAgent.id).then((convs) => {
          chatEl.innerHTML = '';
          if (!convs || convs.length === 0) {
            _setPlaceholder(
              chatEl, '💬',
              `Inicia una conversación directa 1-a-1 con ${_currentAgent?.name}.`,
              'Escribe tu mensaje en la caja inferior y pulsa ENVIAR.'
            );
            return;
          }
          convs.forEach((conv) => {
            if (conv.prompt) {
              const el = document.createElement('div');
              el.className = 'chat-message system';
              el.innerHTML = `
                <div class="msg-role">📤 PROMPT ENVIADO (PIPELINE)</div>
                <pre class="msg-content">${_esc(_truncate(conv.prompt, 600))}</pre>`;
              chatEl.appendChild(el);
            }
            if (conv.response) {
              const el = document.createElement('div');
              el.className = 'chat-message agent';
              el.innerHTML = `
                <div class="msg-role" style="color:var(--panel-accent)">${_currentAgent?.icon ?? ''} ${_currentAgent?.name.toUpperCase() ?? ''}</div>
                <div class="msg-content">${_md(conv.response)}</div>`;
              chatEl.appendChild(el);
            }
          });
          chatEl.scrollTop = chatEl.scrollHeight;
        });
      }

      chatEl.innerHTML = '';
      _setPlaceholder(
        chatEl, '💬',
        `Inicia una conversación directa 1-a-1 con ${_currentAgent.name}.`,
        'Escribe tu mensaje en la caja inferior y pulsa ENVIAR.'
      );
    })
    .catch((err) => {
      chatEl.innerHTML = `<div class="error-pixel">ERROR: ${_esc(String(err))}</div>`;
    });
}

// ── Logs Tab ──────────────────────────────────────────────────────────────

function _loadLogs() {
  const logsEl = $id('logs-list');
  if (!logsEl) return;

  const effPid = _getEffectiveProjectId();
  if (!effPid) {
    _setPlaceholder(logsEl, '📋', 'Selecciona un proyecto activo para ver el historial de ejecución.');
    return;
  }

  logsEl.innerHTML = '<div class="loading-pixel">CARGANDO LOGS...</div>';

  API.getProjectStatus(effPid)
    .then((status) => {
      logsEl.innerHTML = '';
      const history = status.execution_history ?? [];

      if (history.length === 0) {
        _setPlaceholder(logsEl, '📂', 'Sin historial de ejecución disponible aún en este proyecto.');
        return;
      }

      if (_currentAgent) {
        // ── Agent Specific Logs ───────────────────────────────────────────
        const agentHistory = history.filter((step) => step.agent_id === _currentAgent.id);

        const headerEl = document.createElement('div');
        headerEl.style.cssText = 'padding:6px 8px;font-size:7px;color:var(--panel-accent);font-weight:bold;border-bottom:1px solid #1e293b;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;';
        headerEl.innerHTML = `
          <span>📋 PASOS DE ${_currentAgent.fullName.toUpperCase()} (${agentHistory.length})</span>
          <span style="font-size:6.5px;color:#94a3b8;">${_esc(effPid)}</span>
        `;
        logsEl.appendChild(headerEl);

        if (agentHistory.length === 0) {
          const emptyNotice = document.createElement('div');
          emptyNotice.style.cssText = 'padding:14px;text-align:center;color:#94a3b8;font-size:10px;line-height:1.5;background:rgba(15,23,42,0.6);border-radius:6px;border:1px dashed #334155;margin:8px 0;';
          emptyNotice.innerHTML = `
            <div style="font-size:20px;margin-bottom:6px;">ℹ️</div>
            <div style="font-weight:bold;color:#f1f5f9;margin-bottom:4px;">Sin pasos ejecutados por ${_esc(_currentAgent.name)} en este proyecto</div>
            <div>Este agente no ha intervenido directamente en las fases registradas hasta el momento.</div>
            <div style="margin-top:8px;font-size:9px;color:#06b6d4;">💡 Puedes hablar con él en el <strong>CHAT</strong> o pedirle modificaciones en <strong>EDITAR ARCHIVO</strong>.</div>
          `;
          logsEl.appendChild(emptyNotice);
          return;
        }

        agentHistory.forEach((step) => {
          const el = document.createElement('div');
          el.className = 'log-entry log-highlight';
          el.style.cssText = 'border-left: 3px solid var(--panel-accent);';
          el.innerHTML = `
            <div class="log-step">#${step.step_number}</div>
            <div class="log-agent active" style="color:var(--panel-accent)">${_esc(step.agent_id)}</div>
            <div class="log-status" style="color:#22c55e;">${_esc(step.status)}</div>
            <div class="log-time" style="margin-left:auto;">${new Date(step.timestamp_iso).toLocaleTimeString('es-ES')}</div>`;
          logsEl.appendChild(el);
        });

      } else {
        // ── General Project Logs (All Agents) ─────────────────────────────
        const headerEl = document.createElement('div');
        headerEl.style.cssText = 'padding:6px 8px;font-size:7px;color:#06b6d4;font-weight:bold;border-bottom:1px solid #1e293b;margin-bottom:8px;display:flex;justify-content:space-between;align-items:center;';
        headerEl.innerHTML = `
          <span>📋 HISTORIAL GLOBAL DE EJECUCIÓN (${history.length} PASOS)</span>
          <span style="font-size:6.5px;color:#94a3b8;">${_esc(effPid)}</span>
        `;
        logsEl.appendChild(headerEl);

        history.forEach((step) => {
          const matchedAgent = AGENTS.find((a) => a.id === step.agent_id);
          const icon = matchedAgent?.icon || '🤖';
          const name = matchedAgent?.name || step.agent_id;
          const color = matchedAgent?.color || '#06b6d4';

          const el = document.createElement('div');
          el.className = 'log-entry';
          el.style.cssText = 'cursor:pointer;';
          el.title = `Clic para ver detalles de ${name}`;
          el.innerHTML = `
            <div class="log-step">#${step.step_number}</div>
            <div class="log-agent" style="color:${color};font-weight:600;">${icon} ${_esc(name)}</div>
            <div class="log-status">${_esc(step.status)}</div>
            <div class="log-time" style="margin-left:auto;">${new Date(step.timestamp_iso).toLocaleTimeString('es-ES')}</div>`;

          el.addEventListener('click', () => {
            if (matchedAgent) {
              _openPanel(matchedAgent, effPid);
            }
          });
          logsEl.appendChild(el);
        });
      }
    })
    .catch((err) => {
      logsEl.innerHTML = `<div class="error-pixel">ERROR: ${_esc(String(err))}</div>`;
    });
}

// ── Files Tab ─────────────────────────────────────────────────────────────

/**
 * Render the files tree based on cached deliverables and workspace files.
 * Supports real-time text filtering and dual-mode layout.
 */
function _renderFilesList() {
  const filesTree = $id('files-tree');
  if (!filesTree) return;

  const effPid = _getEffectiveProjectId();
  filesTree.innerHTML = '';

  const q = _filesFilterText.trim().toLowerCase();
  let renderedCount = 0;

  // 1. Deliverables Section
  let deliverableItems = _DELIVERABLE_SECTIONS.filter(({ key }) => {
    const content = /** @type {string|undefined} */ (_cachedDeliverables[key]);
    return content && content.trim() !== '';
  });

  if (_currentAgent) {
    // In Agent Mode: highlight agent's own deliverables first
    const agentDelivs = deliverableItems.filter((d) => d.agentId === _currentAgent.id);
    const otherDelivs = deliverableItems.filter((d) => d.agentId !== _currentAgent.id);

    // Section 1A: Deliverables owned by this agent
    const agSec = document.createElement('div');
    agSec.style.cssText = 'padding:6px 8px;font-size:7px;color:var(--panel-accent);font-weight:bold;border-bottom:1px solid #1e293b;margin-bottom:4px;';
    agSec.innerHTML = `── ENTREGABLES DE ${_currentAgent.name.toUpperCase()} (${agentDelivs.length}) ──`;
    filesTree.appendChild(agSec);

    if (agentDelivs.length === 0) {
      const noneNotice = document.createElement('div');
      noneNotice.style.cssText = 'padding:6px 10px;font-size:9.5px;color:#94a3b8;font-style:italic;';
      noneNotice.textContent = 'Sin entregables formales de este agente aún.';
      filesTree.appendChild(noneNotice);
    } else {
      agentDelivs.forEach((d) => {
        const content = _cachedDeliverables[d.key];
        if (q && !d.label.toLowerCase().includes(q) && !d.key.toLowerCase().includes(q)) return;
        renderedCount++;

        const item = document.createElement('div');
        item.className = 'file-item active';
        item.style.cssText = 'border-left: 3px solid var(--panel-accent);';
        const kb = (content.length / 1024).toFixed(1);
        item.innerHTML = `<span>${d.label}</span><span class="file-size">${kb} KB</span>`;
        item.addEventListener('click', () => {
          document.querySelectorAll('.file-item').forEach((el) => el.classList.remove('active'));
          item.classList.add('active');
          _showFileContent(d.label, content);
        });
        filesTree.appendChild(item);
      });
    }

    // Section 1B: Other deliverables in the project
    if (otherDelivs.length > 0) {
      const othSec = document.createElement('div');
      othSec.style.cssText = 'padding:6px 8px;font-size:7px;color:#64748b;font-weight:bold;border-top:1px solid #1e293b;margin-top:8px;margin-bottom:4px;';
      othSec.innerHTML = `── OTROS ENTREGABLES DEL PROYECTO (${otherDelivs.length}) ──`;
      filesTree.appendChild(othSec);

      otherDelivs.forEach((d) => {
        const content = _cachedDeliverables[d.key];
        if (q && !d.label.toLowerCase().includes(q) && !d.key.toLowerCase().includes(q) && !d.agentName.toLowerCase().includes(q)) return;
        renderedCount++;

        const item = document.createElement('div');
        item.className = 'file-item';
        const kb = (content.length / 1024).toFixed(1);
        item.innerHTML = `
          <span>${d.label}</span>
          <span style="font-size:6px;color:#64748b;margin-left:auto;margin-right:8px;">[${_esc(d.agentName)}]</span>
          <span class="file-size">${kb} KB</span>`;
        item.addEventListener('click', () => {
          document.querySelectorAll('.file-item').forEach((el) => el.classList.remove('active'));
          item.classList.add('active');
          _showFileContent(d.label, content);
        });
        filesTree.appendChild(item);
      });
    }

  } else {
    // In General Mode: show all project deliverables cleanly categorized
    const delivSec = document.createElement('div');
    delivSec.style.cssText = 'padding:6px 8px;font-size:7px;color:#06b6d4;font-weight:bold;border-bottom:1px solid #1e293b;margin-bottom:4px;';
    delivSec.innerHTML = `── ENTREGABLES PRINCIPALES DEL PROYECTO (${deliverableItems.length}) ──`;
    filesTree.appendChild(delivSec);

    deliverableItems.forEach((d) => {
      const content = _cachedDeliverables[d.key];
      if (q && !d.label.toLowerCase().includes(q) && !d.key.toLowerCase().includes(q) && !d.agentName.toLowerCase().includes(q)) return;
      renderedCount++;

      const item = document.createElement('div');
      item.className = 'file-item';
      const kb = (content.length / 1024).toFixed(1);
      item.innerHTML = `
        <span>${d.label}</span>
        <span style="font-size:6px;color:#06b6d4;opacity:0.8;margin-left:auto;margin-right:8px;">[${_esc(d.agentName)}]</span>
        <span class="file-size">${kb} KB</span>`;
      item.addEventListener('click', () => {
        document.querySelectorAll('.file-item').forEach((el) => el.classList.remove('active'));
        item.classList.add('active');
        _showFileContent(d.label, content);
      });
      filesTree.appendChild(item);
    });
  }

  // 2. Workspace Code Files Section
  if (_cachedWorkspaceFiles && _cachedWorkspaceFiles.length > 0) {
    let wsList = [..._cachedWorkspaceFiles];

    // In Agent Mode, prioritize files aligned with that agent
    if (_currentAgent) {
      const agentId = _currentAgent.id;
      wsList.sort((a, b) => {
        const matchA = _isAgentRelevantFile(a.path, agentId) ? 1 : 0;
        const matchB = _isAgentRelevantFile(b.path, agentId) ? 1 : 0;
        return matchB - matchA;
      });
    }

    const sep = document.createElement('div');
    sep.style.cssText = 'padding:6px 8px;font-size:7px;color:#94a3b8;font-weight:bold;border-top:1px solid #1e293b;margin-top:10px;margin-bottom:4px;display:flex;justify-content:space-between;align-items:center;';
    sep.innerHTML = `
      <span>── CÓDIGO Y WORKSPACE (${_cachedWorkspaceFiles.length} ARCHIVOS) ──</span>
      <span style="font-size:6.5px;color:#64748b;">${_esc(effPid)}</span>
    `;
    filesTree.appendChild(sep);

    wsList.forEach((file) => {
      if (q && !file.path.toLowerCase().includes(q)) return;
      renderedCount++;

      const item = document.createElement('div');
      item.className = 'file-item';

      const isRelevant = _currentAgent && _isAgentRelevantFile(file.path, _currentAgent.id);
      if (isRelevant) {
        item.style.borderLeft = '2px solid var(--panel-accent)';
      }

      const icon = _getFileIcon(file.path);
      const kb = (file.size / 1024).toFixed(1);
      item.innerHTML = `
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(file.path)}">
          ${icon} ${_esc(file.path)}
        </span>
        <span class="file-size" style="flex-shrink:0;margin-left:6px;">${kb} KB</span>
      `;

      item.addEventListener('click', () => {
        document.querySelectorAll('.file-item').forEach((el) => el.classList.remove('active'));
        item.classList.add('active');
        if (effPid) {
          API.getFileContent(effPid, file.path)
            .then((res) => {
              _showFileContent(`📄 ${file.path}`, res.content, file.path);
            })
            .catch((err) => {
              _showFileContent(`📄 ${file.path}`, `Error al leer archivo: ${err}`);
            });
        }
      });
      filesTree.appendChild(item);
    });
  }

  if (renderedCount === 0) {
    if (q) {
      _setPlaceholder(filesTree, '🔍', `No hay archivos que coincidan con "${q}".`);
    } else {
      _setPlaceholder(
        filesTree, '⏳',
        'Sin archivos ni entregables aún en este proyecto.',
        'Lanza un proyecto o pide a un agente crear un archivo nuevo.'
      );
    }
  }
}

/**
 * Check if a file is relevant to an agent's specialization.
 * @param {string} filePath
 * @param {string} agentId
 * @returns {boolean}
 */
function _isAgentRelevantFile(filePath, agentId) {
  const p = filePath.toLowerCase();
  switch (agentId) {
    case 'agente_03_laravel':
      return p.endsWith('.php') || p.includes('laravel');
    case 'agente_04_fastapi':
      return p.endsWith('.py') || p.includes('fastapi');
    case 'agente_11_ui_ux':
    case 'agente_14_qa_ui_ux':
      return p.endsWith('.html') || p.endsWith('.css') || p.endsWith('.js') || p.includes('ui');
    case 'agente_07_devops':
      return p.includes('docker') || p.endsWith('.yml') || p.endsWith('.yaml') || p.includes('.env') || p.includes('ci-cd');
    case 'agente_05_qa_php':
      return p.endsWith('.php') && (p.includes('test') || p.includes('qa'));
    case 'agente_06_qa_python':
      return p.endsWith('.py') && (p.includes('test') || p.includes('qa'));
    case 'agente_10_ciso':
      return p.includes('ciso') || p.includes('security') || p.includes('audit');
    case 'agente_08_docs':
      return p.endsWith('.md') || p.endsWith('.txt') || p.includes('doc');
    default:
      return false;
  }
}

function _loadFiles() {
  const filesTree = $id('files-tree');
  const filesLabel = $id('files-project-label');
  const filesHeader = $id('files-header');
  if (!filesTree) return;

  const effPid = _getEffectiveProjectId();

  if (!effPid) {
    if (filesLabel) filesLabel.textContent = 'Sin proyecto activo';
    _setPlaceholder(filesTree, '📁', 'Selecciona un proyecto activo para explorar sus entregables y archivos.');
    return;
  }

  // Header subtitle and filter bar
  if (filesLabel) {
    if (_currentAgent) {
      filesLabel.textContent = `📁 ${effPid} (Filtrado: ${_currentAgent.name})`;
    } else {
      filesLabel.textContent = `📁 ${effPid} (Vista Completa del Proyecto)`;
    }
  }

  // Ensure filter input exists inside files-header
  if (filesHeader && !$id('files-filter-input')) {
    filesHeader.style.cssText = 'display:flex;flex-direction:column;gap:6px;padding:8px 12px;background:rgba(0,0,0,0.3);border-bottom:1px solid #1e293b;';
    const filterInput = document.createElement('input');
    filterInput.id = 'files-filter-input';
    filterInput.className = 'pixel-input';
    filterInput.placeholder = '🔍 Filtrar archivos (ej: .php, docker, auth)...';
    filterInput.style.cssText = 'width:100%;font-size:7.5px;padding:4px 8px;background:#020617;border:1px solid #1e293b;border-radius:4px;color:#f8fafc;';
    filterInput.addEventListener('input', (e) => {
      _filesFilterText = /** @type {HTMLInputElement} */ (e.target).value;
      _renderFilesList();
    });
    filesHeader.appendChild(filterInput);
  }

  filesTree.innerHTML = '<div class="loading-pixel">CARGANDO ARCHIVOS Y ENTREGABLES...</div>';

  Promise.all([
    API.getProjectDeliverables(effPid).catch(() => ({})),
    API.getWorkspaceFiles(effPid).catch(() => []),
  ])
    .then(([delivs, wsFiles]) => {
      _cachedDeliverables = delivs || {};
      _cachedWorkspaceFiles = wsFiles || [];
      _renderFilesList();
    })
    .catch((err) => {
      filesTree.innerHTML = `<div class="error-pixel">ERROR: ${_esc(String(err))}</div>`;
    });
}

/**
 * Display file content in the viewer with clickable edit button.
 * Works seamlessly both in General Project Mode and Agent Specific Mode.
 * @param {string} label
 * @param {string} content
 * @param {string|null} [filePath=null]
 */
function _showFileContent(label, content, filePath = null) {
  const header  = $id('file-viewer-header');
  const viewer  = $id('file-viewer-content');
  const wrapper = $id('file-viewer');
  if (!viewer || !wrapper) return;

  if (header) {
    header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:4px 8px;background:#0f172a;border-bottom:1px solid #1e293b;';
    header.innerHTML = `<span style="font-weight:600;font-size:7.5px;color:#f1f5f9;overflow:hidden;text-overflow:ellipsis;">${_esc(label)}</span>`;

    if (filePath) {
      const editBtn = document.createElement('button');
      editBtn.className = 'pixel-btn icon';
      editBtn.style.cssText = 'font-size:6.5px;padding:3px 8px;margin-left:auto;border-color:#06b6d4;color:#06b6d4;';
      editBtn.textContent = '✏ EDITAR ARCHIVO';
      editBtn.title = _currentAgent
        ? `Editar este archivo con ${_currentAgent.name}`
        : 'Editar este archivo con el equipo de agentes';
      editBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        _openFileEditModal(filePath);
      });
      header.appendChild(editBtn);
    }
  }

  viewer.textContent = content;
  wrapper.classList.add('visible');
}

// ── File Edit Modal (Phase 4 Hot Reload) ──────────────────────────────────

/**
 * Convert unified diff text into styled HTML lines.
 * @param {string} diffText
 * @returns {string}
 */
function _renderDiffHtml(diffText) {
  const lines = (diffText || '').split('\n');
  return lines
    .map((line) => {
      if (line.startsWith('+') && !line.startsWith('+++')) {
        return `<span class="diff-line-add" style="display:block;background:rgba(34,197,94,0.15);color:#86efac;padding:1px 4px;">${_esc(line)}</span>`;
      }
      if (line.startsWith('-') && !line.startsWith('---')) {
        return `<span class="diff-line-del" style="display:block;background:rgba(239,68,68,0.15);color:#fca5a5;padding:1px 4px;">${_esc(line)}</span>`;
      }
      if (line.startsWith('@@')) {
        return `<span class="diff-line-info" style="display:block;color:#38bdf8;padding:1px 4px;">${_esc(line)}</span>`;
      }
      return `<span style="display:block;padding:1px 4px;color:#cbd5e1;">${_esc(line)}</span>`;
    })
    .join('');
}

/**
 * Open interactive hot file edit modal for the currently selected agent or general mode.
 * Automatically resolves target agent if in General Mode.
 * @param {string} [initialFilePath='']
 */
async function _openFileEditModal(initialFilePath = '') {
  const overlay = $id('modal-overlay');
  const titleEl = $id('modal-title');
  const bodyEl  = $id('modal-body');
  const footEl  = $id('modal-footer');
  if (!overlay || !titleEl || !bodyEl || !footEl) return;

  const effPid = _getEffectiveProjectId();

  // Resolve initial target agent
  let targetAgent = _currentAgent || _detectBestAgentForFile(initialFilePath) || AGENTS[0];

  titleEl.textContent = `✏ EDITAR ARCHIVO — ${targetAgent ? targetAgent.name.toUpperCase() : 'AGENTE FACTORY'}`;

  // Options for Agent selector
  const agentOptionsHtml = AGENTS.map((a) => {
    const isSel = targetAgent && a.id === targetAgent.id ? 'selected' : '';
    return `<option value="${_esc(a.id)}" ${isSel}>${a.icon} ${_esc(a.fullName)}</option>`;
  }).join('');

  // Options for File selector
  let fileOptionsHtml = '<option value="">-- Selecciona archivo existente o escribe abajo --</option>';
  if (effPid) {
    try {
      const files = _cachedWorkspaceFiles.length > 0 ? _cachedWorkspaceFiles : await API.getWorkspaceFiles(effPid);
      files.forEach((f) => {
        const sel = f.path === initialFilePath ? 'selected' : '';
        const kb = (f.size / 1024).toFixed(1);
        fileOptionsHtml += `<option value="${_esc(f.path)}" ${sel}>${_esc(f.path)} (${kb} KB)</option>`;
      });
    } catch (_) {}
  }

  bodyEl.innerHTML = `
    <div id="fe-form">
      <div class="form-group" style="margin-bottom:8px;">
        <label style="font-size:7px;color:#94a3b8;font-weight:bold;">AGENTE ENCARGADO DE LA MODIFICACIÓN:</label>
        <select id="fe-agent-select" class="pixel-input" style="width:100%;font-size:7.5px;">${agentOptionsHtml}</select>
      </div>
      <div class="form-group" style="margin-bottom:8px;">
        <label style="font-size:7px;color:#94a3b8;font-weight:bold;">PROYECTO:</label>
        <input id="fe-project-id" class="pixel-input" value="${_esc(effPid || '')}" placeholder="ID del proyecto (ej: proj_88c9fd46)" style="width:100%;font-size:7.5px;">
      </div>
      <div class="form-group" style="margin-bottom:8px;">
        <label style="font-size:7px;color:#94a3b8;font-weight:bold;">ARCHIVOS DEL WORKSPACE:</label>
        <select id="fe-file-select" class="pixel-input" style="width:100%;margin-bottom:6px;font-size:7.5px;">${fileOptionsHtml}</select>
        <label style="font-size:7px;color:#94a3b8;font-weight:bold;">O RUTA RELATIVA:</label>
        <input id="fe-file-path" class="pixel-input" value="${_esc(initialFilePath)}" placeholder="ej: app/main.py" style="width:100%;font-size:7.5px;">
      </div>
      <div class="form-group" style="margin-bottom:8px;">
        <label id="fe-instructions-label" style="font-size:7px;color:#94a3b8;font-weight:bold;">
          INSTRUCCIONES PARA ${_esc(targetAgent ? targetAgent.fullName.toUpperCase() : 'EL AGENTE')}:
        </label>
        <textarea id="fe-instructions" class="pixel-input" rows="4" placeholder="Describe qué cambios, corrección o refactorización deseas realizar en el archivo..." style="width:100%;font-size:7.5px;"></textarea>
      </div>
    </div>
    <div id="fe-result" class="hidden">
      <div id="fe-explanation" style="margin-bottom:8px;color:var(--text-bright);font-weight:bold;font-size:8px;"></div>
      <div class="diff-container" id="fe-diff-content" style="max-height:260px;overflow-y:auto;background:#020617;padding:8px;border-radius:4px;font-family:monospace;font-size:10px;"></div>
    </div>
  `;

  footEl.innerHTML = `
    <button id="fe-btn-cancel" class="pixel-btn secondary">CANCELAR</button>
    <button id="fe-btn-propose" class="pixel-btn primary">PROPORNER CAMBIO ▶</button>
  `;

  overlay.classList.remove('hidden');

  const agentSelect = /** @type {HTMLSelectElement|null} */ ($id('fe-agent-select'));
  const fileSelect = /** @type {HTMLSelectElement|null} */ ($id('fe-file-select'));
  const filePathInput = /** @type {HTMLInputElement|null} */ ($id('fe-file-path'));
  const instLabel = $id('fe-instructions-label');

  if (agentSelect) {
    agentSelect.addEventListener('change', () => {
      const chosen = AGENTS.find((a) => a.id === agentSelect.value);
      if (chosen) {
        targetAgent = chosen;
        titleEl.textContent = `✏ EDITAR ARCHIVO — ${chosen.name.toUpperCase()}`;
        if (instLabel) {
          instLabel.textContent = `INSTRUCCIONES PARA ${chosen.fullName.toUpperCase()}:`;
        }
      }
    });
  }

  if (fileSelect && filePathInput) {
    fileSelect.addEventListener('change', () => {
      if (fileSelect.value) {
        filePathInput.value = fileSelect.value;
        const autoAgent = _detectBestAgentForFile(fileSelect.value);
        if (autoAgent && agentSelect && (!agentSelect.value || agentSelect.value === 'agente_00_ceo')) {
          agentSelect.value = autoAgent.id;
          agentSelect.dispatchEvent(new Event('change'));
        }
      }
    });
  }

  $id('fe-btn-cancel')?.addEventListener('click', () => {
    overlay.classList.add('hidden');
  });

  const proposeBtn = $id('fe-btn-propose');
  proposeBtn?.addEventListener('click', async () => {
    const proj = /** @type {HTMLInputElement|null} */ ($id('fe-project-id'))?.value.trim();
    const filePath = filePathInput?.value.trim();
    const instruction = /** @type {HTMLTextAreaElement|null} */ ($id('fe-instructions'))?.value.trim();
    const selectedAgentId = agentSelect?.value || (targetAgent ? targetAgent.id : 'agente_00_ceo');

    if (!proj) {
      alert('Por favor especifica un ID de proyecto.');
      return;
    }
    if (!filePath) {
      alert('Por favor especifica la ruta relativa del archivo.');
      return;
    }
    if (!instruction) {
      alert('Por favor escribe las instrucciones de modificación.');
      return;
    }

    proposeBtn.textContent = '⏳ ANALIZANDO Y GENERANDO DIFF...';
    proposeBtn.setAttribute('disabled', 'true');

    try {
      const proposal = await API.proposeFileEdit(
        selectedAgentId, proj, filePath, instruction, _sessionId
      );

      $id('fe-form')?.classList.add('hidden');
      const resultArea = $id('fe-result');
      if (resultArea) resultArea.classList.remove('hidden');

      const expEl = $id('fe-explanation');
      if (expEl) expEl.textContent = `📋 Explicación: ${proposal.explanation}`;

      const diffEl = $id('fe-diff-content');
      if (diffEl) diffEl.innerHTML = _renderDiffHtml(proposal.diff);

      footEl.innerHTML = `
        <button id="fe-btn-reject" class="pixel-btn secondary">✗ DESCARTAR</button>
        <button id="fe-btn-confirm" class="pixel-btn primary">✓ APLICAR CAMBIO EN DISCO</button>
      `;

      $id('fe-btn-reject')?.addEventListener('click', async () => {
        await API.rejectFileEdit(proposal.edit_token);
        overlay.classList.add('hidden');
      });

      $id('fe-btn-confirm')?.addEventListener('click', async () => {
        const confirmBtn = $id('fe-btn-confirm');
        if (confirmBtn) {
          confirmBtn.textContent = '⏳ GUARDANDO EN DISCO...';
          confirmBtn.setAttribute('disabled', 'true');
        }
        try {
          const res = await API.confirmFileEdit(proposal.edit_token);
          alert(`✓ ${res.message}${res.backup_path ? `\nCopia de seguridad creada en: ${res.backup_path}` : ''}`);
          overlay.classList.add('hidden');
          _loadChatHistory();
          _loadFiles();
        } catch (err) {
          alert(`Error al aplicar cambio: ${err.message || err}`);
          if (confirmBtn) {
            confirmBtn.textContent = '✓ APLICAR CAMBIO EN DISCO';
            confirmBtn.removeAttribute('disabled');
          }
        }
      });
    } catch (err) {
      alert(`Error al generar propuesta: ${err.message || err}`);
      proposeBtn.textContent = 'PROPORNER CAMBIO ▶';
      proposeBtn.removeAttribute('disabled');
    }
  });
}

// ── Models & LLM Routing Tab (PASO 5) ──────────────────────────────────────

/** @type {object|null} Active agent's loaded LLM config */
let _currentAgentLLMConfig = null;
/** @type {Array<object>} Global catalog of models */
let _globalCatalog = [];
/** @type {Record<string, object>} Cached ping results per model_id */
let _pingStatuses = {};

async function _loadModelsTab() {
  const targetAgent = _currentAgent;
  const listEl = $id('agent-models-list');
  const bannerEl = $id('chain-ping-banner');
  if (bannerEl) bannerEl.classList.add('hidden');

  if (!targetAgent) {
    if (listEl) {
      listEl.innerHTML = `
        <div class="chat-placeholder" style="padding:20px;text-align:center;">
          <div class="placeholder-icon">🤖</div>
          <div style="font-family:var(--font-mono);font-size:11px;color:#cbd5e1;margin-bottom:8px;">
            SELECCIONA UN AGENTE PARA CONFIGURAR SUS MODELOS LLM
          </div>
          <div style="font-size:9px;color:#94a3b8;line-height:1.5;">
            Haz clic en cualquier agente en la oficina 2D o usa el acceso rápido a continuación:
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:12px;justify-content:center;">
            ${AGENTS.map((a) => `<button class="pixel-btn secondary btn-pick-agent" data-agent="${_esc(a.id)}" style="font-size:8px;padding:3px 6px;">${a.icon} ${a.name}</button>`).join('')}
          </div>
        </div>
      `;
      listEl.querySelectorAll('.btn-pick-agent').forEach((btn) => {
        btn.addEventListener('click', () => {
          const aid = /** @type {HTMLElement} */ (btn).dataset.agent;
          const found = AGENTS.find((a) => a.id === aid);
          if (found) _openPanel(found, _getEffectiveProjectId());
        });
      });
    }
    return;
  }

  if (listEl) {
    listEl.innerHTML = `
      <div style="padding:16px;text-align:center;font-family:var(--font-mono);font-size:10px;color:#06b6d4;">
        ⏳ Cargando catálogo y modelos para ${_esc(targetAgent.name)}...
      </div>
    `;
  }

  try {
    const [catalog, config] = await Promise.all([
      API.getLLMCatalog(),
      API.getAgentLLMConfig(targetAgent.id),
    ]);
    _globalCatalog = catalog || [];
    _currentAgentLLMConfig = config;
    _renderModelsTab();
  } catch (err) {
    if (listEl) {
      listEl.innerHTML = `
        <div class="chain-banner error">
          Error al cargar configuración LLM: ${_esc(err.message || err)}
        </div>
      `;
    }
  }
}

function _renderModelsTab() {
  if (!_currentAgentLLMConfig) return;

  // 1. Populate agent global params
  const tempSlider = /** @type {HTMLInputElement|null} */ ($id('param-temperature'));
  const tempVal = $id('val-temperature');
  const tokensInput = /** @type {HTMLInputElement|null} */ ($id('param-max-tokens'));
  const timeoutInput = /** @type {HTMLInputElement|null} */ ($id('param-timeout'));
  const retriesInput = /** @type {HTMLInputElement|null} */ ($id('param-max-retries'));

  if (tempSlider) tempSlider.value = String(_currentAgentLLMConfig.temperature ?? 0.2);
  if (tempVal) tempVal.textContent = String(_currentAgentLLMConfig.temperature ?? 0.2);
  if (tokensInput) tokensInput.value = String(_currentAgentLLMConfig.max_tokens ?? 4096);
  if (timeoutInput) timeoutInput.value = String(_currentAgentLLMConfig.timeout ?? 60);
  if (retriesInput) retriesInput.value = String(_currentAgentLLMConfig.max_retries ?? 1);

  // 2. Populate add model dropdown
  const selectEl = /** @type {HTMLSelectElement|null} */ ($id('select-add-model'));
  if (selectEl) {
    const assignedIds = new Set((_currentAgentLLMConfig.assigned_models || []).map((m) => m.model_id));
    const available = _globalCatalog.filter((m) => !assignedIds.has(m.model_id));
    let opts = '<option value="">+ Seleccionar modelo del catálogo...</option>';
    available.forEach((m) => {
      opts += `<option value="${_esc(m.model_id)}">${_esc(m.display_name)} (${_esc(m.provider.toUpperCase())} · ${_esc(m.tier.toUpperCase())})</option>`;
    });
    selectEl.innerHTML = opts;
  }

  // 3. Render assigned models list
  const listEl = $id('agent-models-list');
  if (!listEl) return;

  const assigned = _currentAgentLLMConfig.assigned_models || [];
  if (assigned.length === 0) {
    listEl.innerHTML = '<div style="padding:10px;font-size:9px;color:#94a3b8;font-family:var(--font-mono);">No hay modelos vinculados a este agente. Añade uno del catálogo.</div>';
    return;
  }

  let enabledCounter = 0;
  const cardsHtml = assigned.map((item, idx) => {
    let roleLabel = '[INACTIVO]';
    let roleClass = 'role-inactive';
    let cardClass = 'model-row-card disabled-card';

    if (item.enabled) {
      enabledCounter++;
      if (enabledCounter === 1) {
        roleLabel = '[PRIMARIO]';
        roleClass = 'role-primary';
        cardClass = 'model-row-card primary-card';
      } else {
        roleLabel = `[FALLBACK ${enabledCounter - 1}]`;
        roleClass = 'role-fallback';
        cardClass = 'model-row-card fallback-card';
      }
    }

    const tierBadge = item.tier === 'paid'
      ? '<span class="meta-badge badge-paid">PAID</span>'
      : '<span class="meta-badge badge-free">FREE</span>';

    const keyBadge = item.has_api_key
      ? '<span class="meta-badge badge-key-ok">KEY OK</span>'
      : '<span class="meta-badge badge-key-missing">SIN KEY</span>';

    // Ping status badge
    let pingBadgeHtml = '';
    const pStatus = _pingStatuses[item.model_id];
    if (pStatus) {
      if (pStatus.loading) {
        pingBadgeHtml = '<span class="ping-result-badge loading">Probando...</span>';
      } else if (pStatus.success) {
        pingBadgeHtml = `<span class="ping-result-badge ok">🟢 OK · ${pStatus.latency_ms || 0} ms</span>`;
      } else if (pStatus.status === 'rate_limited') {
        pingBadgeHtml = '<span class="ping-result-badge rate-limited">🟡 429 Cuota Agotada</span>';
      } else {
        const errLabel = pStatus.status === 'missing_api_key' ? 'Sin API Key' : (pStatus.status === 'timeout' ? 'Timeout' : 'Error');
        pingBadgeHtml = `<span class="ping-result-badge error">🔴 ${errLabel}</span>`;
      }
    }

    const upDisabled = idx === 0 ? 'disabled' : '';
    const downDisabled = idx === assigned.length - 1 ? 'disabled' : '';

    return `
      <div class="${cardClass}" data-model="${_esc(item.model_id)}" data-idx="${idx}">
        <div class="model-row-top">
          <span class="model-role-badge ${roleClass}">${roleLabel}</span>
          <div class="model-info-group">
            <span class="model-name-text" title="${_esc(item.model_id)}">${_esc(item.display_name || item.model_id)}</span>
            <span class="model-provider-tag">${_esc(item.provider || 'custom')}</span>
          </div>
          <div class="model-meta-badges">
            ${tierBadge}
            ${keyBadge}
          </div>
        </div>
        <div class="model-row-bottom">
          <div class="model-row-controls">
            <label class="model-toggle-label">
              <input type="checkbox" class="model-active-toggle" data-idx="${idx}" ${item.enabled ? 'checked' : ''}>
              <span>${item.enabled ? 'ACTIVO' : 'APAGADO'}</span>
            </label>
            <div class="reorder-btns">
              <button class="pixel-btn icon btn-arrow btn-move-up" data-idx="${idx}" ${upDisabled} title="Subir prioridad">▲</button>
              <button class="pixel-btn icon btn-arrow btn-move-down" data-idx="${idx}" ${downDisabled} title="Bajar prioridad">▼</button>
            </div>
            <button class="pixel-btn icon btn-arrow btn-remove-model" data-idx="${idx}" title="Quitar de este agente" style="color:#ef4444;">✕</button>
          </div>
          <div class="model-ping-group">
            ${pingBadgeHtml}
            <button class="pixel-btn secondary btn-ping-model" data-model="${_esc(item.model_id)}" style="font-size:7px;padding:2px 6px;">
              ⚡ Ping
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');

  listEl.innerHTML = cardsHtml;

  // 4. Attach event listeners on cards
  listEl.querySelectorAll('.model-active-toggle').forEach((cb) => {
    cb.addEventListener('change', (e) => {
      const idx = parseInt(/** @type {HTMLInputElement} */ (e.target).dataset.idx || '0', 10);
      if (_currentAgentLLMConfig.assigned_models[idx]) {
        _currentAgentLLMConfig.assigned_models[idx].enabled = /** @type {HTMLInputElement} */ (e.target).checked;
        _renderModelsTab();
      }
    });
  });

  listEl.querySelectorAll('.btn-move-up').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt(/** @type {HTMLElement} */ (e.target).dataset.idx || '0', 10);
      if (idx > 0) {
        const arr = _currentAgentLLMConfig.assigned_models;
        const temp = arr[idx];
        arr[idx] = arr[idx - 1];
        arr[idx - 1] = temp;
        arr.forEach((m, i) => { m.priority = i + 1; });
        _renderModelsTab();
      }
    });
  });

  listEl.querySelectorAll('.btn-move-down').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt(/** @type {HTMLElement} */ (e.target).dataset.idx || '0', 10);
      const arr = _currentAgentLLMConfig.assigned_models;
      if (idx < arr.length - 1) {
        const temp = arr[idx];
        arr[idx] = arr[idx + 1];
        arr[idx + 1] = temp;
        arr.forEach((m, i) => { m.priority = i + 1; });
        _renderModelsTab();
      }
    });
  });

  listEl.querySelectorAll('.btn-remove-model').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      const idx = parseInt(/** @type {HTMLElement} */ (e.target).dataset.idx || '0', 10);
      _currentAgentLLMConfig.assigned_models.splice(idx, 1);
      _currentAgentLLMConfig.assigned_models.forEach((m, i) => { m.priority = i + 1; });
      _renderModelsTab();
    });
  });

  listEl.querySelectorAll('.btn-ping-model').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      const modelId = /** @type {HTMLElement} */ (e.target).dataset.model;
      if (!modelId) return;

      _pingStatuses[modelId] = { loading: true };
      _renderModelsTab();

      try {
        const res = await API.pingLLMModel(modelId);
        _pingStatuses[modelId] = res;
      } catch (err) {
        _pingStatuses[modelId] = {
          success: false,
          status: 'provider_error',
          message: err.message || 'Error de conexión',
        };
      }
      _renderModelsTab();
    });
  });
}

function _initModelsTabEvents() {
  // Temperature slider real-time label update
  $id('param-temperature')?.addEventListener('input', (e) => {
    const valEl = $id('val-temperature');
    if (valEl) valEl.textContent = /** @type {HTMLInputElement} */ (e.target).value;
  });

  // Test full agent chain
  $id('btn-ping-chain')?.addEventListener('click', async () => {
    if (!_currentAgent) return;
    const btn = $id('btn-ping-chain');
    const banner = $id('chain-ping-banner');

    if (btn) {
      btn.textContent = '⏳ PROBANDO...';
      btn.setAttribute('disabled', 'true');
    }
    if (banner) {
      banner.className = 'chain-banner warning';
      banner.innerHTML = '⚡ Verificando todos los modelos activos en orden de prioridad...';
      banner.classList.remove('hidden');
    }

    try {
      const res = await API.pingAgentLLMChain(_currentAgent.id);

      if (res.chain_status && Array.isArray(res.chain_status)) {
        res.chain_status.forEach((link) => {
          if (link.model_id && link.ping_result) {
            _pingStatuses[link.model_id] = link.ping_result;
          }
        });
      }

      if (banner) {
        if (res.all_ok) {
          banner.className = 'chain-banner success';
          banner.innerHTML = `🟢 <strong>Cadena Operativa:</strong> Responderá <code>${_esc(res.effective_model_id)}</code> (${_esc(res.effective_provider?.toUpperCase())})`;
        } else {
          banner.className = 'chain-banner error';
          banner.innerHTML = '🔴 <strong>Fallo en la Cadena:</strong> Ningún modelo respondió con éxito. Verifica tus API keys en el entorno.';
        }
      }
      _renderModelsTab();
    } catch (err) {
      if (banner) {
        banner.className = 'chain-banner error';
        banner.innerHTML = `🔴 Error al probar la cadena: ${_esc(err.message || err)}`;
      }
    } finally {
      if (btn) {
        btn.textContent = '⚡ PROBAR CADENA';
        btn.removeAttribute('disabled');
      }
    }
  });

  // Add model from catalog selector
  $id('btn-add-model-to-agent')?.addEventListener('click', () => {
    const selectEl = /** @type {HTMLSelectElement|null} */ ($id('select-add-model'));
    if (!selectEl || !selectEl.value || !_currentAgentLLMConfig) return;

    const mid = selectEl.value;
    const catModel = _globalCatalog.find((m) => m.model_id === mid);
    const newPriority = (_currentAgentLLMConfig.assigned_models || []).length + 1;

    _currentAgentLLMConfig.assigned_models.push({
      model_id: mid,
      enabled: true,
      priority: newPriority,
      display_name: catModel ? catModel.display_name : mid,
      provider: catModel ? catModel.provider : 'custom',
      tier: catModel ? catModel.tier : 'free',
      has_api_key: catModel ? catModel.has_api_key : false,
    });

    _renderModelsTab();
  });

  // Save Agent Configuration
  $id('btn-save-llm-config')?.addEventListener('click', async () => {
    if (!_currentAgent || !_currentAgentLLMConfig) return;
    const btn = $id('btn-save-llm-config');
    const banner = $id('chain-ping-banner');

    const tempSlider = /** @type {HTMLInputElement|null} */ ($id('param-temperature'));
    const tokensInput = /** @type {HTMLInputElement|null} */ ($id('param-max-tokens'));
    const timeoutInput = /** @type {HTMLInputElement|null} */ ($id('param-timeout'));
    const retriesInput = /** @type {HTMLInputElement|null} */ ($id('param-max-retries'));

    const payload = {
      assigned_models: _currentAgentLLMConfig.assigned_models,
      temperature: tempSlider ? parseFloat(tempSlider.value) : 0.2,
      max_tokens: tokensInput ? parseInt(tokensInput.value, 10) : 4096,
      timeout: timeoutInput ? parseInt(timeoutInput.value, 10) : 60,
      max_retries: retriesInput ? parseInt(retriesInput.value, 10) : 1,
    };

    if (btn) {
      btn.textContent = '⏳ GUARDANDO...';
      btn.setAttribute('disabled', 'true');
    }

    try {
      const saved = await API.saveAgentLLMConfig(_currentAgent.id, payload);
      _currentAgentLLMConfig = saved;
      _renderModelsTab();
      if (banner) {
        banner.className = 'chain-banner success';
        banner.innerHTML = '💾 <strong>Configuración guardada en caliente.</strong> Persistida en SQLite.';
        banner.classList.remove('hidden');
        setTimeout(() => banner.classList.add('hidden'), 4000);
      }
    } catch (err) {
      if (banner) {
        banner.className = 'chain-banner error';
        banner.innerHTML = `🔴 Error al guardar: ${_esc(err.message || err)}`;
        banner.classList.remove('hidden');
      }
    } finally {
      if (btn) {
        btn.textContent = '💾 GUARDAR CONFIG';
        btn.removeAttribute('disabled');
      }
    }
  });

  // Reset to default configuration
  $id('btn-reset-llm-config')?.addEventListener('click', async () => {
    if (!_currentAgent) return;
    if (!confirm(`¿Restablecer la cadena de ${_currentAgent.name} a los valores recomendados de fábrica?`)) return;

    try {
      const def = await API.resetAgentLLMConfig(_currentAgent.id);
      _currentAgentLLMConfig = def;
      _pingStatuses = {};
      _renderModelsTab();
      const banner = $id('chain-ping-banner');
      if (banner) {
        banner.className = 'chain-banner success';
        banner.innerHTML = '↺ Cadena restablecida a valores recomendados de fábrica.';
        banner.classList.remove('hidden');
        setTimeout(() => banner.classList.add('hidden'), 4000);
      }
    } catch (err) {
      alert(`Error al restablecer: ${err.message || err}`);
    }
  });

  // Toggle New Model Drawer
  $id('btn-toggle-new-model')?.addEventListener('click', () => {
    const drawer = $id('new-model-drawer');
    drawer?.classList.toggle('hidden');
  });

  $id('btn-close-new-model')?.addEventListener('click', () => {
    $id('new-model-drawer')?.classList.add('hidden');
  });

  // Ping new model before registering
  $id('btn-ping-new-model')?.addEventListener('click', async () => {
    const modelId = /** @type {HTMLInputElement|null} */ ($id('new-model-id'))?.value.trim();
    const resultSpan = $id('new-model-ping-result');
    if (!modelId) {
      alert('Introduce un Model ID primero.');
      return;
    }

    if (resultSpan) {
      resultSpan.className = 'ping-result-badge loading';
      resultSpan.textContent = 'Probando conexión...';
    }

    try {
      const res = await API.pingLLMModel(modelId);
      if (resultSpan) {
        if (res.success) {
          resultSpan.className = 'ping-result-badge ok';
          resultSpan.textContent = `🟢 OK · ${res.latency_ms} ms`;
        } else if (res.status === 'rate_limited') {
          resultSpan.className = 'ping-result-badge rate-limited';
          resultSpan.textContent = '🟡 429 Cuota Agotada';
        } else {
          resultSpan.className = 'ping-result-badge error';
          resultSpan.textContent = `🔴 ${res.status === 'missing_api_key' ? 'Sin API Key' : res.status}`;
        }
      }
    } catch (err) {
      if (resultSpan) {
        resultSpan.className = 'ping-result-badge error';
        resultSpan.textContent = '🔴 Fallo de conexión';
      }
    }
  });

  // Create Catalog Model
  $id('btn-create-catalog-model')?.addEventListener('click', async () => {
    const idInput = /** @type {HTMLInputElement|null} */ ($id('new-model-id'));
    const nameInput = /** @type {HTMLInputElement|null} */ ($id('new-model-name'));
    const provSelect = /** @type {HTMLSelectElement|null} */ ($id('new-model-provider'));
    const urlInput = /** @type {HTMLInputElement|null} */ ($id('new-model-base-url'));
    const envInput = /** @type {HTMLInputElement|null} */ ($id('new-model-env'));
    const tierSelect = /** @type {HTMLSelectElement|null} */ ($id('new-model-tier'));

    if (!idInput || !idInput.value.trim() || !nameInput || !nameInput.value.trim() || !envInput || !envInput.value.trim()) {
      alert('Por favor completa Model ID, Nombre y Env API Key.');
      return;
    }

    const payload = {
      model_id: idInput.value.trim(),
      display_name: nameInput.value.trim(),
      provider: provSelect ? provSelect.value : 'custom',
      base_url: urlInput && urlInput.value.trim() ? urlInput.value.trim() : null,
      api_key_env: envInput.value.trim(),
      tier: tierSelect ? tierSelect.value : 'free',
      default_temperature: 0.2,
      default_max_tokens: 4096,
      is_active: true,
    };

    try {
      const created = await API.createLLMModel(payload);
      _globalCatalog.push(created);
      alert(`¡Modelo '${created.display_name}' registrado en el catálogo con éxito!`);
      $id('new-model-drawer')?.classList.add('hidden');
      idInput.value = '';
      nameInput.value = '';
      if (urlInput) urlInput.value = '';
      _renderModelsTab();
    } catch (err) {
      alert(`Error al crear modelo: ${err.message || err}`);
    }
  });
}

// ── Chat Send ─────────────────────────────────────────────────────────────

function _initChatInput() {
  const sendBtn  = $id('btn-send-chat');
  const inputEl  = /** @type {HTMLTextAreaElement|null} */ ($id('chat-input'));
  if (!sendBtn || !inputEl) return;

  sendBtn.addEventListener('click', async () => {
    const msg = inputEl.value.trim();
    if (!msg) return;

    const effPid = _getEffectiveProjectId();
    const chatEl = $id('chat-messages');

    // Append user bubble immediately
    if (chatEl) {
      const userMsg = document.createElement('div');
      userMsg.className = 'chat-message user';
      userMsg.innerHTML = `
        <div class="msg-role">👤 TÚ</div>
        <div class="msg-content">${_esc(msg)}</div>`;
      chatEl.appendChild(userMsg);
      chatEl.scrollTop = chatEl.scrollHeight;
    }

    inputEl.value = '';
    sendBtn.textContent = '⏳';
    sendBtn.setAttribute('disabled', 'true');

    // Route to selected agent or lead orchestrator (CEO)
    const targetAgentId = _currentAgent ? _currentAgent.id : 'agente_00_ceo';
    const targetAgentDef = _currentAgent || AGENTS.find((a) => a.id === 'agente_00_ceo') || AGENTS[0];

    try {
      const resp = await API.sendChatMessage(
        targetAgentId, msg, effPid, _sessionId,
      );
      if (chatEl) {
        const agentMsg = document.createElement('div');
        agentMsg.className = 'chat-message agent';
        const icon = targetAgentDef?.icon || '🤖';
        const name = targetAgentDef?.name ? targetAgentDef.name.toUpperCase() : 'CEO';
        const color = targetAgentDef?.color || '#06b6d4';
        agentMsg.innerHTML = `
          <div class="msg-role" style="color:${color}">${icon} ${name}</div>
          <div class="msg-content">${_md(resp.response ?? 'Sin respuesta.')}</div>`;
        chatEl.appendChild(agentMsg);
        chatEl.scrollTop = chatEl.scrollHeight;
      }
    } catch (err) {
      if (chatEl) {
        const errEl = document.createElement('div');
        errEl.className = 'chat-message system';
        errEl.innerHTML = `
          <div class="msg-role">⚠️ ERROR</div>
          <div class="msg-content">Error al comunicarse con el agente: ${_esc(String(err instanceof Error ? err.message : err))}</div>`;
        chatEl.appendChild(errEl);
        chatEl.scrollTop = chatEl.scrollHeight;
      }
    } finally {
      sendBtn.textContent = 'ENVIAR ▶';
      sendBtn.removeAttribute('disabled');
    }
  });

  // Ctrl+Enter shortcut
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      e.preventDefault();
      sendBtn.dispatchEvent(new MouseEvent('click'));
    }
  });

  // ✏ File Edit button in Chat footer
  $id('btn-file-edit')?.addEventListener('click', () => {
    _openFileEditModal();
  });
}

// ── Marketing Tab (FASE 3) ────────────────────────────────────────────────

const MARKETING_CHANNELS_META = {
  linkedin: {
    icon: '💼',
    name: 'LinkedIn',
    handleLabel: 'Handle / URL Empresa',
    handlePlaceholder: '@mi_empresa o https://linkedin.com/company/...',
    credLabel: 'Webhook / Token',
    credPlaceholder: 'https://hooks.zapier.com/...',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Posts de autoridad técnica B2B, hitos y casos de uso',
  },
  x_twitter: {
    icon: '🐦',
    name: 'X (Twitter)',
    handleLabel: 'Handle (@cuenta)',
    handlePlaceholder: '@mi_saas_app',
    credLabel: 'API Token / Webhook',
    credPlaceholder: 'Token o webhook de publicación',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Hilos técnicos, anuncios de features y memes dev',
  },
  instagram_meta: {
    icon: '📸',
    name: 'Instagram & Meta',
    handleLabel: 'Usuario / URL Perfil',
    handlePlaceholder: '@mi_cuenta_meta',
    credLabel: 'Access Token / Webhook',
    credPlaceholder: 'Token de Instagram Graph API o webhook',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Carruseles explicativos, copies persuasivos',
  },
  tiktok: {
    icon: '📱',
    name: 'TikTok',
    handleLabel: 'Usuario (@cuenta)',
    handlePlaceholder: '@mi_cuenta_tiktok',
    credLabel: 'Webhook / Token',
    credPlaceholder: 'Webhook para publicar borradores',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Guiones ágiles de video (30-60s), demos en vivo',
  },
  producthunt: {
    icon: '🚀',
    name: 'Product Hunt',
    handleLabel: 'Slug Producto / URL',
    handlePlaceholder: 'mi-saas-launch',
    credLabel: 'API Token / Webhook',
    credPlaceholder: 'Developer token de Product Hunt',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Tagline de alto impacto, primer comentario del maker',
  },
  google_ads: {
    icon: '🎯',
    name: 'Google Ads',
    handleLabel: 'ID de Cuenta / URL Final',
    handlePlaceholder: '123-456-7890 o https://misaas.com',
    credLabel: 'Conversions Webhook / Token',
    credPlaceholder: 'Webhook o conversion tracking token',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Copys con alta intención de búsqueda comercial',
  },
  reddit_devto: {
    icon: '👾',
    name: 'Reddit & Dev.to',
    handleLabel: 'Subreddits / User Dev.to',
    handlePlaceholder: 'r/SaaS, r/webdev, @mi_usuario',
    credLabel: 'Webhook / API Key',
    credPlaceholder: 'Token o webhook',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Enfoque técnico, tutoriales y comparativas de arquitectura',
  },
  telegram_discord: {
    icon: '💬',
    name: 'Telegram & Discord',
    handleLabel: 'Canal / Servidor',
    handlePlaceholder: 't.me/mi_canal o discord.gg/...',
    credLabel: 'Bot Token / Webhook',
    credPlaceholder: 'https://discord.com/api/webhooks/...',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Changelogs, avisos de despliegue y comunidad',
  },
  email_newsletter: {
    icon: '📧',
    name: 'Email / Newsletter',
    handleLabel: 'Remitente / Lista',
    handlePlaceholder: 'newsletter@misaas.com',
    credLabel: 'API Key / Webhook',
    credPlaceholder: 'API Key del gestor de envíos',
    instLabel: 'Instrucciones Especiales',
    instPlaceholder: 'Secuencias drip de bienvenida, valor y conversión',
  },
};

const MARKETING_TOOLS_META = {
  market_research_seo: {
    icon: '🔍',
    title: 'SEO & Investigación de Mercado',
    desc: 'Búsqueda web profunda, análisis de competidores y selección de palabras clave con Tavily/Serper o scraping ligero.',
  },
  seo_landing_injector: {
    icon: '🌐',
    title: 'Landing Page & Píxeles de Tracking',
    desc: 'Genera Landing Page HTML5 + Tailwind e inyecta píxeles (Google Analytics, GTM, Meta, TikTok) y archivos SEO (sitemap.xml, robots.txt).',
  },
  email_campaign_manager: {
    icon: '✉️',
    title: 'Gestor de Campañas de Email',
    desc: 'Secuencias drip automatizadas con envío simulado o real mediante Resend, Brevo o SendGrid.',
  },
  social_ads_publisher: {
    icon: '📢',
    title: 'Social Ads & Publicación Automatizada',
    desc: 'Diseño de anuncios publicitarios multiformato y publicación automatizada vía webhook (Make, Zapier, n8n).',
  },
};

/** @type {any|null} Active project marketing profile */
let _currentMarketingProfile = null;
/** @type {boolean} Guard for event registration */
let _marketingEventsInitialized = false;

async function _loadMarketingTab() {
  const container = $id('tab-marketing');
  if (!container) return;

  const projectSelect = /** @type {HTMLSelectElement|null} */ ($id('mkt-project-select'));
  const effPid = _getEffectiveProjectId();
  const feedback = $id('mkt-execution-feedback');

  if (feedback) {
    feedback.classList.add('hidden');
    feedback.textContent = '';
  }

  try {
    // 1. Fetch marketing projects and factory projects safely
    let mktProjects = [];
    try {
      const res = await API.getMarketingProjects();
      if (Array.isArray(res)) mktProjects = res;
    } catch (e) {
      console.warn('Could not load marketing projects:', e);
    }

    let factoryProjects = [];
    try {
      const res = await (API.listProjects ? API.listProjects() : API.getProjects());
      if (Array.isArray(res)) {
        factoryProjects = res;
      } else if (res && Array.isArray(res.projects)) {
        factoryProjects = res.projects;
      }
    } catch (e) {
      console.warn('Could not load factory projects:', e);
    }

    // Merge into unique projects list
    const projectMap = new Map();

    for (const fp of factoryProjects) {
      const pid = fp.project_id || fp.id;
      if (!pid) continue;
      projectMap.set(pid, {
        project_id: pid,
        project_name: fp.project_name || pid,
        marketing_enabled: false,
        marketing_type: 'none',
      });
    }

    for (const mp of mktProjects) {
      const pid = mp.project_id || mp.id;
      if (!pid) continue;
      if (projectMap.has(pid)) {
        const existing = projectMap.get(pid);
        projectMap.set(pid, { ...existing, ...mp });
      } else {
        projectMap.set(pid, mp);
      }
    }

    const projects = Array.from(projectMap.values());

    if (projects.length === 0) {
      if (feedback) {
        feedback.className = 'mkt-feedback-banner warning';
        feedback.textContent = 'No hay proyectos en la fábrica todavía. Crea uno en la barra superior para activar su marketing.';
        feedback.classList.remove('hidden');
      }
      return;
    }

    // Populate project select if empty or project list changed
    if (projectSelect) {
      const currentVal = projectSelect.value;
      projectSelect.innerHTML = projects.map((p) => {
        const pid = p.project_id || p.id;
        const name = p.project_name || pid;
        const mktStatus = p.marketing_enabled === false ? ' [Sin Mkt]' : ' [Mkt ON]';
        return `<option value="${_esc(pid)}">${_esc(name)}${mktStatus}</option>`;
      }).join('');

      if (currentVal && projects.some((p) => (p.project_id || p.id) === currentVal)) {
        projectSelect.value = currentVal;
      } else if (effPid && projects.some((p) => (p.project_id || p.id) === effPid)) {
        projectSelect.value = effPid;
      } else if (projects[0]) {
        projectSelect.value = projects[0].project_id || projects[0].id;
      }
    }

    const activePid = projectSelect?.value || effPid || projects[0]?.project_id || projects[0]?.id;
    if (!activePid) return;

    _currentProjectId = activePid;

    // 2. Fetch specific profile for active project
    const profile = await API.getProjectMarketingConfig(activePid);
    _currentMarketingProfile = profile;
    _renderMarketingProfile(_currentMarketingProfile);

  } catch (err) {
    console.error('Error loading marketing tab:', err);
    if (feedback) {
      feedback.className = 'mkt-feedback-banner error';
      feedback.textContent = `Error al cargar perfil de marketing: ${err.message || err}`;
      feedback.classList.remove('hidden');
    }
  }
}

function _renderMarketingProfile(profile) {
  if (!profile) return;

  // 1. Master Status Button
  const statusBtn = $id('btn-mkt-toggle-status');
  if (statusBtn) {
    if (profile.marketing_enabled) {
      statusBtn.className = 'pixel-btn mkt-status-btn active';
      statusBtn.textContent = '🟢 MARKETING ACTIVADO';
      statusBtn.title = 'Haz clic para desactivar marketing en este proyecto';
    } else {
      statusBtn.className = 'pixel-btn mkt-status-btn disabled';
      statusBtn.textContent = '🔴 MARKETING DESACTIVADO';
      statusBtn.title = 'Haz clic para activar marketing en este proyecto';
    }
  }

  // 2. Strategy & Identity Inputs
  const presetSel = /** @type {HTMLSelectElement|null} */ ($id('mkt-strategy-preset'));
  if (presetSel && profile.marketing_type) {
    presetSel.value = profile.marketing_type;
  }

  const brandVoiceInput = /** @type {HTMLInputElement|null} */ ($id('mkt-brand-voice'));
  if (brandVoiceInput) brandVoiceInput.value = profile.brand_voice || '';

  const targetAudienceInput = /** @type {HTMLInputElement|null} */ ($id('mkt-target-audience'));
  if (targetAudienceInput) targetAudienceInput.value = profile.target_audience || '';

  const langSel = /** @type {HTMLSelectElement|null} */ ($id('mkt-language'));
  if (langSel && profile.language) langSel.value = profile.language;

  const growthCheck = /** @type {HTMLInputElement|null} */ ($id('mkt-include-growth'));
  if (growthCheck) growthCheck.checked = profile.include_growth_agent ?? true;

  const salesCheck = /** @type {HTMLInputElement|null} */ ($id('mkt-include-sales'));
  if (salesCheck) salesCheck.checked = profile.include_sales_analytics_agent ?? true;

  // 3. Channels Matrix
  _renderMarketingChannels(profile.channels || []);

  // 4. Tools Container
  _renderMarketingTools(profile.tools || [], profile.project_id);

  // Clear previous execution feedback if any
  const feedback = $id('mkt-execution-feedback');
  if (feedback && profile.last_executed_at) {
    feedback.className = 'mkt-feedback-banner success';
    feedback.innerHTML = `
      <span>Última ejecución: <strong>${_esc(profile.last_executed_at)}</strong> (Estado: <strong>${_esc(profile.last_execution_status || 'OK')}</strong>)</span>
    `;
    feedback.classList.remove('hidden');
  }
}

function _renderMarketingChannels(channels) {
  const container = $id('mkt-channels-matrix');
  if (!container) return;

  const channelsMap = {};
  channels.forEach((ch) => {
    channelsMap[ch.channel_id] = ch;
  });

  const cardsHtml = Object.entries(MARKETING_CHANNELS_META).map(([chId, meta]) => {
    const ch = channelsMap[chId] || {
      channel_id: chId,
      name: meta.name,
      enabled: false,
      account_handle_or_url: '',
      credentials: {},
      custom_instructions: '',
    };
    const isEnabled = Boolean(ch.enabled);
    const credVal = ch.credentials?.webhook_url || ch.credentials?.token || ch.credentials?.api_key || '';

    // Determine connection badge (Direct Native vs n8n Webhook vs Draft)
    const creds = ch.credentials || {};
    const hasDirect = Boolean(
      creds.discord_webhook_url ||
      (creds.telegram_bot_token && creds.telegram_chat_id) ||
      creds.devto_api_key ||
      creds.linkedin_token ||
      creds.twitter_bearer_token ||
      creds.access_token ||
      creds.bearer_token
    );
    const hasWebhook = Boolean(creds.webhook_url);
    let badgeHtml = '';
    if (hasDirect) {
      badgeHtml = '<span class="mkt-conn-badge direct" title="Envío directo usando API o Token del proyecto">⚡ Conexión Directa (API)</span>';
    } else if (hasWebhook) {
      badgeHtml = '<span class="mkt-conn-badge webhook" title="Envío delegado al webhook de n8n">🔗 Vía Webhook n8n</span>';
    } else {
      badgeHtml = '<span class="mkt-conn-badge local" title="Modo borrador / webhook general">⚪ Vía Webhook / Borrador</span>';
    }

    return `
      <div class="mkt-channel-card ${isEnabled ? 'channel-active' : 'channel-disabled'}" data-channel-id="${_esc(chId)}">
        <div class="mkt-channel-header">
          <div class="mkt-channel-title">
            <span>${meta.icon}</span>
            <span>${_esc(meta.name)}</span>
          </div>
          <label class="pixel-checkbox-label">
            <input type="checkbox" class="mkt-ch-enable" data-channel="${_esc(chId)}" ${isEnabled ? 'checked' : ''}>
            <span>${isEnabled ? 'ACTIVO' : 'OFF'}</span>
          </label>
        </div>
        <div class="mkt-channel-field">
          <label>${_esc(meta.handleLabel)}</label>
          <input type="text" class="mkt-ch-handle" data-channel="${_esc(chId)}"
                 value="${_esc(ch.account_handle_or_url || '')}"
                 placeholder="${_esc(meta.handlePlaceholder)}">
        </div>
        <div class="mkt-channel-field">
          <label>${_esc(meta.credLabel)}</label>
          <input type="text" class="mkt-ch-cred" data-channel="${_esc(chId)}"
                 value="${_esc(credVal)}"
                 placeholder="${_esc(meta.credPlaceholder)}">
        </div>
        <div class="mkt-channel-field">
          <label>${_esc(meta.instLabel)}</label>
          <textarea class="mkt-ch-inst" data-channel="${_esc(chId)}"
                    placeholder="${_esc(meta.instPlaceholder)}" rows="2">${_esc(ch.custom_instructions || '')}</textarea>
        </div>
        <div class="mkt-channel-badge-wrap">
          ${badgeHtml}
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = cardsHtml;

  // Add change listeners to checkboxes to update visual state
  container.querySelectorAll('.mkt-ch-enable').forEach((chk) => {
    chk.addEventListener('change', (e) => {
      const isChecked = /** @type {HTMLInputElement} */ (e.target).checked;
      const card = /** @type {HTMLElement} */ (e.target).closest('.mkt-channel-card');
      const span = card?.querySelector('.pixel-checkbox-label span');
      if (card) {
        card.classList.toggle('channel-active', isChecked);
        card.classList.toggle('channel-disabled', !isChecked);
      }
      if (span) {
        span.textContent = isChecked ? 'ACTIVO' : 'OFF';
      }
    });
  });
}

function _renderMarketingTools(tools, projectId) {
  const container = $id('mkt-tools-container');
  if (!container) return;

  const toolsMap = {};
  tools.forEach((t) => {
    toolsMap[t.tool_id] = t;
  });

  const cardsHtml = Object.entries(MARKETING_TOOLS_META).map(([toolId, meta]) => {
    const t = toolsMap[toolId] || {
      tool_id: toolId,
      name: meta.title,
      description: meta.desc,
      enabled: true,
      credentials: {},
      settings: {},
    };
    const isEnabled = Boolean(t.enabled);
    const creds = t.credentials || {};
    const sets = t.settings || {};

    let toolFieldsHtml = '';

    if (toolId === 'market_research_seo') {
      const seeds = Array.isArray(sets.seed_keywords) ? sets.seed_keywords.join(', ') : (sets.seed_keywords || '');
      const comps = Array.isArray(sets.competitor_urls) ? sets.competitor_urls.join(', ') : (sets.competitor_urls || '');
      toolFieldsHtml = `
        <div class="mkt-tool-grid-2">
          <div class="mkt-channel-field">
            <label>API KEY BÚSQUEDA (TAVILY / SERPER):</label>
            <input type="text" id="mkt-tool-cred-search-key" value="${_esc(creds.search_api_key || '')}" placeholder="tvly-xxxx o secret...">
          </div>
          <div class="mkt-channel-field">
            <label>PALABRAS CLAVE SEMILLA (COMA):</label>
            <input type="text" id="mkt-tool-set-seed-keywords" value="${_esc(seeds)}" placeholder="saas b2b, devtool, crm...">
          </div>
        </div>
        <div class="mkt-channel-field">
          <label>URLS DE COMPETIDORES DIRECTOS (COMA):</label>
          <input type="text" id="mkt-tool-set-competitors" value="${_esc(comps)}" placeholder="https://competidor1.com, https://competidor2.io...">
        </div>
      `;
    } else if (toolId === 'seo_landing_injector') {
      const genLanding = sets.generate_landing_html !== false;
      const genSitemap = sets.generate_sitemap_robots !== false;
      toolFieldsHtml = `
        <div class="mkt-tool-grid-2">
          <div class="mkt-channel-field">
            <label>DOMINIO PÚBLICO DEL PROYECTO:</label>
            <input type="text" id="mkt-tool-set-domain" value="${_esc(sets.domain_url || '')}" placeholder="https://mi-proyecto.com">
          </div>
          <div class="mkt-agents-checks" style="margin-top:0;">
            <label class="pixel-checkbox-label">
              <input type="checkbox" id="mkt-tool-set-gen-landing" ${genLanding ? 'checked' : ''}>
              <span>Generar landing_page.html con TailwindCSS</span>
            </label>
            <label class="pixel-checkbox-label">
              <input type="checkbox" id="mkt-tool-set-gen-sitemap" ${genSitemap ? 'checked' : ''}>
              <span>Generar sitemap.xml y robots.txt</span>
            </label>
          </div>
        </div>
        <div class="mkt-tool-grid-2">
          <div class="mkt-channel-field">
            <label>GOOGLE ANALYTICS ID (G-XXXX):</label>
            <input type="text" id="mkt-tool-cred-ga" value="${_esc(creds.google_analytics_id || '')}" placeholder="G-XXXXXXXXXX">
          </div>
          <div class="mkt-channel-field">
            <label>GOOGLE TAG MANAGER ID (GTM-XXXX):</label>
            <input type="text" id="mkt-tool-cred-gtm" value="${_esc(creds.gtm_id || '')}" placeholder="GTM-XXXXXXX">
          </div>
        </div>
        <div class="mkt-tool-grid-2">
          <div class="mkt-channel-field">
            <label>META / FACEBOOK PIXEL ID:</label>
            <input type="text" id="mkt-tool-cred-meta" value="${_esc(creds.meta_pixel_id || '')}" placeholder="123456789012345">
          </div>
          <div class="mkt-channel-field">
            <label>TIKTOK PIXEL ID:</label>
            <input type="text" id="mkt-tool-cred-tiktok" value="${_esc(creds.tiktok_pixel_id || '')}" placeholder="CXXXXXXXXXXXXXX">
          </div>
        </div>
      `;
    } else if (toolId === 'email_campaign_manager') {
      const provider = sets.email_provider || 'resend';
      const sendMode = sets.send_mode || 'simulate';
      const recipients = Array.isArray(sets.recipient_list) ? sets.recipient_list.join(', ') : (sets.recipient_list || '');
      toolFieldsHtml = `
        <div class="mkt-tool-grid-2">
          <div class="mkt-channel-field">
            <label>PROVEEDOR DE EMAIL:</label>
            <select id="mkt-tool-set-email-provider" class="pixel-select">
              <option value="resend" ${provider === 'resend' ? 'selected' : ''}>Resend API</option>
              <option value="brevo" ${provider === 'brevo' ? 'selected' : ''}>Brevo (Sendinblue)</option>
              <option value="sendgrid" ${provider === 'sendgrid' ? 'selected' : ''}>SendGrid</option>
            </select>
          </div>
          <div class="mkt-channel-field">
            <label>MODO DE ENVÍO:</label>
            <select id="mkt-tool-set-send-mode" class="pixel-select">
              <option value="simulate" ${sendMode === 'simulate' ? 'selected' : ''}>Simulación Segura (Guardar JSON)</option>
              <option value="send_live" ${sendMode === 'send_live' ? 'selected' : ''}>Envío Real en Vivo (API)</option>
            </select>
          </div>
        </div>
        <div class="mkt-tool-grid-2">
          <div class="mkt-channel-field">
            <label>EMAIL REMITENTE:</label>
            <input type="text" id="mkt-tool-set-sender-email" value="${_esc(sets.sender_email || '')}" placeholder="hola@mi-dominio.com">
          </div>
          <div class="mkt-channel-field">
            <label>NOMBRE REMITENTE:</label>
            <input type="text" id="mkt-tool-set-sender-name" value="${_esc(sets.sender_name || '')}" placeholder="Equipo Mi Proyecto">
          </div>
        </div>
        <div class="mkt-tool-grid-2">
          <div class="mkt-channel-field">
            <label>API KEY DEL PROVEEDOR:</label>
            <input type="text" id="mkt-tool-cred-email-key" value="${_esc(creds.email_api_key || '')}" placeholder="re_xxxx / xkeysib-xxxx...">
          </div>
          <div class="mkt-channel-field">
            <label>LISTA DE PRUEBA (DESTINATARIOS COMA):</label>
            <input type="text" id="mkt-tool-set-recipient-list" value="${_esc(recipients)}" placeholder="test@email.com, demo@empresa.com...">
          </div>
        </div>
      `;
    } else if (toolId === 'social_ads_publisher') {
      const formats = Array.isArray(sets.formats) ? sets.formats.join(', ') : (sets.formats || 'carousel, single_image, thread, story');
      const platforms = Array.isArray(sets.target_platforms) ? sets.target_platforms.join(', ') : (sets.target_platforms || 'linkedin, x, instagram');
      toolFieldsHtml = `
        <div class="mkt-tool-grid-2">
          <div class="mkt-channel-field">
            <label>FORMATOS DE ANUNCIO (COMA):</label>
            <input type="text" id="mkt-tool-set-formats" value="${_esc(formats)}" placeholder="carousel, single_image, thread, story">
          </div>
          <div class="mkt-channel-field">
            <label>PLATAFORMAS DESTINO (COMA):</label>
            <input type="text" id="mkt-tool-set-platforms" value="${_esc(platforms)}" placeholder="linkedin, x, instagram">
          </div>
        </div>
        <div class="mkt-channel-field">
          <label>WEBHOOK DE PUBLICACIÓN (MAKE / ZAPIER / N8N):</label>
          <input type="text" id="mkt-tool-cred-webhook" value="${_esc(creds.webhook_url || '')}" placeholder="https://hook.eu1.make.com/xxxxxx">
        </div>
        <div class="mkt-n8n-automation-box">
          <div class="mkt-n8n-header">
            <span>⚡ AUTOMATIZACIÓN CON N8N POR PROYECTO</span>
            <span class="mkt-n8n-sub">Flujo dinámico y conector nativo generado para tus canales</span>
          </div>
          <div class="mkt-n8n-actions">
            <button type="button" id="btn-mkt-n8n-download" class="pixel-btn secondary" title="Descargar workflow JSON listo para importar en n8n">
              📥 DESCARGAR JSON PARA N8N
            </button>
            <button type="button" id="btn-mkt-n8n-provision" class="pixel-btn primary" title="Crear workflow automáticamente en n8n vía API y auto-asignar Webhook URL">
              ⚙️ AUTOCONFIGURAR EN MI N8N (API)
            </button>
          </div>
          <div id="mkt-n8n-feedback" class="mkt-feedback-banner hidden" style="margin-top:6px;font-size:9px;"></div>
        </div>
      `;
    }

    return `
      <div class="mkt-tool-card ${isEnabled ? 'tool-active' : 'tool-disabled'}" data-tool-id="${_esc(toolId)}">
        <div class="mkt-tool-header">
          <div class="mkt-tool-title">
            <span>${meta.icon}</span>
            <span>${_esc(meta.title)}</span>
          </div>
          <label class="pixel-checkbox-label">
            <input type="checkbox" class="mkt-tool-enable" data-tool="${_esc(toolId)}" ${isEnabled ? 'checked' : ''}>
            <span>${isEnabled ? 'HABILITADA' : 'DESACTIVADA'}</span>
          </label>
        </div>
        <div class="mkt-tool-desc">${_esc(meta.desc)}</div>
        <div class="mkt-tool-body">
          ${toolFieldsHtml}
        </div>
        <div class="mkt-tool-actions">
          <button class="pixel-btn secondary btn-mkt-test-tool" data-tool="${_esc(toolId)}" title="Diagnosticar credenciales y conectividad">
            ⚡ PROBAR HERRAMIENTA
          </button>
          <span class="mkt-tool-test-badge" id="mkt-test-badge-${_esc(toolId)}"></span>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = cardsHtml;

  // Checkbox toggle handler
  container.querySelectorAll('.mkt-tool-enable').forEach((chk) => {
    chk.addEventListener('change', (e) => {
      const isChecked = /** @type {HTMLInputElement} */ (e.target).checked;
      const card = /** @type {HTMLElement} */ (e.target).closest('.mkt-tool-card');
      const span = card?.querySelector('.pixel-checkbox-label span');
      if (card) {
        card.classList.toggle('tool-active', isChecked);
        card.classList.toggle('tool-disabled', !isChecked);
      }
      if (span) {
        span.textContent = isChecked ? 'HABILITADA' : 'DESACTIVADA';
      }
    });
  });

  // Diagnostic test buttons
  container.querySelectorAll('.btn-mkt-test-tool').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const toolId = /** @type {HTMLElement} */ (btn).dataset.tool;
      if (!toolId || !projectId) return;

      const badge = $id(`mkt-test-badge-${toolId}`);
      if (badge) {
        badge.className = 'mkt-tool-test-badge';
        badge.innerHTML = '⏳ Probando...';
      }

      // Collect current credentials and settings for this tool
      const payload = _collectToolData(toolId);

      try {
        const res = await API.testProjectMarketingTool(projectId, toolId, payload);
        if (badge) {
          if (res.status === 'ok') {
            badge.className = 'mkt-tool-test-badge ping-badge ok';
            badge.textContent = `🟢 OK (${res.latency_ms || 0}ms)`;
          } else if (res.status === 'missing_credentials') {
            badge.className = 'mkt-tool-test-badge ping-badge warning';
            badge.textContent = `🟡 SIN CREDENCIALES (${res.message || 'Simulado'})`;
          } else if (res.status === 'simulated') {
            badge.className = 'mkt-tool-test-badge ping-badge ok';
            badge.textContent = `🔵 SIMULADO (${res.latency_ms || 0}ms)`;
          } else {
            badge.className = 'mkt-tool-test-badge ping-badge error';
            badge.textContent = `🔴 ${res.message || 'Error en prueba'}`;
          }
        }
      } catch (err) {
        if (badge) {
          badge.className = 'mkt-tool-test-badge ping-badge error';
          badge.textContent = `🔴 ${err.message || 'Error de red'}`;
        }
      }
    });
  });

  // n8n Workflow Download button
  const n8nDownloadBtn = $id('btn-mkt-n8n-download');
  const n8nFeedback = $id('mkt-n8n-feedback');
  n8nDownloadBtn?.addEventListener('click', async () => {
    if (!projectId) return;
    if (n8nDownloadBtn) {
      n8nDownloadBtn.textContent = '⏳ GENERANDO...';
      n8nDownloadBtn.setAttribute('disabled', 'true');
    }
    try {
      const wf = await API.getProjectN8NWorkflow(projectId);
      const blob = new Blob([JSON.stringify(wf, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `n8n_workflow_${projectId}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      if (n8nFeedback) {
        n8nFeedback.className = 'mkt-feedback-banner success';
        n8nFeedback.innerHTML = `✅ Workflow JSON descargado y guardado en <code>marketing/n8n_workflow_${_esc(projectId)}.json</code>`;
        n8nFeedback.classList.remove('hidden');
      }
    } catch (err) {
      if (n8nFeedback) {
        n8nFeedback.className = 'mkt-feedback-banner error';
        n8nFeedback.textContent = `Error al generar flujo n8n: ${err.message || err}`;
        n8nFeedback.classList.remove('hidden');
      }
    } finally {
      if (n8nDownloadBtn) {
        n8nDownloadBtn.textContent = '📥 DESCARGAR JSON PARA N8N';
        n8nDownloadBtn.removeAttribute('disabled');
      }
    }
  });

  // Auto-provision in n8n API button
  const n8nProvisionBtn = $id('btn-mkt-n8n-provision');
  n8nProvisionBtn?.addEventListener('click', async () => {
    if (!projectId) return;
    if (n8nProvisionBtn) {
      n8nProvisionBtn.textContent = '⏳ CONECTANDO...';
      n8nProvisionBtn.setAttribute('disabled', 'true');
    }
    try {
      const res = await API.provisionProjectN8NWorkflow(projectId);
      const webhookInput = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-cred-webhook'));
      if (webhookInput && res.webhook_url) {
        webhookInput.value = res.webhook_url;
      }
      if (n8nFeedback) {
        n8nFeedback.className = res.live_n8n_connected ? 'mkt-feedback-banner success' : 'mkt-feedback-banner warning';
        n8nFeedback.innerHTML = `
          <strong>${res.live_n8n_connected ? '🟢 Aprovisionado en n8n' : '🔵 Webhook Local Asignado'}:</strong>
          ${_esc(res.message || res.webhook_url)}<br>
          URL: <code>${_esc(res.webhook_url)}</code>
        `;
        n8nFeedback.classList.remove('hidden');
      }
    } catch (err) {
      if (n8nFeedback) {
        n8nFeedback.className = 'mkt-feedback-banner error';
        n8nFeedback.textContent = `Error al aprovisionar en n8n: ${err.message || err}`;
        n8nFeedback.classList.remove('hidden');
      }
    } finally {
      if (n8nProvisionBtn) {
        n8nProvisionBtn.textContent = '⚙️ AUTOCONFIGURAR EN MI N8N (API)';
        n8nProvisionBtn.removeAttribute('disabled');
      }
    }
  });
}

function _collectToolData(toolId) {
  const credentials = {};
  const settings = {};

  if (toolId === 'market_research_seo') {
    const key = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-cred-search-key'))?.value.trim();
    if (key) credentials.search_api_key = key;

    const seeds = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-seed-keywords'))?.value.trim();
    if (seeds) settings.seed_keywords = seeds.split(',').map((s) => s.trim()).filter(Boolean);

    const comps = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-competitors'))?.value.trim();
    if (comps) settings.competitor_urls = comps.split(',').map((s) => s.trim()).filter(Boolean);

  } else if (toolId === 'seo_landing_injector') {
    const domain = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-domain'))?.value.trim();
    if (domain) settings.domain_url = domain;

    settings.generate_landing_html = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-gen-landing'))?.checked ?? true;
    settings.generate_sitemap_robots = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-gen-sitemap'))?.checked ?? true;

    const ga = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-cred-ga'))?.value.trim();
    if (ga) credentials.google_analytics_id = ga;

    const gtm = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-cred-gtm'))?.value.trim();
    if (gtm) credentials.gtm_id = gtm;

    const meta = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-cred-meta'))?.value.trim();
    if (meta) credentials.meta_pixel_id = meta;

    const tiktok = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-cred-tiktok'))?.value.trim();
    if (tiktok) credentials.tiktok_pixel_id = tiktok;

  } else if (toolId === 'email_campaign_manager') {
    const provider = /** @type {HTMLSelectElement|null} */ ($id('mkt-tool-set-email-provider'))?.value;
    if (provider) settings.email_provider = provider;

    const mode = /** @type {HTMLSelectElement|null} */ ($id('mkt-tool-set-send-mode'))?.value;
    if (mode) settings.send_mode = mode;

    const email = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-sender-email'))?.value.trim();
    if (email) settings.sender_email = email;

    const name = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-sender-name'))?.value.trim();
    if (name) settings.sender_name = name;

    const recs = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-recipient-list'))?.value.trim();
    if (recs) settings.recipient_list = recs.split(',').map((s) => s.trim()).filter(Boolean);

    const key = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-cred-email-key'))?.value.trim();
    if (key) credentials.email_api_key = key;

  } else if (toolId === 'social_ads_publisher') {
    const fmts = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-formats'))?.value.trim();
    if (fmts) settings.formats = fmts.split(',').map((s) => s.trim()).filter(Boolean);

    const plats = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-set-platforms'))?.value.trim();
    if (plats) settings.target_platforms = plats.split(',').map((s) => s.trim()).filter(Boolean);

    const webhook = /** @type {HTMLInputElement|null} */ ($id('mkt-tool-cred-webhook'))?.value.trim();
    if (webhook) credentials.webhook_url = webhook;
  }

  return { credentials, settings };
}

function _collectFullMarketingProfile() {
  const pid = _currentProjectId || _getEffectiveProjectId();
  if (!pid) return null;

  const statusBtn = $id('btn-mkt-toggle-status');
  const marketingEnabled = statusBtn ? statusBtn.classList.contains('active') : true;

  const presetSel = /** @type {HTMLSelectElement|null} */ ($id('mkt-strategy-preset'));
  const brandVoiceInput = /** @type {HTMLInputElement|null} */ ($id('mkt-brand-voice'));
  const targetAudienceInput = /** @type {HTMLInputElement|null} */ ($id('mkt-target-audience'));
  const langSel = /** @type {HTMLSelectElement|null} */ ($id('mkt-language'));
  const growthCheck = /** @type {HTMLInputElement|null} */ ($id('mkt-include-growth'));
  const salesCheck = /** @type {HTMLInputElement|null} */ ($id('mkt-include-sales'));

  // Collect channels
  const channels = [];
  document.querySelectorAll('.mkt-channel-card').forEach((card) => {
    const chId = /** @type {HTMLElement} */ (card).dataset.channelId;
    if (!chId) return;

    const chk = /** @type {HTMLInputElement|null} */ (card.querySelector('.mkt-ch-enable'));
    const handleInput = /** @type {HTMLInputElement|null} */ (card.querySelector('.mkt-ch-handle'));
    const credInput = /** @type {HTMLInputElement|null} */ (card.querySelector('.mkt-ch-cred'));
    const instInput = /** @type {HTMLTextAreaElement|null} */ (card.querySelector('.mkt-ch-inst'));

    const credVal = credInput?.value.trim() || '';
    const credentials = {};
    if (credVal) {
      if (credVal.startsWith('http://') || credVal.startsWith('https://')) {
        credentials.webhook_url = credVal;
      } else {
        credentials.token = credVal;
      }
    }

    channels.push({
      channel_id: chId,
      name: MARKETING_CHANNELS_META[chId]?.name || chId,
      enabled: chk ? chk.checked : false,
      account_handle_or_url: handleInput?.value.trim() || '',
      credentials,
      custom_instructions: instInput?.value.trim() || '',
    });
  });

  // Collect tools
  const tools = [];
  ['market_research_seo', 'seo_landing_injector', 'email_campaign_manager', 'social_ads_publisher'].forEach((toolId) => {
    const card = document.querySelector(`.mkt-tool-card[data-tool-id="${toolId}"]`);
    const isEnabled = card ? Boolean(/** @type {HTMLInputElement|null} */ (card.querySelector('.mkt-tool-enable'))?.checked) : true;
    const { credentials, settings } = _collectToolData(toolId);

    tools.push({
      tool_id: toolId,
      name: MARKETING_TOOLS_META[toolId]?.title || toolId,
      description: MARKETING_TOOLS_META[toolId]?.desc || '',
      enabled: isEnabled,
      credentials,
      settings,
      is_configured: true,
    });
  });

  return {
    project_id: pid,
    project_name: _currentMarketingProfile?.project_name || pid,
    marketing_enabled: marketingEnabled,
    include_growth_agent: growthCheck ? growthCheck.checked : true,
    include_sales_analytics_agent: salesCheck ? salesCheck.checked : true,
    marketing_type: presetSel?.value || 'saas_b2b',
    brand_voice: brandVoiceInput?.value.trim() || 'persuasivo-profesional',
    target_audience: targetAudienceInput?.value.trim() || '',
    language: langSel?.value || 'es',
    channels,
    tools,
  };
}

function _initMarketingTabEvents() {
  if (_marketingEventsInitialized) return;
  _marketingEventsInitialized = true;

  // Project selector change
  $id('mkt-project-select')?.addEventListener('change', (e) => {
    const pid = /** @type {HTMLSelectElement} */ (e.target).value;
    if (pid) {
      _currentProjectId = pid;
      _loadMarketingTab();
    }
  });

  // Master switch toggle
  $id('btn-mkt-toggle-status')?.addEventListener('click', () => {
    const statusBtn = $id('btn-mkt-toggle-status');
    if (!statusBtn) return;
    const currentlyActive = statusBtn.classList.contains('active');
    if (currentlyActive) {
      statusBtn.className = 'pixel-btn mkt-status-btn disabled';
      statusBtn.textContent = '🔴 MARKETING DESACTIVADO';
      statusBtn.title = 'Haz clic para activar marketing en este proyecto';
    } else {
      statusBtn.className = 'pixel-btn mkt-status-btn active';
      statusBtn.textContent = '🟢 MARKETING ACTIVADO';
      statusBtn.title = 'Haz clic para desactivar marketing en este proyecto';
    }
  });

  // Apply preset button
  $id('btn-mkt-apply-preset')?.addEventListener('click', async () => {
    const pid = _currentProjectId || _getEffectiveProjectId();
    const presetSel = /** @type {HTMLSelectElement|null} */ ($id('mkt-strategy-preset'));
    const preset = presetSel?.value || 'saas_b2b';
    if (!pid) return;

    const btn = $id('btn-mkt-apply-preset');
    if (btn) btn.textContent = '⏳...';

    try {
      const updated = await API.applyProjectMarketingPreset(pid, preset);
      _currentMarketingProfile = updated;
      _renderMarketingProfile(_currentMarketingProfile);

      const feedback = $id('mkt-execution-feedback');
      if (feedback) {
        feedback.className = 'mkt-feedback-banner success';
        feedback.textContent = `✅ Preset "${preset}" aplicado con éxito a las herramientas y canales.`;
        feedback.classList.remove('hidden');
      }
    } catch (err) {
      const feedback = $id('mkt-execution-feedback');
      if (feedback) {
        feedback.className = 'mkt-feedback-banner error';
        feedback.textContent = `Error al aplicar preset: ${err.message || err}`;
        feedback.classList.remove('hidden');
      }
    } finally {
      if (btn) btn.textContent = 'APLICAR';
    }
  });

  // Execute marketing now button
  $id('btn-mkt-execute-now')?.addEventListener('click', async () => {
    const pid = _currentProjectId || _getEffectiveProjectId();
    if (!pid) return;

    const execBtn = /** @type {HTMLButtonElement|null} */ ($id('btn-mkt-execute-now'));
    const feedback = $id('mkt-execution-feedback');

    if (execBtn) {
      execBtn.disabled = true;
      execBtn.textContent = '⏳ EJECUTANDO MARKETING...';
    }
    if (feedback) {
      feedback.className = 'mkt-feedback-banner warning';
      feedback.innerHTML = '⚡ Ejecutando herramientas y canales configurados bajo demanda...';
      feedback.classList.remove('hidden');
    }

    try {
      // First save current form changes before executing
      const payload = _collectFullMarketingProfile();
      if (payload) {
        await API.saveProjectMarketingConfig(pid, payload).catch(() => {});
      }

      const res = await API.executeProjectMarketingNow(pid);

      if (feedback) {
        const toolsCount = res.tools_executed?.length || 0;
        const chansCount = res.channels_notified?.length || 0;
        const filesCount = res.generated_files?.length || 0;

        feedback.className = 'mkt-feedback-banner success';
        feedback.innerHTML = `
          <div class="mkt-feedback-title">🚀 ¡MARKETING EJECUTADO CON ÉXITO!</div>
          <div class="mkt-feedback-details">
            <span>🛠️ <strong>${toolsCount}</strong> herramientas ejecutadas</span>
            <span>📡 <strong>${chansCount}</strong> canales configurados</span>
            <span>📁 <strong>${filesCount}</strong> archivos generados</span>
          </div>
          ${filesCount > 0 ? `<div class="mkt-feedback-files">Entregables: ${res.generated_files.map((f) => `<code>${_esc(f)}</code>`).join(' ')}</div>` : ''}
        `;
      }

      // Reload profile to refresh execution timestamp
      _loadMarketingTab();
    } catch (err) {
      if (feedback) {
        feedback.className = 'mkt-feedback-banner error';
        feedback.textContent = `🔴 Error durante la ejecución de marketing: ${err.message || err}`;
      }
    } finally {
      if (execBtn) {
        execBtn.disabled = false;
        execBtn.textContent = '⚡ EJECUTAR MARKETING AHORA';
      }
    }
  });

  // Save marketing profile button
  $id('btn-save-marketing-profile')?.addEventListener('click', async () => {
    const pid = _currentProjectId || _getEffectiveProjectId();
    const saveFeedback = $id('mkt-save-feedback');
    const saveBtn = /** @type {HTMLButtonElement|null} */ ($id('btn-save-marketing-profile'));

    if (!pid) {
      if (saveFeedback) {
        saveFeedback.className = 'mkt-feedback-banner error';
        saveFeedback.textContent = 'No hay un proyecto activo seleccionado.';
        saveFeedback.classList.remove('hidden');
      }
      return;
    }

    const payload = _collectFullMarketingProfile();
    if (!payload) return;

    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = '⏳ GUARDANDO...';
    }

    try {
      const updated = await API.saveProjectMarketingConfig(pid, payload);
      _currentMarketingProfile = updated;

      if (saveFeedback) {
        saveFeedback.className = 'mkt-feedback-banner success';
        saveFeedback.innerHTML = `✅ Configuración de marketing guardada para <strong>${_esc(pid)}</strong>.`;
        saveFeedback.classList.remove('hidden');
        setTimeout(() => {
          saveFeedback.classList.add('hidden');
        }, 4000);
      }
    } catch (err) {
      if (saveFeedback) {
        saveFeedback.className = 'mkt-feedback-banner error';
        saveFeedback.textContent = `Error al guardar: ${err.message || err}`;
        saveFeedback.classList.remove('hidden');
      }
    } finally {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = '💾 GUARDAR CONFIGURACIÓN DE MARKETING';
      }
    }
  });
}

// ── Command Dock & FAB Handlers ───────────────────────────────────────────

function _initDockAndFAB() {
  // 1. Files & Code Button (Top Sub-toolbar or Legacy Dock) -> Opens in General Project Mode
  const filesBtn = $id('btn-top-files') || $id('dock-btn-files');
  filesBtn?.addEventListener('click', () => {
    _openGeneralPanel('files');
  });

  // 2. Chat 1-on-1 Button
  $id('dock-btn-chat')?.addEventListener('click', () => {
    if (_currentAgent) {
      _openPanel(_currentAgent, _getEffectiveProjectId());
      _switchTab('chat');
    } else {
      _openGeneralPanel('chat');
    }
  });

  // 3. Marketing Control Center Button
  $id('dock-btn-marketing')?.addEventListener('click', () => {
    _openGeneralPanel('marketing');
  });

  // 4. Telemetry Drawer Button
  $id('dock-btn-telemetry')?.addEventListener('click', () => {
    const drawer = $id('telemetry-drawer');
    if (drawer) drawer.classList.toggle('hidden');
  });

  // 5. Close Telemetry Drawer
  $id('btn-close-telemetry')?.addEventListener('click', () => {
    $id('telemetry-drawer')?.classList.add('hidden');
  });

  // 6. Brownfield Dock Button
  $id('dock-btn-brownfield')?.addEventListener('click', () => {
    const bfModeBtn = document.querySelector('.mode-btn[data-mode="brownfield"]');
    if (bfModeBtn) {
      bfModeBtn.dispatchEvent(new MouseEvent('click'));
      const repoInput = $id('repo-url-input');
      if (repoInput) {
        repoInput.focus();
        repoInput.scrollIntoView({ behavior: 'smooth' });
      }
    }
  });

  // 7. FAB Quick Chat
  $id('fab-chat')?.addEventListener('click', () => {
    if (_currentAgent) {
      _openPanel(_currentAgent, _getEffectiveProjectId());
      _switchTab('chat');
      $id('chat-input')?.focus();
    } else {
      _openGeneralPanel('chat');
      $id('chat-input')?.focus();
    }
  });
}

// ── Modal ─────────────────────────────────────────────────────────────────

$id('btn-close-modal')?.addEventListener('click', () => {
  $id('modal-overlay')?.classList.add('hidden');
});

// ── Init ──────────────────────────────────────────────────────────────────

/** Initialize the side panel, tabs and chat input. */
export function initPanel() {
  $id('btn-close-panel')?.addEventListener('click', _closePanel);

  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const tab = /** @type {HTMLElement} */ (btn).dataset.tab;
      if (tab) _switchTab(tab);
    });
  });

  // Listen for agent selection events dispatched by office.js
  document.addEventListener('agent:selected', (e) => {
    const { agent, projectId } = /** @type {CustomEvent<{agent: AgentDef, projectId: string|null}>} */ (e).detail;
    _openPanel(agent, projectId);
  });

  // Listen for project selection events dispatched by office.js
  document.addEventListener('project:selected', (e) => {
    _currentProjectId = e.detail?.projectId || null;
    if ($id('side-panel')?.classList.contains('open')) {
      _updatePanelHeader();
      _loadTabContent(_activeTab);
    }
  });

  // Listen for marketing configure events dispatched by office.js
  document.addEventListener('marketing:configure', (e) => {
    const pid = /** @type {CustomEvent<{projectId: string|null}>} */ (e).detail?.projectId;
    if (pid) _currentProjectId = pid;
    _openGeneralPanel('marketing');
  });

  _initChatInput();
  _initDockAndFAB();
  _initModelsTabEvents();
  _initMarketingTabEvents();

  // URL Query Parameters support for quick deep linking / automated testing
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('open_files') === '1') {
    _openGeneralPanel('files');
  } else if (urlParams.get('open_logs') === '1') {
    _openGeneralPanel('logs');
  } else if (urlParams.get('open_marketing') === '1') {
    _openGeneralPanel('marketing');
  } else if (urlParams.get('open_agent')) {
    const agId = urlParams.get('open_agent');
    const ag = AGENTS.find((a) => a.id === agId);
    if (ag) _openPanel(ag, _getEffectiveProjectId());
  } else if (urlParams.get('open_edit') === '1') {
    _openFileEditModal('build/app/Domain/Billing/Services/WalletService.php');
  }
}
