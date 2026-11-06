/**
 * api.js — AgentOffice API Client
 * Wraps all backend HTTP + WebSocket communications.
 * @module api
 */

const BASE = ''; // Same origin — served by FastAPI on port 8080

const API = {

  // ── Projects ──────────────────────────────────────────────────────────────

  /**
   * List all factory projects with status and telemetry.
   * @returns {Promise<{total: number, projects: Array<{project_id: string, current_status: string, steps_completed: number, updated_at: string}>}>}
   */
  async listProjects() {
    const r = await fetch(`${BASE}/api/v1/projects`);
    if (!r.ok) throw new Error(`listProjects: HTTP ${r.status}`);
    return r.json();
  },

  /**
   * Create a new Greenfield project from an idea.
   * @param {string} idea
   * @returns {Promise<{project_id: string, status: string}>}
   */
  async createProject(idea) {
    const r = await fetch(`${BASE}/api/v1/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea_inicial: idea }),
    });
    if (!r.ok) {
      const txt = await r.text().catch(() => '');
      throw new Error(`createProject: HTTP ${r.status} — ${txt}`);
    }
    return r.json();
  },

  /**
   * Get project pipeline status and execution history.
   * @param {string} projectId
   * @returns {Promise<{project_id: string, ultimo_agente: string|null, pasos_completados: number, execution_history: Array<{step_number: number, agent_id: string, status: string, timestamp_iso: string}>}>}
   */
  async getProjectStatus(projectId) {
    const r = await fetch(`${BASE}/api/v1/projects/${projectId}/status`);
    if (!r.ok) throw new Error(`getProjectStatus: HTTP ${r.status}`);
    return r.json();
  },

  /**
   * Get all deliverables (documents, code) produced for a project.
   * @param {string} projectId
   * @returns {Promise<Record<string, string>>}
   */
  async getProjectDeliverables(projectId) {
    const r = await fetch(`${BASE}/api/v1/projects/${projectId}/deliverables`);
    if (!r.ok) throw new Error(`getDeliverables: HTTP ${r.status}`);
    return r.json();
  },

  /**
   * Resume a halted project from its last checkpoint.
   * @param {string} projectId
   * @returns {Promise<{project_id: string, status: string}>}
   */
  async resumeProject(projectId) {
    const r = await fetch(`${BASE}/api/v1/projects/${projectId}/resume`, {
      method: 'POST',
    });
    if (!r.ok) throw new Error(`resumeProject: HTTP ${r.status}`);
    return r.json();
  },

  /**
   * Get conversation/LLM prompt history for a project, optionally filtered by agent.
   * @param {string} projectId
   * @param {string|null} [agentId]
   * @returns {Promise<Array<{agent_id: string, prompt: string, response: string, timestamp_iso: string}>>}
   */
  async getConversations(projectId, agentId = null) {
    let url = `${BASE}/api/v1/projects/${projectId}/conversations`;
    if (agentId) url += `?agent_id=${encodeURIComponent(agentId)}`;
    const r = await fetch(url);
    if (!r.ok) return [];
    return r.json();
  },

  /**
   * Get internal office email inbox for a project.
   * @param {string} projectId
   * @returns {Promise<Array<{subject: string, sender: string, recipient: string, body_summary: string}>>}
   */
  async getInbox(projectId) {
    const r = await fetch(`${BASE}/api/v1/projects/${projectId}/inbox`);
    if (!r.ok) return [];
    return r.json();
  },

  // ── Office UI (Phase 2+) ──────────────────────────────────────────────────

  /**
   * Get current visual state for all agents in the office map.
   * Phase 1: returns idle states. Phase 2: live states from AgentStatusService.
   * @returns {Promise<Array<{agent_id: string, name: string, room: string, icon: string, status: string, message: string}>>}
   */
  async getAgentStatuses() {
    try {
      const r = await fetch(`${BASE}/api/v1/office/agents/status`);
      if (r.ok) return r.json();
    } catch (_) { /* Phase 2 endpoint might be unavailable */ }
    return [];
  },

  /**
   * Send a chat message to a specific agent (Phase 3).
   * @param {string} agentId
   * @param {string} message
   * @param {string|null} projectId
   * @param {string} sessionId
   * @returns {Promise<{agent_id: string, response: string, session_id: string}>}
   */
  async sendChatMessage(agentId, message, projectId, sessionId) {
    const r = await fetch(`${BASE}/api/v1/office/chat/${encodeURIComponent(agentId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, project_id: projectId, session_id: sessionId }),
    });
    if (!r.ok) throw new Error(`sendChatMessage: HTTP ${r.status}`);
    return r.json();
  },

  /**
   * Get 1-on-1 direct chat history with an agent (Phase 3).
   * @param {string} agentId
   * @param {string} sessionId
   * @returns {Promise<{session_id: string, agent_id: string, turns: Array<{id: string, role: string, content: string, created_at: string}>, total: number}>}
   */
  async getChatHistory(agentId, sessionId) {
    try {
      const r = await fetch(`${BASE}/api/v1/office/chat/${encodeURIComponent(agentId)}/history?session_id=${encodeURIComponent(sessionId)}`);
      if (r.ok) return r.json();
    } catch (_) {}
    return { session_id: sessionId, agent_id: agentId, turns: [], total: 0 };
  },

  // ── Workspace Files & Hot File Edit (Phase 4) ─────────────────────────────

  /**
   * List files within a project workspace.
   * @param {string} projectId
   * @returns {Promise<Array<{path: string, size: number, is_dir: boolean, last_modified: string}>>}
   */
  async getWorkspaceFiles(projectId) {
    const r = await fetch(`${BASE}/api/v1/office/files?project_id=${encodeURIComponent(projectId)}`);
    if (!r.ok) return [];
    return r.json();
  },

  /**
   * Read full content of a workspace file.
   * @param {string} projectId
   * @param {string} filePath
   * @returns {Promise<{project_id: string, file_path: string, content: string, size: number}>}
   */
  async getFileContent(projectId, filePath) {
    const r = await fetch(
      `${BASE}/api/v1/office/files/content?project_id=${encodeURIComponent(projectId)}&file_path=${encodeURIComponent(filePath)}`
    );
    if (!r.ok) throw new Error(`getFileContent: HTTP ${r.status}`);
    return r.json();
  },

  /**
   * Ask an agent to propose modifications to a workspace file.
   * @param {string} agentId
   * @param {string} projectId
   * @param {string} filePath
   * @param {string} instruction
   * @param {string|null} sessionId
   * @returns {Promise<{edit_token: string, agent_id: string, project_id: string, file_path: string, diff: string, explanation: string}>}
   */
  async proposeFileEdit(agentId, projectId, filePath, instruction, sessionId = null) {
    const r = await fetch(`${BASE}/api/v1/office/chat/${encodeURIComponent(agentId)}/file-edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        file_path: filePath,
        instruction,
        session_id: sessionId,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `proposeFileEdit: HTTP ${r.status}`);
    }
    return r.json();
  },

  /**
   * Confirm and apply a proposed file edit to disk.
   * @param {string} editToken
   * @returns {Promise<{success: boolean, message: string, file_path: string, backup_path: string|null}>}
   */
  async confirmFileEdit(editToken) {
    const r = await fetch(`${BASE}/api/v1/office/chat/file-edit/${encodeURIComponent(editToken)}/confirm`, {
      method: 'POST',
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `confirmFileEdit: HTTP ${r.status}`);
    }
    return r.json();
  },

  /**
   * Reject a proposed file edit.
   * @param {string} editToken
   * @returns {Promise<{success: boolean, message: string}>}
   */
  async rejectFileEdit(editToken) {
    const r = await fetch(`${BASE}/api/v1/office/chat/file-edit/${encodeURIComponent(editToken)}/reject`, {
      method: 'POST',
    });
    if (!r.ok) return { success: false, message: 'Error al rechazar' };
    return r.json();
  },

  // ── Brownfield GitHub Audit (Phase 5) ─────────────────────────────────────

  /**
   * Start read-only brownfield repository diagnosis with CISO & Architect.
   * @param {string} repoUrl
   * @param {string} [branch='main']
   * @param {'surface'|'deep'} [depth='deep']
   * @param {string|null} [authToken=null]
   * @returns {Promise<object>}
   */
  async startBrownfieldAudit(repoUrl, branch = 'main', depth = 'deep', authToken = null) {
    const r = await fetch(`${BASE}/api/v1/office/brownfield/audit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_url: repoUrl,
        branch,
        depth,
        auth_token: authToken,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `startBrownfieldAudit: HTTP ${r.status}`);
    }
    return r.json();
  },

  /**
   * Get executive audit report for a brownfield project.
   * @param {string} projectId
   * @returns {Promise<object>}
   */
  async getBrownfieldAudit(projectId) {
    const r = await fetch(`${BASE}/api/v1/office/brownfield/${encodeURIComponent(projectId)}/audit`);
    if (!r.ok) throw new Error(`getBrownfieldAudit: HTTP ${r.status}`);
    return r.json();
  },

  /**
   * Approve brownfield audit and begin refactoring pipeline.
   * @param {string} projectId
   * @param {string[]} scope
   * @param {string|null} [refactorPrompt=null]
   * @returns {Promise<{project_id: string, status: string, message: string}>}
   */
  async approveBrownfieldAudit(projectId, scope = ['security', 'architecture'], refactorPrompt = null) {
    const r = await fetch(`${BASE}/api/v1/office/brownfield/${encodeURIComponent(projectId)}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope, refactor_prompt: refactorPrompt }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `approveBrownfieldAudit: HTTP ${r.status}`);
    }
    return r.json();
  },

  /**
   * Reject brownfield audit.
   * @param {string} projectId
   * @returns {Promise<{project_id: string, status: string, message: string}>}
   */
  async rejectBrownfieldAudit(projectId) {
    const r = await fetch(`${BASE}/api/v1/office/brownfield/${encodeURIComponent(projectId)}/reject`, {
      method: 'POST',
    });
    if (!r.ok) throw new Error(`rejectBrownfieldAudit: HTTP ${r.status}`);
    return r.json();
  },

  // ── WebSocket ─────────────────────────────────────────────────────────────

  /**
   * Connect to the real-time event stream for a specific project.
   * @param {string} projectId
   * @param {(data: object) => void} onMessage
   * @returns {WebSocket}
   */
  connectProjectWS(projectId, onMessage) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws/projects/${projectId}`);
    ws.addEventListener('message', (e) => {
      try { onMessage(JSON.parse(e.data)); } catch (_) {}
    });
    return ws;
  },

  /**
   * Connect to the global office event stream (Phase 2 — fails silently if not available).
   * @param {(data: object) => void} onMessage
   * @returns {WebSocket|null}
   */
  connectOfficeWS(onMessage) {
    try {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${location.host}/ws/office/global`);
      ws.addEventListener('message', (e) => {
        try { onMessage(JSON.parse(e.data)); } catch (_) {}
      });
      ws.addEventListener('error', () => { /* silent — Phase 2 feature */ });
      return ws;
    } catch (_) {
      return null;
    }
  },
};

export default API;
