/**
 * panel.js — AgentOffice Side Panel Manager
 * Controls the agent interaction panel (Chat | Logs | Files tabs).
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

/** @type {AgentDef|null} */
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
let _activeTab = 'chat';

// ── DOM helpers ───────────────────────────────────────────────────────────

/** @param {string} id @returns {HTMLElement|null} */
const $id = (id) => document.getElementById(id);

// ── Panel Open / Close ────────────────────────────────────────────────────

/**
 * Open the side panel for the selected agent.
 * @param {AgentDef} agent
 * @param {string|null} projectId
 */
function _openPanel(agent, projectId) {
  _currentAgent    = agent;
  _currentProjectId = projectId;
  _sessionId       = _getSessionId(agent.id); // keep persistent session per agent

  // Update header
  const iconEl = $id('panel-agent-icon');
  if (iconEl) iconEl.textContent = agent.icon;

  const nameEl = $id('panel-agent-name');
  if (nameEl) nameEl.textContent = agent.fullName.toUpperCase();

  const roleEl = $id('panel-agent-role');
  if (roleEl) roleEl.textContent = agent.description ?? '';

  // Apply agent accent colour
  const panel = $id('side-panel');
  if (panel) {
    panel.style.setProperty('--panel-accent', agent.color);
    panel.classList.remove('hidden');
    panel.classList.add('open');
  }

  // Ensure Chat tab is immediately active and input focused
  _switchTab('chat');
  setTimeout(() => {
    const input = $id('chat-input');
    if (input) {
      input.focus();
    }
  }, 100);
}

function _closePanel() {
  const panel = $id('side-panel');
  if (panel) {
    panel.classList.remove('open');
    panel.classList.add('hidden');
  }
  document.querySelectorAll('.workstation').forEach((el) => el.classList.remove('selected'));
  document.querySelectorAll('.agent-avatar').forEach((el) => el.classList.remove('selected'));
  _currentAgent     = null;
  _currentProjectId = null;
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
  if (!_currentAgent) return;
  if (tabName === 'chat')  _loadChatHistory();
  if (tabName === 'logs')  _loadLogs();
  if (tabName === 'files') _loadFiles();
}

// ── Helpers ───────────────────────────────────────────────────────────────

/** @param {string} s @returns {string} */
function _esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/** @param {string} s @param {number} max @returns {string} */
function _truncate(s, max) {
  return s.length > max ? `${s.slice(0, max)}\u2026` : s;
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

/** @param {HTMLElement} el @param {string} html */
function _setPlaceholder(el, icon, text, hint = '') {
  el.innerHTML = `
    <div class="chat-placeholder">
      <div class="placeholder-icon">${icon}</div>
      <div>${_esc(text)}</div>
      ${hint ? `<div class="placeholder-hint">${_esc(hint)}</div>` : ''}
    </div>`;
}

// ── Chat Tab ──────────────────────────────────────────────────────────────

function _loadChatHistory() {
  const chatEl = $id('chat-messages');
  if (!chatEl || !_currentAgent) return;

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
      if (_currentProjectId) {
        return API.getConversations(_currentProjectId, _currentAgent.id).then((convs) => {
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
  if (!logsEl || !_currentAgent) return;

  if (!_currentProjectId) {
    _setPlaceholder(logsEl, '📋', 'Selecciona un proyecto activo para ver el historial de ejecución.');
    return;
  }

  logsEl.innerHTML = '<div class="loading-pixel">CARGANDO LOGS...</div>';

  API.getProjectStatus(_currentProjectId)
    .then((status) => {
      logsEl.innerHTML = '';
      const history = status.execution_history ?? [];
      if (history.length === 0) {
        _setPlaceholder(logsEl, '📂', 'Sin historial de ejecución disponible aún.');
        return;
      }
      history.forEach((step) => {
        const isMe = step.agent_id === _currentAgent?.id;
        const el = document.createElement('div');
        el.className = `log-entry${isMe ? ' log-highlight' : ''}`;
        el.innerHTML = `
          <div class="log-step">#${step.step_number}</div>
          <div class="log-agent${isMe ? ' active' : ''}">${_esc(step.agent_id)}</div>
          <div class="log-status">${_esc(step.status)}</div>
          <div class="log-time">${new Date(step.timestamp_iso).toLocaleTimeString('es-ES')}</div>`;
        logsEl.appendChild(el);
      });
    })
    .catch((err) => {
      logsEl.innerHTML = `<div class="error-pixel">ERROR: ${_esc(String(err))}</div>`;
    });
}

// ── Files Tab ─────────────────────────────────────────────────────────────

/** @type {Array<{key: string, label: string}>} */
const _DELIVERABLE_SECTIONS = [
  { key: 'ceo_charter',          label: '📄 CEO Charter' },
  { key: 'pre_sdd_doc',          label: '📄 Pre-SDD' },
  { key: 'sdd_arquitectura',     label: '🏛 SDD Arquitectura' },
  { key: 'ui_ux_spec',           label: '🎨 UI/UX Spec' },
  { key: 'codigo_php',           label: '🐘 Código PHP' },
  { key: 'codigo_python',        label: '⚡ Código Python' },
  { key: 'reporte_qa_php',       label: '🔬 Reporte QA PHP' },
  { key: 'reporte_qa_python',    label: '🐍 Reporte QA Python' },
  { key: 'infraestructura_docker', label: '⚙ Docker Infra' },
  { key: 'dictamen_ciso',        label: '🛡 Dictamen CISO' },
  { key: 'documentacion_rag',    label: '📚 Docs & RAG' },
  { key: 'estrategia_growth',    label: '📈 Growth Strategy' },
  { key: 'marketing_spec',       label: '📣 Marketing Spec' },
  { key: 'sales_analytics_spec', label: '💹 Sales Analytics' },
  { key: 'ceo_signoff',          label: '✅ CEO Sign-off' },
];

function _loadFiles() {
  const filesTree  = $id('files-tree');
  const filesLabel = $id('files-project-label');
  if (!filesTree) return;

  if (!_currentProjectId) {
    _setPlaceholder(filesTree, '📁', 'Selecciona un proyecto activo para explorar sus entregables y archivos.');
    return;
  }
  if (filesLabel) filesLabel.textContent = `📁 ${_currentProjectId}`;

  filesTree.innerHTML = '<div class="loading-pixel">CARGANDO ARCHIVOS Y ENTREGABLES...</div>';

  Promise.all([
    API.getProjectDeliverables(_currentProjectId).catch(() => ({})),
    API.getWorkspaceFiles(_currentProjectId).catch(() => []),
  ])
    .then(([delivs, wsFiles]) => {
      filesTree.innerHTML = '';
      let count = 0;

      // 1. Deliverables
      _DELIVERABLE_SECTIONS.forEach(({ key, label }) => {
        const content = /** @type {string|undefined} */ (/** @type {any} */ (delivs)[key]);
        if (!content || content.trim() === '') return;
        count++;

        const item = document.createElement('div');
        item.className = 'file-item';
        const kb = (content.length / 1024).toFixed(1);
        item.innerHTML = `<span>${label}</span><span class="file-size">${kb} KB</span>`;
        item.addEventListener('click', () => {
          document.querySelectorAll('.file-item').forEach((el) => el.classList.remove('active'));
          item.classList.add('active');
          _showFileContent(label, content);
        });
        filesTree.appendChild(item);
      });

      // 2. Workspace code files
      if (wsFiles && wsFiles.length > 0) {
        const sep = document.createElement('div');
        sep.className = 'files-section-label';
        sep.style.cssText = 'padding:6px 8px;font-size:6px;color:var(--text-dim);border-top:1px solid var(--border);margin-top:6px;';
        sep.textContent = '── CÓDIGO EN WORKSPACE ──';
        filesTree.appendChild(sep);

        wsFiles.forEach((file) => {
          count++;
          const item = document.createElement('div');
          item.className = 'file-item';
          const kb = (file.size / 1024).toFixed(1);
          item.innerHTML = `<span>📄 ${_esc(file.path)}</span><span class="file-size">${kb} KB</span>`;
          item.addEventListener('click', () => {
            document.querySelectorAll('.file-item').forEach((el) => el.classList.remove('active'));
            item.classList.add('active');
            API.getFileContent(_currentProjectId, file.path)
              .then((res) => {
                _showFileContent(`📄 ${file.path}`, res.content, file.path);
              })
              .catch((err) => {
                _showFileContent(`📄 ${file.path}`, `Error al leer archivo: ${err}`);
              });
          });
          filesTree.appendChild(item);
        });
      }

      if (count === 0) {
        _setPlaceholder(
          filesTree,
          '⏳',
          'Sin archivos ni entregables aún.',
          'Lanza un proyecto o pide a un agente crear un archivo nuevo.'
        );
      }
    })
    .catch((err) => {
      filesTree.innerHTML = `<div class="error-pixel">ERROR: ${_esc(String(err))}</div>`;
    });
}

/**
 * Display file content in the viewer with optional edit button.
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
    header.innerHTML = `<span>${_esc(label)}</span>`;
    if (filePath && _currentAgent) {
      const editBtn = document.createElement('button');
      editBtn.className = 'pixel-btn icon';
      editBtn.style.cssText = 'font-size:6px;padding:3px 6px;margin-left:auto;';
      editBtn.textContent = '✏ EDITAR';
      editBtn.title = `Editar este archivo con ${_currentAgent.name}`;
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

// ── File Edit Modal (Phase 4) ─────────────────────────────────────────────

/**
 * Convert unified diff text into styled HTML lines.
 * @param {string} diffText
 * @returns {string}
 */
function _renderDiffHtml(diffText) {
  const lines = diffText.split('\n');
  return lines
    .map((line) => {
      if (line.startsWith('+') && !line.startsWith('+++')) {
        return `<span class="diff-line-add">${_esc(line)}</span>`;
      }
      if (line.startsWith('-') && !line.startsWith('---')) {
        return `<span class="diff-line-del">${_esc(line)}</span>`;
      }
      if (line.startsWith('@@')) {
        return `<span class="diff-line-info">${_esc(line)}</span>`;
      }
      return `<span>${_esc(line)}</span>`;
    })
    .join('\n');
}

/**
 * Open interactive hot file edit modal for the currently selected agent.
 * @param {string} [initialFilePath='']
 */
async function _openFileEditModal(initialFilePath = '') {
  if (!_currentAgent) return;
  const overlay = $id('modal-overlay');
  const titleEl = $id('modal-title');
  const bodyEl  = $id('modal-body');
  const footEl  = $id('modal-footer');
  if (!overlay || !titleEl || !bodyEl || !footEl) return;

  titleEl.textContent = `✏ EDITAR ARCHIVO — ${_currentAgent.name.toUpperCase()}`;

  let fileOptionsHtml = '<option value="">-- Selecciona archivo existente o escribe abajo --</option>';
  if (_currentProjectId) {
    try {
      const files = await API.getWorkspaceFiles(_currentProjectId);
      files.forEach((f) => {
        const sel = f.path === initialFilePath ? 'selected' : '';
        const kb = (f.size / 1024).toFixed(1);
        fileOptionsHtml += `<option value="${_esc(f.path)}" ${sel}>${_esc(f.path)} (${kb} KB)</option>`;
      });
    } catch (_) {}
  }

  bodyEl.innerHTML = `
    <div id="fe-form">
      <div class="form-group">
        <label>PROYECTO:</label>
        <input id="fe-project-id" class="pixel-input" value="${_esc(_currentProjectId || '')}" placeholder="ID del proyecto (ej: proj_123)">
      </div>
      <div class="form-group">
        <label>ARCHIVOS DEL WORKSPACE:</label>
        <select id="fe-file-select" class="pixel-input" style="margin-bottom:6px;">${fileOptionsHtml}</select>
        <label>O RUTA RELATIVA:</label>
        <input id="fe-file-path" class="pixel-input" value="${_esc(initialFilePath)}" placeholder="ej: app/main.py">
      </div>
      <div class="form-group">
        <label>INSTRUCCIONES PARA ${_esc(_currentAgent.fullName.toUpperCase())}:</label>
        <textarea id="fe-instructions" class="pixel-input" rows="4" placeholder="Describe qué cambios, refactorización o corrección deseas realizar..."></textarea>
      </div>
    </div>
    <div id="fe-result" class="hidden">
      <div id="fe-explanation" style="margin-bottom:8px;color:var(--text-bright);font-weight:bold;"></div>
      <div class="diff-container" id="fe-diff-content"></div>
    </div>
  `;

  footEl.innerHTML = `
    <button id="fe-btn-cancel" class="pixel-btn secondary">CANCELAR</button>
    <button id="fe-btn-propose" class="pixel-btn primary">PROPORNER CAMBIO ▶</button>
  `;

  overlay.classList.remove('hidden');

  const fileSelect = /** @type {HTMLSelectElement|null} */ ($id('fe-file-select'));
  const filePathInput = /** @type {HTMLInputElement|null} */ ($id('fe-file-path'));
  if (fileSelect && filePathInput) {
    fileSelect.addEventListener('change', () => {
      if (fileSelect.value) filePathInput.value = fileSelect.value;
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
        _currentAgent.id, proj, filePath, instruction, _sessionId
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
    if (!msg || !_currentAgent) return;

    // Append user bubble immediately
    const chatEl = $id('chat-messages');
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

    try {
      const resp = await API.sendChatMessage(
        _currentAgent.id, msg, _currentProjectId, _sessionId,
      );
      if (chatEl) {
        const agentMsg = document.createElement('div');
        agentMsg.className = 'chat-message agent';
        agentMsg.innerHTML = `
          <div class="msg-role" style="color:var(--panel-accent)">${_currentAgent.icon} ${_currentAgent.name.toUpperCase()}</div>
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

  // ✏ File Edit (Phase 4)
  $id('btn-file-edit')?.addEventListener('click', () => {
    if (!_currentAgent) {
      alert('Selecciona un agente primero haciendo clic en su despacho o avatar.');
      return;
    }
    _openFileEditModal();
  });
}

// ── Command Dock & FAB Handlers ───────────────────────────────────────────

function _initDockAndFAB() {
  // 1. Files & Code Button
  $id('dock-btn-files')?.addEventListener('click', () => {
    if (!_currentAgent && AGENTS.length > 0) {
      _currentAgent = AGENTS[0];
    }
    const sidePanel = $id('side-panel');
    if (sidePanel) {
      sidePanel.classList.remove('hidden');
      sidePanel.classList.add('open');
    }
    _switchTab('files');
  });

  // 2. Chat 1-on-1 Button
  $id('dock-btn-chat')?.addEventListener('click', () => {
    if (!_currentAgent && AGENTS.length > 0) {
      _currentAgent = AGENTS[0];
    }
    const sidePanel = $id('side-panel');
    if (sidePanel) {
      sidePanel.classList.remove('hidden');
      sidePanel.classList.add('open');
    }
    _switchTab('chat');
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
    if (!_currentAgent && AGENTS.length > 0) {
      _currentAgent = AGENTS[0];
    }
    const sidePanel = $id('side-panel');
    if (sidePanel) {
      sidePanel.classList.remove('hidden');
      sidePanel.classList.add('open');
    }
    _switchTab('chat');
    $id('chat-input')?.focus();
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

  _initChatInput();
  _initDockAndFAB();
}
