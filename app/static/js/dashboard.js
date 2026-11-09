/**
 * 🏢 AgentOffice — Operations & Telemetry Dashboard Engine
 * Real-time monitoring, live thoughts stream, agent stats, cost analysis,
 * circuit breaker governance, SQLite table inspector, and artifacts browser.
 */

(function () {
  'use strict';

  // State
  let soundEnabled = true;
  let activeFilter = 'all';
  let allActivityEvents = [];
  let currentThoughts = [];
  let availableProjects = [];

  // DOM Elements - Top Status Bar
  const kpiProjects = document.getElementById('kpi-projects');
  const kpiTokens = document.getElementById('kpi-tokens');
  const kpiCost = document.getElementById('kpi-cost');
  const kpiToday = document.getElementById('kpi-today');
  const kpiSaved = document.getElementById('kpi-saved');
  const kpiHealth = document.getElementById('kpi-health');
  const kpiAgents = document.getElementById('kpi-agents');
  const clockEl = document.getElementById('live-clock');
  const soundBtn = document.getElementById('sound-toggle-btn');

  // --- 1. Real-Time Clock & Sound Toggle ---
  function updateClock() {
    if (!clockEl) return;
    const now = new Date();
    clockEl.textContent = now.toTimeString().split(' ')[0];
  }
  setInterval(updateClock, 1000);
  updateClock();

  if (soundBtn) {
    soundBtn.addEventListener('click', () => {
      soundEnabled = !soundEnabled;
      soundBtn.textContent = soundEnabled ? '🔊' : '🔇';
      soundBtn.title = soundEnabled ? 'Silenciar Notificaciones' : 'Activar Sonido';
    });
  }

  // --- 2. Tab Navigation System ---
  const navTabs = document.querySelectorAll('.nav-tab');
  const tabPanes = document.querySelectorAll('.tab-pane');

  function switchTab(targetId) {
    navTabs.forEach(tab => {
      const isTarget = tab.getAttribute('data-target') === targetId;
      if (isTarget) {
        tab.classList.add('border-cyan-400', 'text-cyan-400', 'bg-slate-800/80', 'font-semibold');
        tab.classList.remove('border-transparent', 'text-slate-400');
      } else {
        tab.classList.remove('border-cyan-400', 'text-cyan-400', 'bg-slate-800/80', 'font-semibold');
        tab.classList.add('border-transparent', 'text-slate-400');
      }
    });

    tabPanes.forEach(pane => {
      if (pane.id === targetId) {
        pane.classList.remove('hidden');
      } else {
        pane.classList.add('hidden');
      }
    });

    // Lazy load or refresh data when opening specific tabs
    if (targetId === 'tab-thoughts') loadThoughts();
    if (targetId === 'tab-usage') loadAgentStats();
    if (targetId === 'tab-tokens') loadCostBreakdown();
    if (targetId === 'tab-security') loadSecurityStatus();
    if (targetId === 'tab-database') {
      loadDatabaseTable();
      loadArtifactsProjectSelector();
    }
  }

  navTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-target');
      if (target) {
        window.location.hash = target;
        switchTab(target);
      }
    });
  });

  // Deep linking: activate tab from URL query param (e.g. ?tab=tab-thoughts) or hash (e.g. #tab-thoughts)
  const urlParamTab = new URLSearchParams(window.location.search).get('tab');
  const hashTab = window.location.hash ? window.location.hash.replace('#', '') : null;
  const initialTarget = urlParamTab || hashTab;
  if (initialTarget && document.getElementById(initialTarget)) {
    switchTab(initialTarget);
  }

  // --- 3. Telemetry KPIs Engine (Real-Time Backend Polling) ---
  async function fetchKpis() {
    try {
      const resp = await fetch('/api/dashboard/telemetry');
      if (!resp.ok) return;
      const data = await resp.json();

      if (kpiProjects) kpiProjects.textContent = data.projects.toString();
      if (kpiTokens) kpiTokens.textContent = data.tokens.toLocaleString();
      if (kpiCost) kpiCost.textContent = data.cost;
      if (kpiToday) kpiToday.textContent = data.today;
      if (kpiSaved) kpiSaved.textContent = data.saved;
      if (kpiHealth) {
        kpiHealth.textContent = `${data.health_score}%`;
        kpiHealth.className = data.health_score >= 80 ? 'text-emerald-400 font-semibold' : 'text-amber-400 font-semibold';
      }
      if (kpiAgents) {
        kpiAgents.textContent = data.agents_ready_str;
      }
    } catch (err) {
      console.warn('Error fetching telemetry KPIs:', err);
    }
  }

  // Initial fetch and poll every 4 seconds
  fetchKpis();
  setInterval(fetchKpis, 4000);

  // --- 4. Tab 2: Interaction & Pipeline Component ---
  const projectSelect = document.getElementById('dash-interaction-project-select') || document.getElementById('project-select');
  const projectIdeaInput = document.getElementById('project-idea-input');
  const projectIdInput = document.getElementById('project-id-input');
  const launchBtn = document.getElementById('btn-launch-factory');
  const pipelineInfoText = document.getElementById('pipeline-info-text');
  const pipelineStepCounter = document.getElementById('pipeline-step-counter');
  const activityStream = document.getElementById('activity-log-stream');
  const logEventsCount = document.getElementById('log-events-count');
  const doneCounter = document.getElementById('done-counter');
  const btnClearLogs = document.getElementById('btn-clear-logs');
  const filterBtns = document.querySelectorAll('.filter-btn');

  const STAGE_IDS = [
    'stage-received',
    'stage-ceo-charter',
    'stage-pm-design',
    'stage-coding',
    'stage-qa-ciso',
    'stage-growth-docs',
    'stage-ceo-signoff',
  ];

  function setPipelineStage(activeIdx) {
    STAGE_IDS.forEach((id, idx) => {
      const el = document.getElementById(id);
      if (!el) return;
      const tag = el.querySelector('.status-tag');
      if (idx < activeIdx) {
        el.className = 'pipeline-step flex-1 bg-emerald-950/40 border border-emerald-500/60 rounded-lg p-2.5 flex flex-col items-center text-center';
        if (tag) { tag.textContent = 'DONE'; tag.className = 'text-[10px] text-emerald-400 status-tag font-bold'; }
      } else if (idx === activeIdx) {
        el.className = 'pipeline-step flex-1 bg-cyan-950/70 border border-cyan-400 rounded-lg p-2.5 flex flex-col items-center text-center shadow-lg shadow-cyan-950 animate-pulse';
        if (tag) { tag.textContent = 'ACTIVE'; tag.className = 'text-[10px] text-cyan-300 status-tag font-bold'; }
      } else {
        el.className = 'pipeline-step flex-1 bg-[#0b0f19] border border-[#1f2937] rounded-lg p-2.5 flex flex-col items-center text-center opacity-60';
        if (tag) { tag.textContent = 'PENDING'; tag.className = 'text-[10px] text-slate-500 status-tag'; }
      }
    });

    if (pipelineStepCounter) {
      pipelineStepCounter.textContent = `Paso ${activeIdx + 1}/7`;
    }
  }

  // Load projects list for dropdowns
  async function loadProjectsList() {
    try {
      const resp = await fetch('/api/v1/projects');
      if (!resp.ok) return;
      const data = await resp.json();
      availableProjects = data.projects || [];

      // Populate project-select in Tab 1
      if (projectSelect) {
        const cur = projectSelect.value;
        projectSelect.innerHTML = '<option value="">-- Nuevo Proyecto --</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          opt.textContent = `${p.project_id} (${p.current_status || 'IDLE'})`;
          projectSelect.appendChild(opt);
        });
        if (cur) projectSelect.value = cur;
      }

      // Populate project filters in other tabs
      const thoughtsProjSelect = document.getElementById('thoughts-project-select');
      if (thoughtsProjSelect) {
        const cur = thoughtsProjSelect.value;
        thoughtsProjSelect.innerHTML = '<option value="">Todos los Proyectos</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          opt.textContent = p.project_id;
          thoughtsProjSelect.appendChild(opt);
        });
        if (cur) thoughtsProjSelect.value = cur;
      }

      const artProjSelect = document.getElementById('artifacts-project-select');
      if (artProjSelect) {
        const cur = artProjSelect.value;
        artProjSelect.innerHTML = '<option value="">Selecciona un Proyecto...</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          opt.textContent = p.project_id;
          artProjSelect.appendChild(opt);
        });
        if (cur) artProjSelect.value = cur;
      }
    } catch (err) {
      console.warn('Error loading projects list:', err);
    }
  }

  loadProjectsList();

  // Handle Project Selection in Tab 1
  if (projectSelect) {
    projectSelect.addEventListener('change', async () => {
      const pid = projectSelect.value;
      if (!pid) {
        setPipelineStage(0);
        if (pipelineInfoText) pipelineInfoText.textContent = 'Selecciona un proyecto para cargar su pipeline.';
        return;
      }

      if (pipelineInfoText) pipelineInfoText.textContent = `Monitoreando proyecto: ${pid}`;

      try {
        const statusResp = await fetch(`/api/v1/projects/${pid}/status`);
        if (statusResp.ok) {
          const s = await statusResp.json();
          const steps = s.pasos_completados || 0;
          const stageIdx = Math.min(6, Math.max(0, Math.floor(steps / 2)));
          setPipelineStage(stageIdx);
        }

        // Load project conversations into activity log
        const convResp = await fetch(`/api/v1/telemetry/thoughts?project_id=${pid}&limit=30`);
        if (convResp.ok) {
          const tData = await convResp.json();
          allActivityEvents = (tData.thoughts || []).map(t => {
            let cat = 'response';
            if (t.agent_id.includes('ceo')) cat = 'delegate';
            else if (t.agent_id.includes('qa') || t.agent_id.includes('ciso')) cat = 'tool';
            if (t.verdict === 'APROBADO') cat = 'done';

            return {
              time: t.created_at ? t.created_at.substring(11, 19) : '00:00:00',
              category: cat,
              agent: t.agent_name || t.agent_id,
              msg: t.snippet || t.raw_response.substring(0, 140),
            };
          });
          renderActivityLog();
        }
      } catch (err) {
        console.warn('Error loading project status:', err);
      }
    });
  }

  // Activity Log rendering & filtering
  function renderActivityLog() {
    if (!activityStream) return;
    activityStream.innerHTML = '';

    const filtered = allActivityEvents.filter(ev => {
      if (activeFilter === 'all') return true;
      return ev.category === activeFilter;
    });

    if (logEventsCount) logEventsCount.textContent = `${allActivityEvents.length} events ▼`;
    if (doneCounter) {
      doneCounter.textContent = allActivityEvents.filter(e => e.category === 'done').length.toString();
    }

    if (filtered.length === 0) {
      activityStream.innerHTML = '<div class="text-slate-500 text-center py-4">No hay eventos para el filtro seleccionado.</div>';
      return;
    }

    filtered.forEach(ev => {
      const row = document.createElement('div');
      row.className = 'p-2 rounded bg-[#0b0f19] border border-[#1f2937] flex items-start gap-2 hover:border-slate-600 transition';

      let badgeColor = 'bg-slate-800 text-slate-300 border-slate-700';
      if (ev.category === 'user') badgeColor = 'bg-emerald-950 text-emerald-400 border-emerald-800';
      else if (ev.category === 'tool') badgeColor = 'bg-blue-950 text-blue-400 border-blue-800';
      else if (ev.category === 'response') badgeColor = 'bg-purple-950 text-purple-400 border-purple-800';
      else if (ev.category === 'delegate') badgeColor = 'bg-amber-950 text-amber-400 border-amber-800';
      else if (ev.category === 'done') badgeColor = 'bg-teal-950 text-teal-400 border-teal-800';

      row.innerHTML = `
        <span class="text-slate-500 text-[10px] whitespace-nowrap mt-0.5">[${ev.time}]</span>
        <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold border ${badgeColor} whitespace-nowrap uppercase">${ev.category}</span>
        <span class="text-cyan-400 font-semibold whitespace-nowrap">${ev.agent}</span>
        <span class="text-slate-300 break-all">${escapeHtml(ev.msg)}</span>
      `;
      activityStream.appendChild(row);
    });
  }

  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => {
        b.classList.remove('bg-slate-800', 'text-white', 'border-cyan-500/50');
      });
      btn.classList.add('bg-slate-800', 'text-white', 'border-cyan-500/50');
      activeFilter = btn.getAttribute('data-filter') || 'all';
      renderActivityLog();
    });
  });

  if (btnClearLogs) {
    btnClearLogs.addEventListener('click', () => {
      allActivityEvents = [];
      renderActivityLog();
    });
  }

  // Launch Factory button
  if (launchBtn) {
    launchBtn.addEventListener('click', async () => {
      const idea = projectIdeaInput ? projectIdeaInput.value.trim() : '';
      if (!idea) {
        alert('Por favor describe tu idea de negocio o directriz de software.');
        return;
      }
      launchBtn.disabled = true;
      launchBtn.innerHTML = '<span>⏳ Iniciando...</span>';

      try {
        const resp = await fetch('/api/v1/projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ idea_inicial: idea }),
        });
        if (resp.ok) {
          const res = await resp.json();
          alert(`¡AI Factory lanzada con éxito!\nID de Proyecto: ${res.project_id}`);
          if (projectIdeaInput) projectIdeaInput.value = '';
          await loadProjectsList();
          if (projectSelect) projectSelect.value = res.project_id;
          setPipelineStage(1);
        } else {
          alert('Error al iniciar el proyecto.');
        }
      } catch (err) {
        alert('Error de red al conectar con la fábrica.');
      } finally {
        launchBtn.disabled = false;
        launchBtn.innerHTML = '<span>🚀 Launch Factory</span>';
      }
    });
  }

  // --- 5. Tab 2: Agent Thoughts Stream & Modal Inspector ---
  const thoughtsContainer = document.getElementById('agent-thoughts-stream');
  const thoughtsProjSelect = document.getElementById('thoughts-project-select');
  const thoughtsAgentSelect = document.getElementById('thoughts-agent-select');
  const btnRefreshThoughts = document.getElementById('btn-refresh-thoughts');

  const thoughtModal = document.getElementById('thought-modal');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalAgentTitle = document.getElementById('modal-agent-title');
  const modalProject = document.getElementById('modal-project');
  const modalStep = document.getElementById('modal-step');
  const modalVerdict = document.getElementById('modal-verdict');
  const modalTokens = document.getElementById('modal-tokens');
  const modalSysPrompt = document.getElementById('modal-sys-prompt');
  const modalPayload = document.getElementById('modal-payload');
  const modalResponse = document.getElementById('modal-response');

  if (modalCloseBtn && thoughtModal) {
    modalCloseBtn.addEventListener('click', () => thoughtModal.classList.add('hidden'));
    thoughtModal.addEventListener('click', (e) => {
      if (e.target === thoughtModal) thoughtModal.classList.add('hidden');
    });
  }

  // Populate agent selector for thoughts
  async function populateThoughtsAgentSelect() {
    if (!thoughtsAgentSelect) return;
    try {
      const resp = await fetch('/api/v1/telemetry/agent-stats');
      if (!resp.ok) return;
      const data = await resp.json();
      thoughtsAgentSelect.innerHTML = '<option value="">Todos los Agentes</option>';
      (data.agents || []).forEach(ag => {
        const opt = document.createElement('option');
        opt.value = ag.agent_id;
        opt.textContent = `${ag.icon} ${ag.name}`;
        thoughtsAgentSelect.appendChild(opt);
      });
    } catch (err) {
      console.warn('Error loading agent list for thoughts:', err);
    }
  }
  populateThoughtsAgentSelect();

  async function loadThoughts() {
    if (!thoughtsContainer) return;
    const proj = thoughtsProjSelect ? thoughtsProjSelect.value : '';
    const agent = thoughtsAgentSelect ? thoughtsAgentSelect.value : '';

    let url = '/api/v1/telemetry/thoughts?limit=40';
    if (proj) url += `&project_id=${encodeURIComponent(proj)}`;
    if (agent) url += `&agent_id=${encodeURIComponent(agent)}`;

    try {
      const resp = await fetch(url);
      if (!resp.ok) return;
      const data = await resp.json();
      currentThoughts = data.thoughts || [];

      thoughtsContainer.innerHTML = '';
      if (currentThoughts.length === 0) {
        thoughtsContainer.innerHTML = '<div class="p-6 text-center text-slate-500 font-mono text-xs">No se encontraron pensamientos registrados con los filtros actuales.</div>';
        return;
      }

      currentThoughts.forEach(t => {
        const card = document.createElement('div');
        card.className = 'p-3.5 rounded-lg bg-[#0b0f19] border border-[#1f2937] flex flex-col gap-2 font-mono text-xs hover:border-slate-600 transition';

        let vColor = 'text-emerald-400 bg-emerald-950 border-emerald-800';
        if (t.verdict === 'RECHAZADO') vColor = 'text-red-400 bg-red-950 border-red-800';
        else if (t.verdict === 'OBSERVACIONES') vColor = 'text-amber-400 bg-amber-950 border-amber-800';

        card.innerHTML = `
          <div class="flex items-center justify-between flex-wrap gap-2 border-b border-[#1f2937] pb-2">
            <div class="flex items-center gap-2">
              <span class="text-cyan-400 font-bold">[${t.agent_name || t.agent_id}]</span>
              <span class="text-slate-500 text-[10px]">Paso #${t.step_number}</span>
              <span class="text-slate-500 text-[10px]">(${t.project_id})</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${vColor}">${t.verdict}</span>
              <span class="text-slate-500 text-[10px]">${t.created_at ? t.created_at.substring(11, 19) : ''}</span>
            </div>
          </div>
          <p class="text-slate-300 leading-relaxed">${escapeHtml(t.snippet)}</p>
          <div class="flex items-center justify-between text-[11px] text-slate-500 pt-1">
            <span>Tokens: In ${t.tokens_in} / Out ${t.tokens_out} • ${t.duration_ms}ms</span>
            <button class="btn-inspect-thought text-cyan-400 hover:text-cyan-300 hover:underline font-semibold" data-id="${t.id}">
              🔍 Ver Razonamiento Completo
            </button>
          </div>
        `;
        thoughtsContainer.appendChild(card);
      });

      // Bind inspect buttons
      document.querySelectorAll('.btn-inspect-thought').forEach(btn => {
        btn.addEventListener('click', () => {
          const id = btn.getAttribute('data-id');
          const t = currentThoughts.find(item => item.id === id);
          if (t && thoughtModal) {
            if (modalAgentTitle) modalAgentTitle.textContent = `${t.agent_name} (${t.agent_id}) — Razonamiento`;
            if (modalProject) modalProject.textContent = t.project_id;
            if (modalStep) modalStep.textContent = `#${t.step_number}`;
            if (modalVerdict) modalVerdict.textContent = t.verdict;
            if (modalTokens) modalTokens.textContent = `${t.tokens_in + t.tokens_out} tokens`;
            if (modalSysPrompt) modalSysPrompt.textContent = t.system_prompt || 'N/A';
            if (modalPayload) modalPayload.textContent = t.user_payload || 'N/A';
            if (modalResponse) modalResponse.textContent = t.raw_response || 'N/A';
            thoughtModal.classList.remove('hidden');
          }
        });
      });

    } catch (err) {
      console.warn('Error loading thoughts:', err);
    }
  }

  if (btnRefreshThoughts) btnRefreshThoughts.addEventListener('click', loadThoughts);
  if (thoughtsProjSelect) thoughtsProjSelect.addEventListener('change', loadThoughts);
  if (thoughtsAgentSelect) thoughtsAgentSelect.addEventListener('change', loadThoughts);

  // --- 6. Tab 3: Agent Usage & Stats Component ---
  const statsTotalAgents = document.getElementById('stats-total-agents');
  const statsTotalTasks = document.getElementById('stats-total-tasks');
  const statsAvgLatency = document.getElementById('stats-avg-latency');
  const statsTrippedBreakers = document.getElementById('stats-tripped-breakers');
  const agentStatsGrid = document.getElementById('agent-stats-grid');

  async function loadAgentStats() {
    if (!agentStatsGrid) return;
    try {
      const resp = await fetch('/api/v1/telemetry/agent-stats');
      if (!resp.ok) return;
      const data = await resp.json();
      const agents = data.agents || [];

      let totalTasks = 0;
      let totalLatency = 0;
      let reworkSum = 0;

      agents.forEach(a => {
        totalTasks += a.tasks_count;
        totalLatency += a.avg_duration_ms * a.tasks_count;
        reworkSum += a.rework_count;
      });

      const avgLat = totalTasks > 0 ? (totalLatency / totalTasks / 1000).toFixed(2) : '0.00';

      if (statsTotalAgents) statsTotalAgents.textContent = data.total_agents.toString();
      if (statsTotalTasks) statsTotalTasks.textContent = totalTasks.toLocaleString();
      if (statsAvgLatency) statsAvgLatency.textContent = `${avgLat}s`;
      if (statsTrippedBreakers) statsTrippedBreakers.textContent = `${reworkSum} Reworks`;

      agentStatsGrid.innerHTML = '';
      agents.forEach(ag => {
        const card = document.createElement('div');
        card.className = 'p-3 rounded-lg bg-[#0b0f19] border border-[#1f2937] flex flex-col gap-2 font-mono text-xs hover:border-cyan-500/50 transition';

        card.innerHTML = `
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-1.5 font-bold text-white">
              <span>${ag.icon}</span>
              <span>${ag.name}</span>
            </div>
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-emerald-400 font-semibold border border-slate-700 uppercase">
              ${ag.status}
            </span>
          </div>
          <div class="grid grid-cols-2 gap-1 text-[11px] text-slate-400 pt-1">
            <div>Tareas: <strong class="text-white">${ag.tasks_count}</strong></div>
            <div>Tokens: <strong class="text-cyan-400">${ag.total_tokens.toLocaleString()}</strong></div>
            <div>Latencia: <strong class="text-slate-300">${(ag.avg_duration_ms / 1000).toFixed(2)}s</strong></div>
            <div>Aprobación: <strong class="text-emerald-400">${ag.approval_rate}%</strong></div>
          </div>
          <div class="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden mt-1">
            <div class="bg-cyan-500 h-1.5 rounded-full" style="width: ${ag.approval_rate}%"></div>
          </div>
        `;
        agentStatsGrid.appendChild(card);
      });
    } catch (err) {
      console.warn('Error loading agent stats:', err);
    }
  }

  // --- 7. Tab 4: Token & Cost Monitor Component ---
  const costTokensIn = document.getElementById('cost-tokens-in');
  const costTokensOut = document.getElementById('cost-tokens-out');
  const costTotalUsd = document.getElementById('cost-total-usd');
  const costSavedUsd = document.getElementById('cost-saved-usd');
  const agentCostTbody = document.getElementById('agent-cost-tbody');
  const pricingTiersList = document.getElementById('pricing-tiers-list');

  async function loadCostBreakdown() {
    try {
      const resp = await fetch('/api/v1/telemetry/cost-breakdown');
      if (!resp.ok) return;
      const data = await resp.json();

      if (costTokensIn) costTokensIn.textContent = data.total_tokens_in.toLocaleString();
      if (costTokensOut) costTokensOut.textContent = data.total_tokens_out.toLocaleString();
      if (costTotalUsd) costTotalUsd.textContent = `$${data.total_cost_usd.toFixed(2)}`;
      if (costSavedUsd) costSavedUsd.textContent = `$${data.saved_usd.toFixed(2)}`;

      if (agentCostTbody) {
        agentCostTbody.innerHTML = '';
        (data.by_agent || []).forEach(ag => {
          const tr = document.createElement('tr');
          tr.className = 'hover:bg-slate-900/50';
          tr.innerHTML = `
            <td class="p-2 font-semibold text-white">${ag.name}</td>
            <td class="p-2 text-cyan-400">${ag.tokens.toLocaleString()}</td>
            <td class="p-2">
              <div class="flex items-center gap-2">
                <div class="w-16 bg-slate-900 rounded-full h-1.5 overflow-hidden">
                  <div class="bg-cyan-400 h-1.5" style="width: ${ag.pct_of_total}%"></div>
                </div>
                <span>${ag.pct_of_total}%</span>
              </div>
            </td>
            <td class="p-2 text-amber-400">$${ag.cost_usd.toFixed(3)}</td>
          `;
          agentCostTbody.appendChild(tr);
        });
      }

      if (pricingTiersList) {
        pricingTiersList.innerHTML = '';
        (data.pricing_tiers || []).forEach(tier => {
          const item = document.createElement('div');
          item.className = 'p-3 rounded bg-[#0b0f19] border border-[#1f2937] flex flex-col gap-1';
          item.innerHTML = `
            <div class="flex justify-between items-center">
              <span class="font-bold text-white text-sm">${tier.name} ($${tier.price_usd}/mes)</span>
              <span class="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
                Margen: ${tier.net_margin_pct}%
              </span>
            </div>
            <div class="text-[11px] text-slate-400 flex justify-between">
              <span>Stripe Fee: $${tier.stripe_fee_usd}</span>
              <span>Max COGS: $${tier.max_cogs_usd}</span>
              <span class="text-emerald-400 font-semibold">Zero-Touch Compliant</span>
            </div>
          `;
          pricingTiersList.appendChild(item);
        });
      }
    } catch (err) {
      console.warn('Error loading cost breakdown:', err);
    }
  }

  // --- 8. Tab 5: Security & Circuit Breakers Component ---
  const circuitBreakersContainer = document.getElementById('circuit-breakers-container');
  const securityEventsContainer = document.getElementById('security-events-container');

  async function loadSecurityStatus() {
    try {
      const resp = await fetch('/api/v1/telemetry/security');
      if (!resp.ok) return;
      const data = await resp.json();

      if (circuitBreakersContainer) {
        circuitBreakersContainer.innerHTML = '';
        const monitored = data.projects_monitored || [];
        if (monitored.length === 0) {
          circuitBreakersContainer.innerHTML = '<div class="p-3 text-slate-500 text-center">No hay proyectos activos registrados.</div>';
        } else {
          monitored.forEach(item => {
            const row = document.createElement('div');
            const isTripped = item.tripped;
            const borderCol = isTripped ? 'border-red-500/50 bg-red-950/20' : 'border-[#1f2937] bg-[#0b0f19]';
            row.className = `p-2.5 rounded border ${borderCol} flex items-center justify-between`;
            row.innerHTML = `
              <div>
                <span class="font-bold text-white block">${item.project_id}</span>
                <span class="text-[10px] text-slate-400">Iteración: ${item.iteration}/${item.max_iterations} • Veredicto: ${item.last_verdict}</span>
              </div>
              <span class="px-2 py-0.5 rounded text-[10px] font-bold ${isTripped ? 'bg-red-950 text-red-400 border border-red-800' : 'bg-emerald-950 text-emerald-400 border border-emerald-800'}">
                ${isTripped ? 'TRIPPED' : 'NORMAL'}
              </span>
            `;
            circuitBreakersContainer.appendChild(row);
          });
        }
      }

      if (securityEventsContainer) {
        securityEventsContainer.innerHTML = '';
        const events = data.recent_security_events || [];
        if (events.length === 0) {
          securityEventsContainer.innerHTML = '<div class="p-3 text-slate-500 text-center">No se registran alertas de seguridad o vetos críticos.</div>';
        } else {
          events.forEach(ev => {
            const card = document.createElement('div');
            const isCrit = ev.level === 'CRITICAL';
            card.className = `p-2.5 rounded border ${isCrit ? 'border-red-900/60 bg-red-950/20' : 'border-amber-900/60 bg-amber-950/20'} flex flex-col gap-1`;
            card.innerHTML = `
              <div class="flex items-center justify-between">
                <span class="font-bold ${isCrit ? 'text-red-400' : 'text-amber-400'}">[${ev.level}] ${ev.agent_id}</span>
                <span class="text-[10px] text-slate-500">${ev.timestamp.substring(11, 19)}</span>
              </div>
              <p class="text-slate-300 text-[11px] leading-tight">${escapeHtml(ev.message)}</p>
              ${ev.culprit ? `<span class="text-[10px] text-red-400 font-semibold">Culprit: ${ev.culprit}</span>` : ''}
            `;
            securityEventsContainer.appendChild(card);
          });
        }
      }
    } catch (err) {
      console.warn('Error loading security status:', err);
    }
  }

  // --- 9. Tab 6: Database & Artifacts Inspector Component ---
  const dbTableSelect = document.getElementById('db-table-select');
  const dbSearchInput = document.getElementById('db-search-input');
  const btnDbRefresh = document.getElementById('btn-db-refresh');
  const dbTableHead = document.getElementById('db-table-head');
  const dbTableBody = document.getElementById('db-table-body');
  const dbRowsCount = document.getElementById('db-rows-count');

  const artProjectSelect = document.getElementById('artifacts-project-select');
  const artifactsFileList = document.getElementById('artifacts-file-list');
  const previewFilename = document.getElementById('preview-filename');
  const previewFilesize = document.getElementById('preview-filesize');
  const previewContent = document.getElementById('preview-content');

  async function loadDatabaseTable() {
    if (!dbTableSelect || !dbTableHead || !dbTableBody) return;
    const table = dbTableSelect.value;
    const search = dbSearchInput ? dbSearchInput.value.trim() : '';

    let url = `/api/v1/telemetry/database/query?table=${encodeURIComponent(table)}&limit=30`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    try {
      const resp = await fetch(url);
      if (!resp.ok) return;
      const data = await resp.json();

      if (dbRowsCount) dbRowsCount.textContent = `${data.rows.length} de ${data.total_rows}`;

      // Build Headers
      dbTableHead.innerHTML = '';
      const trHead = document.createElement('tr');
      (data.columns || []).forEach(col => {
        const th = document.createElement('th');
        th.className = 'p-2 whitespace-nowrap uppercase tracking-wider font-semibold text-[10px]';
        th.textContent = col;
        trHead.appendChild(th);
      });
      dbTableHead.appendChild(trHead);

      // Build Body
      dbTableBody.innerHTML = '';
      if (data.rows.length === 0) {
        dbTableBody.innerHTML = `<tr><td colspan="${data.columns.length}" class="p-4 text-center text-slate-500">Tabla vacía o sin coincidencias de búsqueda.</td></tr>`;
        return;
      }

      data.rows.forEach(row => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-900/50';
        data.columns.forEach(col => {
          const td = document.createElement('td');
          td.className = 'p-2 whitespace-nowrap max-w-[200px] truncate text-[11px]';
          const val = row[col];
          td.textContent = val !== null && val !== undefined ? String(val) : '';
          td.title = String(val || '');
          tr.appendChild(td);
        });
        dbTableBody.appendChild(tr);
      });
    } catch (err) {
      console.warn('Error querying database table:', err);
    }
  }

  if (dbTableSelect) dbTableSelect.addEventListener('change', loadDatabaseTable);
  if (btnDbRefresh) btnDbRefresh.addEventListener('click', loadDatabaseTable);
  if (dbSearchInput) {
    dbSearchInput.addEventListener('keyup', (e) => {
      if (e.key === 'Enter') loadDatabaseTable();
    });
  }

  // Artifacts Explorer
  async function loadArtifactsProjectSelector() {
    if (!artProjectSelect) return;
    if (artProjectSelect.options.length <= 1) {
      await loadProjectsList();
    }
  }

  if (artProjectSelect) {
    artProjectSelect.addEventListener('change', async () => {
      const pid = artProjectSelect.value;
      if (!pid || !artifactsFileList) {
        if (artifactsFileList) artifactsFileList.innerHTML = '<div class="p-3 text-slate-500 text-center">Selecciona un proyecto arriba.</div>';
        return;
      }

      artifactsFileList.innerHTML = '<div class="p-3 text-slate-400 text-center">Cargando artefactos...</div>';

      try {
        const resp = await fetch(`/api/v1/telemetry/artifacts?project_id=${encodeURIComponent(pid)}`);
        if (!resp.ok) {
          artifactsFileList.innerHTML = '<div class="p-3 text-amber-500 text-center">No se encontraron artefactos para este proyecto.</div>';
          return;
        }

        const data = await resp.json();
        const files = data.artifacts || [];

        artifactsFileList.innerHTML = '';
        if (files.length === 0) {
          artifactsFileList.innerHTML = '<div class="p-3 text-slate-500 text-center">Workspace vacío.</div>';
          return;
        }

        files.forEach(f => {
          const btn = document.createElement('button');
          btn.className = 'w-full text-left p-1.5 rounded hover:bg-slate-800 flex items-center justify-between gap-1 text-slate-300 transition';

          let icon = '📄';
          if (f.file_type === 'json') icon = '⚙️';
          else if (f.file_type === 'markdown') icon = '📝';
          else if (f.file_type === 'code') icon = '⚡';

          btn.innerHTML = `
            <div class="flex items-center gap-1.5 truncate">
              <span>${icon}</span>
              <span class="truncate">${escapeHtml(f.relative_path)}</span>
            </div>
            <span class="text-slate-500 text-[10px] whitespace-nowrap">${formatBytes(f.size_bytes)}</span>
          `;

          btn.addEventListener('click', () => {
            loadArtifactContent(pid, f.relative_path, f.size_bytes);
          });

          artifactsFileList.appendChild(btn);
        });

      } catch (err) {
        console.warn('Error loading project artifacts:', err);
      }
    });
  }

  async function loadArtifactContent(projectId, filePath, sizeBytes) {
    if (!previewContent) return;
    if (previewFilename) previewFilename.textContent = filePath;
    if (previewFilesize) previewFilesize.textContent = formatBytes(sizeBytes);
    previewContent.textContent = 'Cargando contenido...';

    try {
      const resp = await fetch(`/api/v1/telemetry/artifacts/content?project_id=${encodeURIComponent(projectId)}&file_path=${encodeURIComponent(filePath)}`);
      if (!resp.ok) {
        previewContent.textContent = 'Error al cargar el archivo.';
        return;
      }
      const data = await resp.json();
      previewContent.textContent = data.content;
    } catch (err) {
      previewContent.textContent = 'Error de conexión al leer el archivo.';
    }
  }

  // --- Utility Helpers ---
  function escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

})();
