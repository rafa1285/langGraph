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

  // Activate tab (default to current active or chat)
  _switchTab(_activeTab || 'chat');
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

  // 3. Telemetry Drawer Button
  $id('dock-btn-telemetry')?.addEventListener('click', () => {
    const drawer = $id('telemetry-drawer');
    if (drawer) drawer.classList.toggle('hidden');
  });

  // 4. Close Telemetry Drawer
  $id('btn-close-telemetry')?.addEventListener('click', () => {
    $id('telemetry-drawer')?.classList.add('hidden');
  });

  // 5. Brownfield Dock Button
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

  // 6. FAB Quick Chat
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

  _initChatInput();
  _initDockAndFAB();

  // URL Query Parameters support for quick deep linking / automated testing
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('open_files') === '1') {
    _openGeneralPanel('files');
  } else if (urlParams.get('open_logs') === '1') {
    _openGeneralPanel('logs');
  } else if (urlParams.get('open_agent')) {
    const agId = urlParams.get('open_agent');
    const ag = AGENTS.find((a) => a.id === agId);
    if (ag) _openPanel(ag, _getEffectiveProjectId());
  } else if (urlParams.get('open_edit') === '1') {
    _openFileEditModal('build/app/Domain/Billing/Services/WalletService.php');
  }
}
