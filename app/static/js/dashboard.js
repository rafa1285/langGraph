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
    if (targetId === 'tab-whatsapp') {
      loadWhatsAppHub();
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



  // Live Badge Elements
  const liveBadge = document.getElementById('live-connection-badge');
  const liveDot = document.getElementById('live-connection-dot');
  const liveText = document.getElementById('live-connection-text');

  function updateLiveStatus(status, text, tooltip) {
    if (!liveBadge || !liveDot || !liveText) return;
    if (status === 'live') {
      liveBadge.className = 'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-500/40 transition-colors duration-300';
      liveDot.className = 'w-2 h-2 rounded-full bg-emerald-400 live-dot';
      liveText.textContent = text || 'LIVE';
      liveBadge.title = tooltip || 'Conexión activa con el servidor FastAPI';
    } else if (status === 'degraded') {
      liveBadge.className = 'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-400 border border-amber-500/40 transition-colors duration-300';
      liveDot.className = 'w-2 h-2 rounded-full bg-amber-400';
      liveText.textContent = text || 'DEGRADED';
      liveBadge.title = tooltip || 'Respuesta anormal del backend';
    } else {
      liveBadge.className = 'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950/80 text-rose-400 border border-rose-500/40 transition-colors duration-300';
      liveDot.className = 'w-2 h-2 rounded-full bg-rose-500';
      liveText.textContent = text || 'OFFLINE';
      liveBadge.title = tooltip || 'Sin conexión con el backend (servidor detenido o inaccesible)';
    }
  }

  // --- 3. Telemetry KPIs Engine (Real-Time Backend Polling) ---
  async function fetchKpis() {
    try {
      const resp = await fetch('/api/dashboard/telemetry');
      if (!resp.ok) {
        updateLiveStatus('degraded', `HTTP ${resp.status}`, `Error del servidor HTTP ${resp.status}`);
        return;
      }
      const data = await resp.json();
      updateLiveStatus('live', 'LIVE', 'Conexión en tiempo real activa');

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
      updateLiveStatus('offline', 'OFFLINE', 'Servidor no responde');
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

  function setPipelineStage(activeIdx, isCompleted = false) {
    STAGE_IDS.forEach((id, idx) => {
      const el = document.getElementById(id);
      if (!el) return;
      const tag = el.querySelector('.status-tag');
      if (idx < activeIdx || (idx === activeIdx && isCompleted)) {
        el.className = 'pipeline-step flex-1 bg-emerald-950/40 border border-emerald-500/60 rounded-lg p-2.5 flex flex-col items-center text-center transition';
        if (tag) { tag.textContent = 'DONE'; tag.className = 'text-[10px] text-emerald-400 status-tag font-bold'; }
      } else if (idx === activeIdx) {
        el.className = 'pipeline-step flex-1 bg-cyan-950/70 border border-cyan-400 rounded-lg p-2.5 flex flex-col items-center text-center shadow-lg shadow-cyan-950 animate-pulse transition';
        if (tag) { tag.textContent = 'ACTIVE'; tag.className = 'text-[10px] text-cyan-300 status-tag font-bold'; }
      } else {
        el.className = 'pipeline-step flex-1 bg-[#0b0f19] border border-[#1f2937] rounded-lg p-2.5 flex flex-col items-center text-center opacity-60 transition';
        if (tag) { tag.textContent = 'PENDING'; tag.className = 'text-[10px] text-slate-500 status-tag'; }
      }
    });

    if (pipelineStepCounter) {
      pipelineStepCounter.textContent = isCompleted ? 'Paso 7/7 (Completado)' : `Paso ${activeIdx + 1}/7`;
    }
  }

  // Load projects list for dropdowns
  async function loadProjectsList() {
    try {
      const resp = await fetch('/api/v1/projects');
      if (!resp.ok) return;
      const data = await resp.json();
      availableProjects = data.projects || [];

      // Populate project-select in Tab 2
      if (projectSelect) {
        const cur = projectSelect.value;
        projectSelect.innerHTML = '<option value="">-- Nuevo Proyecto --</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          const name = p.project_name || (p.project_id === 'proj_88c9fd46' ? 'validator-hq-saas' : null);
          const label = name ? `${name} (${p.project_id})` : p.project_id;
          opt.textContent = `${label} (${p.current_status || 'IDLE'})`;
          projectSelect.appendChild(opt);
        });
        if (cur) {
          projectSelect.value = cur;
        } else if (availableProjects.length > 0) {
          // Auto-select latest active project if none was selected
          projectSelect.value = availableProjects[0].project_id;
          projectSelect.dispatchEvent(new Event('change'));
        }
      }

      // Populate project filters in other tabs
      const thoughtsProjSelect = document.getElementById('thoughts-project-select');
      if (thoughtsProjSelect) {
        const cur = thoughtsProjSelect.value;
        thoughtsProjSelect.innerHTML = '<option value="">Todos los Proyectos</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          const name = p.project_name || (p.project_id === 'proj_88c9fd46' ? 'validator-hq-saas' : null);
          const label = name ? `${name} (${p.project_id})` : p.project_id;
          opt.textContent = label;
          thoughtsProjSelect.appendChild(opt);
        });
        if (cur) {
          thoughtsProjSelect.value = cur;
        } else if (availableProjects.length > 0) {
          thoughtsProjSelect.value = availableProjects[0].project_id;
        }
      }

      const statsProjSelect = document.getElementById('stats-project-select');
      if (statsProjSelect) {
        const cur = statsProjSelect.value;
        statsProjSelect.innerHTML = '<option value="">Todos los Proyectos</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          const name = p.project_name || (p.project_id === 'proj_88c9fd46' ? 'validator-hq-saas' : null);
          const label = name ? `${name} (${p.project_id})` : p.project_id;
          opt.textContent = label;
          statsProjSelect.appendChild(opt);
        });
        if (cur) {
          statsProjSelect.value = cur;
        } else if (availableProjects.length > 0) {
          statsProjSelect.value = availableProjects[0].project_id;
        }
      }

      const costProjSelect = document.getElementById('cost-project-select');
      if (costProjSelect) {
        const cur = costProjSelect.value;
        costProjSelect.innerHTML = '<option value="">Todos los Proyectos</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          const name = p.project_name || (p.project_id === 'proj_88c9fd46' ? 'validator-hq-saas' : null);
          const label = name ? `${name} (${p.project_id})` : p.project_id;
          opt.textContent = label;
          costProjSelect.appendChild(opt);
        });
        if (cur) {
          costProjSelect.value = cur;
        } else if (availableProjects.length > 0) {
          costProjSelect.value = availableProjects[0].project_id;
        }
      }

      const secProjSelect = document.getElementById('sec-project-select');
      if (secProjSelect) {
        const cur = secProjSelect.value;
        secProjSelect.innerHTML = '<option value="">Todos los Proyectos</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          const name = p.project_name || (p.project_id === 'proj_88c9fd46' ? 'validator-hq-saas' : null);
          const label = name ? `${name} (${p.project_id})` : p.project_id;
          opt.textContent = label;
          secProjSelect.appendChild(opt);
        });
        if (cur) {
          secProjSelect.value = cur;
        } else if (availableProjects.length > 0) {
          secProjSelect.value = availableProjects[0].project_id;
        }
      }

      const artProjSelect = document.getElementById('artifacts-project-select');
      if (artProjSelect) {
        const cur = artProjSelect.value;
        artProjSelect.innerHTML = '<option value="">Selecciona un Proyecto...</option>';
        availableProjects.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.project_id;
          const name = p.project_name || (p.project_id === 'proj_88c9fd46' ? 'validator-hq-saas' : null);
          const label = name ? `${name} (${p.project_id})` : p.project_id;
          opt.textContent = label;
          artProjSelect.appendChild(opt);
        });
        if (cur) {
          artProjSelect.value = cur;
        } else if (availableProjects.length > 0) {
          artProjSelect.value = availableProjects[0].project_id;
        }
      }

      window.__debug_projects = {
        available: availableProjects,
        artProjFound: !!artProjSelect,
        optionsCount: artProjSelect ? artProjSelect.options.length : -1,
        artProjValue: artProjSelect ? artProjSelect.value : null
      };

      // If any tab is active on boot, trigger data load now that project ID is set
      const tPane = document.getElementById('tab-thoughts');
      if (tPane && !tPane.classList.contains('hidden') && typeof loadThoughts === 'function') {
        loadThoughts();
      }
      const uPane = document.getElementById('tab-usage');
      if (uPane && !uPane.classList.contains('hidden') && typeof loadAgentStats === 'function') {
        loadAgentStats();
      }
      const tokPane = document.getElementById('tab-tokens');
      if (tokPane && !tokPane.classList.contains('hidden') && typeof loadCostBreakdown === 'function') {
        loadCostBreakdown();
      }
      const secPane = document.getElementById('tab-security');
      if (secPane && !secPane.classList.contains('hidden') && typeof loadSecurityStatus === 'function') {
        loadSecurityStatus();
      }
      const dbPane = document.getElementById('tab-database');
      if (dbPane && !dbPane.classList.contains('hidden') && typeof loadDatabaseTable === 'function') {
        loadDatabaseTable();
        if (typeof loadArtifactsProjectSelector === 'function') loadArtifactsProjectSelector();
      }
    } catch (err) {
      console.warn('Error loading projects list:', err);
      window.__debug_projects_err = String(err);
    }
  }

  loadProjectsList();

  // --- Live EventSource Management for LangGraph Streaming ---
  let currentEventSource = null;

  function connectDashboardStream(pid) {
    if (currentEventSource) {
      currentEventSource.close();
      currentEventSource = null;
    }
    if (!pid) return;

    currentEventSource = new EventSource(`/api/dashboard/stream?project_id=${encodeURIComponent(pid)}`);

    const wsStatus = document.getElementById('ws-status');
    currentEventSource.onopen = () => {
      if (wsStatus) {
        wsStatus.textContent = 'En Vivo (SSE)';
        wsStatus.className = 'text-emerald-400 font-semibold';
      }
    };

    currentEventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event_type === 'ping') return;

        // Add to activity events
        if (data.category && data.msg) {
          const isDup = allActivityEvents.some(
            e => e.time === data.time && e.msg === data.msg && e.agent === data.agent
          );
          if (!isDup) {
            allActivityEvents.push(data);
            renderActivityLog();
          }
        }

        // Update pipeline step
        const isCompleted = data.status === 'COMPLETED' || data.stage_index === 6;
        if (typeof data.stage_index === 'number') {
          setPipelineStage(data.stage_index, isCompleted);
        }
        if (pipelineInfoText && data.msg) {
          pipelineInfoText.textContent = `[${data.stage_name || 'Pipeline'}] ${data.msg}`;
        }

        // Update pipeline badge
        const badgeEl = document.getElementById('pipeline-active-badge');
        if (badgeEl) {
          badgeEl.textContent = isCompleted ? 'Completado ✓' : '1 activo ▼';
        }

        // Update KPI HUD values
        const kpis = data.kpis || {};
        if (kpiTokens && (kpis.tokens_str || data.tokens)) {
          kpiTokens.textContent = kpis.tokens_str || Number(data.tokens).toLocaleString();
        }
        if (kpiCost && (kpis.cost || data.cost)) {
          kpiCost.textContent = kpis.cost || `$${Number(data.cost).toFixed(4)}`;
        }
        if (kpiSaved && (kpis.saved || data.saved)) {
          kpiSaved.textContent = kpis.saved || `$${Number(data.saved).toFixed(2)}`;
        }

        if (data.status === 'COMPLETED') {
          if (pipelineInfoText) {
            pipelineInfoText.textContent = '✅ Proyecto completado con éxito — Lanzamiento Autorizado.';
          }
        } else if (data.status === 'FAILED') {
          if (pipelineInfoText) {
            pipelineInfoText.textContent = '❌ Error durante la ejecución del grafo.';
          }
        }
      } catch (err) {
        console.warn('Error procesando evento SSE:', err);
      }
    };

    currentEventSource.onerror = (err) => {
      console.warn('SSE stream reconectando o desconectado:', err);
      if (wsStatus) {
        wsStatus.textContent = 'Reconectando...';
        wsStatus.className = 'text-amber-400';
      }
    };
  }

  // Handle Project Selection in Tab 2
  if (projectSelect) {
    projectSelect.addEventListener('change', async () => {
      const pid = projectSelect.value;
      if (!pid) {
        setPipelineStage(0, false);
        if (pipelineInfoText) pipelineInfoText.textContent = 'Selecciona un proyecto para cargar su pipeline.';
        if (currentEventSource) {
          currentEventSource.close();
          currentEventSource = null;
        }
        allActivityEvents = [];
        renderActivityLog();
        return;
      }

      if (pipelineInfoText) pipelineInfoText.textContent = `Cargando estado del proyecto ${pid}...`;

      try {
        const stateResp = await fetch(`/api/dashboard/state?project_id=${encodeURIComponent(pid)}`);
        if (stateResp.ok) {
          const state = await stateResp.json();
          const isDone = state.status === 'COMPLETED' || state.stage_index === 6;
          setPipelineStage(state.stage_index || 0, isDone);
          allActivityEvents = state.events || [];
          renderActivityLog();

          const badgeEl = document.getElementById('pipeline-active-badge');
          if (badgeEl) {
            badgeEl.textContent = isDone ? 'Completado ✓' : `${state.status || 'Activo'} ▼`;
          }

          if (pipelineInfoText) {
            pipelineInfoText.textContent = `Monitoreando ${pid} — Etapa: ${state.stage_name} [${state.status}]`;
          }
          if (kpiTokens && state.tokens) kpiTokens.textContent = Number(state.tokens).toLocaleString();
          if (kpiCost && state.cost) kpiCost.textContent = `$${Number(state.cost).toFixed(4)}`;
          if (kpiSaved && state.saved) kpiSaved.textContent = `$${Number(state.saved).toFixed(2)}`;

          // Connect stream to receive live updates
          connectDashboardStream(pid);
        } else {
          // Fallback to thoughts endpoint if state endpoint has an issue
          console.warn('State endpoint returned non-200, falling back to telemetry thoughts...');
          const tResp = await fetch(`/api/v1/telemetry/thoughts?project_id=${encodeURIComponent(pid)}&limit=50`);
          if (tResp.ok) {
            const tData = await tResp.json();
            allActivityEvents = (tData.thoughts || []).map(t => {
              let cat = 'response';
              const ag = (t.agent_id || '').toLowerCase();
              if (ag.includes('ceo')) cat = 'delegate';
              else if (ag.includes('qa') || ag.includes('ciso') || ag.includes('devops')) cat = 'tool';
              if (t.verdict === 'APROBADO') cat = 'done';
              return {
                time: t.created_at ? t.created_at.substring(11, 19) : '00:00:00',
                category: cat,
                agent: t.agent_name || t.agent_id,
                msg: t.snippet || (t.raw_response ? t.raw_response.substring(0, 140) : ''),
              };
            });
            setPipelineStage(6, true);
            renderActivityLog();
            if (pipelineInfoText) pipelineInfoText.textContent = `Monitoreando ${pid} (Histórico cargado)`;
          }
        }
      } catch (err) {
        console.warn('Error loading project dashboard state:', err);
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
        <span class="text-slate-500 text-[10px] whitespace-nowrap mt-0.5">[${ev.time || '00:00:00'}]</span>
        <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold border ${badgeColor} whitespace-nowrap uppercase">${ev.category}</span>
        <span class="text-cyan-400 font-semibold whitespace-nowrap">${ev.agent || 'Agente'}</span>
        <span class="text-slate-300 break-all">${escapeHtml(ev.msg || '')}</span>
      `;
      activityStream.appendChild(row);
    });

    // Auto-scroll to bottom of activity log
    activityStream.scrollTop = activityStream.scrollHeight;
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

  // Launch Factory button (Real-Time LangGraph Execution)
  if (launchBtn) {
    launchBtn.addEventListener('click', async () => {
      const idea = projectIdeaInput ? projectIdeaInput.value.trim() : '';
      if (!idea) {
        alert('Por favor describe tu idea de negocio o directriz de software.');
        return;
      }
      const customPid = projectIdInput ? projectIdInput.value.trim() : '';
      const mockCheck = document.getElementById('check-mock-llm');
      const isMock = mockCheck ? mockCheck.checked : false;

      launchBtn.disabled = true;
      launchBtn.innerHTML = '<span>⏳ Conectando...</span>';

      try {
        const resp = await fetch('/api/dashboard/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: idea,
            id_proyecto: customPid || null,
            mock: isMock,
          }),
        });

        if (!resp.ok) {
          const errData = await resp.json().catch(() => ({}));
          alert(`Error al iniciar el pipeline: ${errData.detail || 'Fallo desconocido'}`);
          return;
        }

        const res = await resp.json();
        const newPid = res.project_id;
        if (projectIdeaInput) projectIdeaInput.value = '';
        if (projectIdInput) projectIdInput.value = '';

        await loadProjectsList();
        if (projectSelect) projectSelect.value = newPid;

        // Initialize pipeline to stage 0 (Received) and activity log
        setPipelineStage(0);
        allActivityEvents = [{
          time: new Date().toTimeString().substring(0, 8),
          category: 'user',
          agent: '👔 Boss',
          msg: `Request from Boss: ${idea}`,
          project_id: newPid,
          stage_index: 0,
          stage_id: 'stage-received',
          stage_name: 'Received',
        }];
        renderActivityLog();

        // Connect SSE stream
        connectDashboardStream(newPid);

        if (pipelineInfoText) {
          pipelineInfoText.textContent = `Iniciado: ${newPid}. Transmitiendo eventos LangGraph en vivo...`;
        }
      } catch (err) {
        console.error('Error de red al lanzar fábrica:', err);
        alert('Error de red al conectar con el servidor.');
      } finally {
        launchBtn.disabled = false;
        launchBtn.innerHTML = '<span>🚀 Launch Factory</span>';
      }
    });
  }

  // --- 5. Tab 2: Agent Thoughts Stream & Split-Inspector ---
  const OFFICIAL_13_AGENTS = [
    { id: 'agente_00_ceo', name: 'CEO', icon: '👔', desc: 'Apertura Charter & Cierre Signoff' },
    { id: 'agente_01_pm', name: 'Product Manager', icon: '📋', desc: 'Sprint Backlog & User Stories' },
    { id: 'agente_02_architect', name: 'Software Architect', icon: '📐', desc: 'Arquitectura del Sistema & SDD' },
    { id: 'agente_11_ui_ux', name: 'UI/UX Designer', icon: '🎨', desc: 'Design System & Wireframes' },
    { id: 'agente_03_laravel', name: 'Dev PHP (Laravel)', icon: '🐘', desc: 'Backend API & Eloquent ORM' },
    { id: 'agente_04_fastapi', name: 'Dev Python (FastAPI)', icon: '⚡', desc: 'Microservicios & Asincronía' },
    { id: 'agente_05_qa_php', name: 'QA PHP (Pest)', icon: '🧪', desc: 'Tests Unitarios PHP & Pest' },
    { id: 'agente_06_qa_python', name: 'QA Python (Pytest)', icon: '🔬', desc: 'Batería de Tests & Pytest' },
    { id: 'agente_07_devops', name: 'DevOps & Docker', icon: '🐳', desc: 'Docker & CI/CD Pipelines' },
    { id: 'agente_10_ciso', name: 'CISO Security', icon: '🛡️', desc: 'Auditoría Ciberseguridad & OWASP' },
    { id: 'agente_08_docs', name: 'Docs & RAG', icon: '📚', desc: 'Documentación Técnica & Embeddings' },
    { id: 'agente_12_marketing', name: 'Marketing PLG', icon: '📢', desc: 'Estrategia PLG & Captación' },
    { id: 'agente_13_sales_analytics', name: 'Sales BI & Analytics', icon: '📊', desc: 'Embudo de Ventas & Métricas' },
  ];

  let selectedThoughtAgentId = 'agente_00_ceo';
  let selectedThoughtStepIndex = 0;
  let allProjectThoughts = [];

  const thoughtsProjSelect = document.getElementById('thoughts-project-select');
  const btnRefreshThoughts = document.getElementById('btn-refresh-thoughts');
  const thoughtsAgentPills = document.getElementById('thoughts-agent-pills');
  const thoughtsCountBadge = document.getElementById('thoughts-count-badge');
  const thoughtStepSelectorBar = document.getElementById('thoughts-step-selector-bar');
  const thoughtStepPills = document.getElementById('thoughts-step-pills');

  const thoughtMetaAgentBadge = document.getElementById('thought-meta-agent-badge');
  const yamlMetaProyecto = document.getElementById('yaml-meta-proyecto');
  const yamlMetaIteracion = document.getElementById('yaml-meta-iteracion');
  const yamlMetaEmisor = document.getElementById('yaml-meta-emisor');
  const yamlMetaReceptor = document.getElementById('yaml-meta-receptor');
  const yamlMetaEstado = document.getElementById('yaml-meta-estado');
  const yamlMetaPrioridad = document.getElementById('yaml-meta-prioridad');
  const yamlMetaTimestamp = document.getElementById('yaml-meta-timestamp');

  const thoughtDocTitle = document.getElementById('thought-doc-title');
  const btnCopyThoughtOutput = document.getElementById('btn-copy-thought-output');
  const btnExpandAllSections = document.getElementById('btn-expand-all-sections');
  const btnCollapseAllSections = document.getElementById('btn-collapse-all-sections');
  const btnToggleYamlMeta = document.getElementById('btn-toggle-yaml-meta');
  const yamlMetaChevron = document.getElementById('yaml-meta-chevron');
  const thoughtYamlMetaGrid = document.getElementById('thought-yaml-meta-grid');
  const thoughtMarkdownViewer = document.getElementById('thought-markdown-viewer');

  // Format the inner body of an individual section (Markdown + Code Blocks)
  function formatSectionBodyMarkdown(text) {
    if (!text || !text.trim()) {
      return '<div class="text-slate-500 italic py-2 font-mono text-xs">Sin contenido adicional en este apartado.</div>';
    }

    let escaped = escapeHtml(text);

    // Code blocks ```lang ... ```
    escaped = escaped.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      const langTag = lang ? `<span class="text-[10px] uppercase font-bold text-cyan-400 bg-cyan-950 px-2 py-0.5 rounded border border-cyan-800">${lang}</span>` : '';
      return `
        <div class="my-3 rounded-lg overflow-hidden border border-[#1f2937] bg-[#070a12]">
          <div class="flex items-center justify-between px-3 py-1.5 bg-[#0e1422] border-b border-[#1f2937]">
            <span class="text-[10px] text-slate-400 font-mono">Código Fuente / Artefacto</span>
            ${langTag}
          </div>
          <pre class="p-3 text-[11px] font-mono leading-relaxed overflow-x-auto text-emerald-300 whitespace-pre">${code.trim()}</pre>
        </div>
      `;
    });

    // Inline code `code`
    escaped = escaped.replace(/`([^`]+)`/g, '<code class="bg-[#111827] text-cyan-300 px-1.5 py-0.5 rounded border border-slate-700 font-mono text-[11px]">$1</code>');

    // Sub-headers inside the section
    escaped = escaped.replace(/^#### (.*$)/gim, '<h4 class="text-xs font-bold text-slate-300 mt-3 mb-1 uppercase tracking-wider">$1</h4>');
    escaped = escaped.replace(/^### (.*$)/gim, '<h3 class="text-xs font-bold text-cyan-300 mt-3.5 mb-1 pb-1 border-b border-slate-800/80">$1</h3>');
    escaped = escaped.replace(/^## (.*$)/gim, '<h2 class="text-sm font-bold text-white mt-4 mb-1.5 pb-1 border-b border-[#1f2937]">$1</h2>');

    // Bold & italic
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, '<strong class="text-white font-semibold">$1</strong>');
    escaped = escaped.replace(/\*([^*]+)\*/g, '<em class="text-slate-300 italic">$1</em>');

    // Unordered lists
    escaped = escaped.replace(/^\s*[-*]\s+(.*$)/gim, '<li class="ml-4 list-disc text-slate-300 my-0.5">$1</li>');

    return `<div class="whitespace-pre-wrap leading-relaxed">${escaped}</div>`;
  }

  // Split raw deliverable markdown into structured collapsible sections
  function splitMarkdownIntoSections(rawText) {
    if (!rawText || !rawText.trim()) return [];

    let text = rawText;
    const sections = [];

    // 1. Frontmatter
    const fmMatch = text.match(/^\s*---\s*\n([\s\S]*?)\n---\s*\n?/);
    if (fmMatch) {
      sections.push({
        title: '⚙️ Frontmatter YAML (Metadatos de Enrutamiento y Auditoría)',
        content: fmMatch[1].trim(),
        isFrontmatter: true,
      });
      text = text.substring(fmMatch[0].length);
    }

    // 2. Protect code blocks from false heading matches (# comments inside code blocks)
    const codeBlocks = [];
    const maskedText = text.replace(/```[a-zA-Z0-9_-]*\n[\s\S]*?```/g, match => {
      codeBlocks.push(match);
      return `\n\n__CODE_BLOCK_${codeBlocks.length - 1}__\n\n`;
    });

    // 3. Find headings on #, ##, or ###
    const matches = Array.from(maskedText.matchAll(/^(#{1,3})\s+(.+)$/gm));

    if (matches.length === 0) {
      let full = maskedText;
      codeBlocks.forEach((cb, idx) => {
        full = full.replaceAll(`__CODE_BLOCK_${idx}__`, cb);
      });
      sections.push({
        title: '📄 Entregable Completo',
        content: full.trim(),
        isFrontmatter: false,
      });
      return sections;
    }

    // Preamble before first heading
    if (matches[0].index > 0) {
      let preamble = maskedText.substring(0, matches[0].index).trim();
      if (preamble) {
        codeBlocks.forEach((cb, idx) => {
          preamble = preamble.replaceAll(`__CODE_BLOCK_${idx}__`, cb);
        });
        sections.push({
          title: '📋 Introducción / Resumen Ejecutivo',
          content: preamble,
          isFrontmatter: false,
        });
      }
    }

    // Process each heading and its content
    for (let i = 0; i < matches.length; i++) {
      const m = matches[i];
      const start = m.index + m[0].length;
      const end = i + 1 < matches.length ? matches[i + 1].index : maskedText.length;
      const rawTitle = m[2].trim();
      let body = maskedText.substring(start, end).trim();

      codeBlocks.forEach((cb, idx) => {
        body = body.replaceAll(`__CODE_BLOCK_${idx}__`, cb);
      });

      sections.push({
        title: rawTitle,
        content: body,
        isFrontmatter: false,
      });
    }

    return sections;
  }

  // Lightweight Markdown & Code Block Formatter with Collapsible Sections (Apartados)
  function renderFormattedMarkdown(text) {
    if (!text || !text.trim()) {
      return '<div class="text-center text-slate-500 py-10 font-mono text-xs">No hay entregable generado para este agente en el proyecto seleccionado.</div>';
    }

    const sections = splitMarkdownIntoSections(text);
    if (sections.length === 0) {
      return '<div class="text-center text-slate-500 py-10 font-mono text-xs">Sin contenido.</div>';
    }

    let html = '';
    const firstContentIdx = sections.some(s => s.isFrontmatter) ? 1 : 0;

    sections.forEach((sec, idx) => {
      // By default:
      // Frontmatter is collapsed.
      // First content section is open, rest are collapsed so long docs are clean and easy to scan!
      const isExpanded = idx === firstContentIdx;
      const chevron = isExpanded ? '▼' : '▶';
      const hiddenClass = isExpanded ? '' : 'hidden';
      const activeBorder = isExpanded ? 'border-b border-[#1f2937] bg-[#101728]' : 'bg-[#0e1422]';

      let bodyHtml = '';
      if (sec.isFrontmatter) {
        const fmLines = escapeHtml(sec.content).split('\n').map(l => {
          const cIdx = l.indexOf(':');
          if (cIdx > -1) {
            const k = l.substring(0, cIdx);
            const v = l.substring(cIdx + 1);
            return `<span class="text-cyan-400 font-semibold">${k}:</span><span class="text-slate-300">${v}</span>`;
          }
          return `<span class="text-slate-400">${l}</span>`;
        }).join('\n');
        bodyHtml = `
          <div class="p-3 rounded-lg bg-[#070b14] border border-cyan-900/60 font-mono text-[11px]">
            <pre class="whitespace-pre-wrap leading-relaxed">${fmLines}</pre>
          </div>
        `;
      } else {
        bodyHtml = formatSectionBodyMarkdown(sec.content);
      }

      const lengthBadge = sec.content ? `${sec.content.length.toLocaleString()} carácteres` : 'Vacío';

      html += `
        <div class="thought-accordion-card border border-[#1f2937] rounded-lg bg-[#0b0f19] overflow-hidden transition shadow-sm">
          <button type="button" class="thought-accordion-header w-full px-3.5 py-2.5 ${activeBorder} hover:bg-[#151f34] flex items-center justify-between gap-3 text-left transition select-none cursor-pointer">
            <div class="flex items-center gap-2.5 min-w-0">
              <span class="thought-accordion-chevron text-cyan-400 text-xs font-mono transition-transform duration-200">${chevron}</span>
              <span class="text-xs font-bold text-slate-200 truncate font-mono">${escapeHtml(sec.title)}</span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <span class="text-[10px] text-slate-400 font-mono px-2 py-0.5 rounded bg-[#070a12] border border-[#1f2937]">${lengthBadge}</span>
            </div>
          </button>
          <div class="thought-accordion-body p-3.5 bg-[#080c14] border-t border-[#1f2937] font-mono text-xs leading-relaxed text-slate-300 ${hiddenClass}">
            ${bodyHtml}
          </div>
        </div>
      `;
    });

    return html;
  }

  // Render the selected agent's YAML metadata and Markdown body
  function renderSelectedAgentThought() {
    const agentObj = OFFICIAL_13_AGENTS.find(a => a.id === selectedThoughtAgentId) || OFFICIAL_13_AGENTS[0];
    const agentThoughts = allProjectThoughts.filter(t => t.agent_id === selectedThoughtAgentId);

    // Update active state in sidebar pills
    if (thoughtsAgentPills) {
      thoughtsAgentPills.querySelectorAll('.thought-agent-pill').forEach(btn => {
        const aid = btn.getAttribute('data-agent-id');
        if (aid === selectedThoughtAgentId) {
          btn.className = 'thought-agent-pill w-full text-left py-1.5 px-2.5 rounded-lg border border-cyan-400 bg-cyan-950/70 shadow-lg shadow-cyan-950/50 flex items-center justify-between transition shrink-0';
        } else {
          btn.className = 'thought-agent-pill w-full text-left py-1.5 px-2.5 rounded-lg border border-[#1f2937] bg-[#111827] hover:border-slate-600 hover:bg-slate-800/60 flex items-center justify-between transition shrink-0';
        }
      });
    }

    if (thoughtMetaAgentBadge) {
      thoughtMetaAgentBadge.textContent = `${agentObj.icon} ${agentObj.name} (${agentObj.id})`;
      thoughtMetaAgentBadge.className = 'text-xs font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-bold';
    }

    // Step Selector Bar if multiple iterations exist
    if (thoughtStepSelectorBar && thoughtStepPills) {
      if (agentThoughts.length > 1) {
        thoughtStepSelectorBar.classList.remove('hidden');
        thoughtStepPills.innerHTML = '';
        agentThoughts.forEach((th, idx) => {
          const btn = document.createElement('button');
          const isSel = idx === selectedThoughtStepIndex;
          btn.className = isSel
            ? 'px-2.5 py-1 rounded bg-cyan-900 text-cyan-200 border border-cyan-400 font-bold text-[11px]'
            : 'px-2.5 py-1 rounded bg-[#111827] text-slate-400 border border-[#1f2937] hover:text-white text-[11px]';
          btn.textContent = `Paso #${th.step_number} (${th.status || th.verdict})`;
          btn.addEventListener('click', () => {
            selectedThoughtStepIndex = idx;
            renderSelectedAgentThought();
          });
          thoughtStepPills.appendChild(btn);
        });
      } else {
        thoughtStepSelectorBar.classList.add('hidden');
      }
    }

    const t = agentThoughts[selectedThoughtStepIndex] || agentThoughts[0];

    if (!t) {
      // Empty state
      if (yamlMetaProyecto) yamlMetaProyecto.textContent = thoughtsProjSelect ? thoughtsProjSelect.value || '-' : '-';
      if (yamlMetaIteracion) yamlMetaIteracion.textContent = 'v1';
      if (yamlMetaEmisor) yamlMetaEmisor.textContent = agentObj.id;
      if (yamlMetaReceptor) yamlMetaReceptor.textContent = '-';
      if (yamlMetaEstado) yamlMetaEstado.textContent = 'IDLE';
      if (yamlMetaPrioridad) yamlMetaPrioridad.textContent = 'ALTA';
      if (yamlMetaTimestamp) yamlMetaTimestamp.textContent = '-';

      if (thoughtDocTitle) thoughtDocTitle.textContent = `${agentObj.name} (Sin entregable)`;
      if (thoughtMarkdownViewer) {
        thoughtMarkdownViewer.innerHTML = `
          <div class="text-center text-slate-500 py-12 font-mono text-xs">
            <span class="text-2xl block mb-2">${agentObj.icon}</span>
            No se encontró entregable registrado para <strong>${agentObj.name}</strong> en este proyecto.
          </div>
        `;
      }
      return;
    }

    // Extract YAML frontmatter dictionary
    const fm = t.frontmatter || {};
    if (yamlMetaProyecto) yamlMetaProyecto.textContent = fm.id_proyecto || t.project_id || '-';
    if (yamlMetaIteracion) yamlMetaIteracion.textContent = `v${fm.version_iteracion || 1}`;
    if (yamlMetaEmisor) yamlMetaEmisor.textContent = fm.agente_emisor || t.agent_id || '-';
    if (yamlMetaReceptor) yamlMetaReceptor.textContent = fm.agente_receptor || 'siguiente_fase';

    const estadoVal = fm.estado || t.status || 'COMPLETADO';
    if (yamlMetaEstado) {
      yamlMetaEstado.textContent = estadoVal;
      let stColor = 'text-cyan-300';
      if (estadoVal.includes('APROBADO') || estadoVal.includes('AUTORIZADO') || estadoVal.includes('LISTO')) stColor = 'text-emerald-400';
      else if (estadoVal.includes('RECHAZADO') || estadoVal.includes('BLOQUEADO')) stColor = 'text-rose-400';
      yamlMetaEstado.className = `font-semibold truncate ${stColor}`;
    }

    if (yamlMetaPrioridad) yamlMetaPrioridad.textContent = fm.prioridad || 'ALTA';
    if (yamlMetaTimestamp) yamlMetaTimestamp.textContent = fm.timestamp || t.created_at || '-';

    if (thoughtDocTitle) {
      thoughtDocTitle.textContent = `Paso #${t.step_number} • Veredicto: ${t.verdict || 'OK'} (${t.tokens_in + t.tokens_out} tokens)`;
    }

    if (thoughtMarkdownViewer) {
      thoughtMarkdownViewer.innerHTML = renderFormattedMarkdown(t.raw_response);

      // Attach accordion toggle handlers to each section header
      thoughtMarkdownViewer.querySelectorAll('.thought-accordion-header').forEach(header => {
        header.addEventListener('click', () => {
          const card = header.closest('.thought-accordion-card');
          if (!card) return;
          const body = card.querySelector('.thought-accordion-body');
          const chevron = card.querySelector('.thought-accordion-chevron');
          if (!body) return;
          const isHidden = body.classList.contains('hidden');
          if (isHidden) {
            body.classList.remove('hidden');
            if (chevron) chevron.textContent = '▼';
            header.classList.add('border-b', 'border-[#1f2937]', 'bg-[#101728]');
            header.classList.remove('bg-[#0e1422]');
          } else {
            body.classList.add('hidden');
            if (chevron) chevron.textContent = '▶';
            header.classList.remove('border-b', 'border-[#1f2937]', 'bg-[#101728]');
            header.classList.add('bg-[#0e1422]');
          }
        });
      });
    }
  }

  // Render Left Sidebar Pills of the 13 Official Agents
  function renderThoughtsAgentPills() {
    if (!thoughtsAgentPills) return;
    thoughtsAgentPills.innerHTML = '';

    OFFICIAL_13_AGENTS.forEach(ag => {
      const count = allProjectThoughts.filter(t => t.agent_id === ag.id).length;
      const btn = document.createElement('button');
      btn.setAttribute('data-agent-id', ag.id);
      const isSelected = ag.id === selectedThoughtAgentId;

      btn.className = isSelected
        ? 'thought-agent-pill w-full text-left py-1.5 px-2.5 rounded-lg border border-cyan-400 bg-cyan-950/70 shadow-lg shadow-cyan-950/50 flex items-center justify-between transition shrink-0'
        : 'thought-agent-pill w-full text-left py-1.5 px-2.5 rounded-lg border border-[#1f2937] bg-[#111827] hover:border-slate-600 hover:bg-slate-800/60 flex items-center justify-between transition shrink-0';

      let countBadge = '<span class="text-[10px] text-slate-500 font-mono">Inactivo</span>';
      if (count > 0) {
        countBadge = `<span class="text-[10px] text-emerald-400 bg-emerald-950/80 border border-emerald-600/50 px-1.5 py-0.5 rounded font-mono font-bold">${count} ${count === 1 ? 'doc' : 'docs'}</span>`;
      }

      btn.innerHTML = `
        <div class="flex items-center gap-2 min-w-0">
          <span class="text-base">${ag.icon}</span>
          <div class="truncate leading-tight">
            <div class="text-xs font-bold text-white truncate leading-tight">${ag.name}</div>
            <div class="text-[10px] font-mono text-slate-400 truncate leading-tight">${ag.id}</div>
          </div>
        </div>
        ${countBadge}
      `;

      btn.addEventListener('click', () => {
        selectedThoughtAgentId = ag.id;
        selectedThoughtStepIndex = 0;
        renderSelectedAgentThought();
      });

      thoughtsAgentPills.appendChild(btn);
    });
  }

  // Expand / Collapse All Sections in Document Viewer
  if (btnExpandAllSections) {
    btnExpandAllSections.addEventListener('click', () => {
      if (!thoughtMarkdownViewer) return;
      thoughtMarkdownViewer.querySelectorAll('.thought-accordion-card').forEach(card => {
        const body = card.querySelector('.thought-accordion-body');
        const chevron = card.querySelector('.thought-accordion-chevron');
        const header = card.querySelector('.thought-accordion-header');
        if (body) body.classList.remove('hidden');
        if (chevron) chevron.textContent = '▼';
        if (header) {
          header.classList.add('border-b', 'border-[#1f2937]', 'bg-[#101728]');
          header.classList.remove('bg-[#0e1422]');
        }
      });
    });
  }

  if (btnCollapseAllSections) {
    btnCollapseAllSections.addEventListener('click', () => {
      if (!thoughtMarkdownViewer) return;
      thoughtMarkdownViewer.querySelectorAll('.thought-accordion-card').forEach(card => {
        const body = card.querySelector('.thought-accordion-body');
        const chevron = card.querySelector('.thought-accordion-chevron');
        const header = card.querySelector('.thought-accordion-header');
        if (body) body.classList.add('hidden');
        if (chevron) chevron.textContent = '▶';
        if (header) {
          header.classList.remove('border-b', 'border-[#1f2937]', 'bg-[#101728]');
          header.classList.add('bg-[#0e1422]');
        }
      });
    });
  }

  // Toggle Top YAML Metadata Panel
  if (btnToggleYamlMeta && thoughtYamlMetaGrid) {
    btnToggleYamlMeta.addEventListener('click', () => {
      const isHidden = thoughtYamlMetaGrid.classList.contains('hidden');
      if (isHidden) {
        thoughtYamlMetaGrid.classList.remove('hidden');
        if (yamlMetaChevron) yamlMetaChevron.textContent = '▼';
      } else {
        thoughtYamlMetaGrid.classList.add('hidden');
        if (yamlMetaChevron) yamlMetaChevron.textContent = '▶';
      }
    });
  }
  if (btnCopyThoughtOutput) {
    btnCopyThoughtOutput.addEventListener('click', async () => {
      const agentThoughts = allProjectThoughts.filter(t => t.agent_id === selectedThoughtAgentId);
      const t = agentThoughts[selectedThoughtStepIndex] || agentThoughts[0];
      if (t && t.raw_response) {
        try {
          await navigator.clipboard.writeText(t.raw_response);
          const origHtml = btnCopyThoughtOutput.innerHTML;
          btnCopyThoughtOutput.innerHTML = '<span class="text-emerald-400 font-bold">✓ Copiado!</span>';
          setTimeout(() => { btnCopyThoughtOutput.innerHTML = origHtml; }, 2000);
        } catch (err) {
          console.warn('Fallo al copiar al portapapeles:', err);
        }
      }
    });
  }

  async function loadThoughts() {
    const proj = thoughtsProjSelect ? thoughtsProjSelect.value : '';
    let url = '/api/v1/telemetry/thoughts?limit=100';
    if (proj) url += `&project_id=${encodeURIComponent(proj)}`;

    try {
      const resp = await fetch(url);
      if (!resp.ok) return;
      const data = await resp.json();
      allProjectThoughts = data.thoughts || [];

      if (thoughtsCountBadge) {
        thoughtsCountBadge.textContent = `${allProjectThoughts.length} entregables`;
      }

      renderThoughtsAgentPills();
      renderSelectedAgentThought();
    } catch (err) {
      console.warn('Error loading thoughts:', err);
    }
  }

  if (btnRefreshThoughts) btnRefreshThoughts.addEventListener('click', loadThoughts);
  if (thoughtsProjSelect) thoughtsProjSelect.addEventListener('change', () => {
    selectedThoughtStepIndex = 0;
    loadThoughts();
  });

  // --- 6. Tab 3: Agent Usage & Stats Component ---
  const statsTotalTasks = document.getElementById('stats-total-tasks');
  const statsCurrentIteration = document.getElementById('stats-current-iteration');
  const statsAvgLatency = document.getElementById('stats-avg-latency');
  const statsQaSuccess = document.getElementById('stats-qa-success');
  const statsProjSelect = document.getElementById('stats-project-select');
  const btnRefreshStats = document.getElementById('btn-refresh-stats');
  const agentStatsGrid = document.getElementById('agent-stats-grid');

  async function loadAgentStats() {
    if (!agentStatsGrid) return;
    const proj = statsProjSelect ? statsProjSelect.value : (thoughtsProjSelect ? thoughtsProjSelect.value : '');
    let url = '/api/v1/telemetry/agent-stats';
    if (proj) url += `?project_id=${encodeURIComponent(proj)}`;

    try {
      const resp = await fetch(url);
      if (!resp.ok) return;
      const data = await resp.json();
      const agents = data.agents || [];

      // Update Top KPIs
      if (statsTotalTasks) statsTotalTasks.textContent = (data.total_nodes_executed || 0).toLocaleString();
      if (statsCurrentIteration) statsCurrentIteration.textContent = `v${data.current_iteration || 1}`;
      if (statsAvgLatency) statsAvgLatency.textContent = `${((data.avg_node_duration_ms || 0) / 1000).toFixed(2)}s`;
      if (statsQaSuccess) statsQaSuccess.textContent = `${(data.qa_success_rate || 100).toFixed(1)}%`;

      // Render 13 Agent Cards Grid
      agentStatsGrid.innerHTML = '';
      agents.forEach(ag => {
        const card = document.createElement('div');
        card.className = 'p-3.5 rounded-xl bg-[#0b0f19] border border-[#1f2937] flex flex-col justify-between gap-3 font-mono text-xs hover:border-cyan-500/60 transition shadow-sm';

        // Badge styling
        const badge = ag.status_badge || 'IDLE';
        let badgeStyle = 'bg-slate-800 text-slate-400 border-slate-700';
        if (badge === 'APPROVED') {
          badgeStyle = 'bg-emerald-950/80 text-emerald-300 border-emerald-500/60 font-bold';
        } else if (badge === 'WORKING') {
          badgeStyle = 'bg-cyan-950/80 text-cyan-300 border-cyan-400 animate-pulse font-bold';
        } else if (badge === 'BLOCKED') {
          badgeStyle = 'bg-rose-950/80 text-rose-300 border-rose-500/60 font-bold';
        }

        const share = ag.token_share_pct || 0;

        card.innerHTML = `
          <div>
            <div class="flex items-center justify-between gap-2 border-b border-[#1f2937] pb-2">
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-xl">${ag.icon}</span>
                <div class="truncate">
                  <div class="font-bold text-white text-xs truncate">${ag.name}</div>
                  <div class="text-[10px] text-slate-500 truncate font-mono">${ag.agent_id}</div>
                </div>
              </div>
              <span class="text-[10px] px-2 py-0.5 rounded border uppercase ${badgeStyle}">
                ${badge}
              </span>
            </div>

            <div class="grid grid-cols-2 gap-2 text-[11px] text-slate-400 pt-2.5">
              <div>Invocaciones: <strong class="text-white">${ag.tasks_count}</strong></div>
              <div>Tokens: <strong class="text-cyan-400">${ag.total_tokens.toLocaleString()}</strong></div>
              <div>Duración Med: <strong class="text-slate-300">${((ag.avg_duration_ms || 0) / 1000).toFixed(2)}s</strong></div>
              <div>Aprobación: <strong class="text-emerald-400">${ag.approval_rate}%</strong></div>
            </div>
          </div>

          <div class="pt-2 border-t border-[#1f2937]/60">
            <div class="flex items-center justify-between text-[10px] text-slate-400 mb-1">
              <span>Peso en Proyecto:</span>
              <span class="font-bold text-cyan-300">${share}%</span>
            </div>
            <div class="w-full bg-slate-900 rounded-full h-2 overflow-hidden border border-slate-800">
              <div class="bg-gradient-to-r from-cyan-500 to-emerald-400 h-2 rounded-full transition-all duration-500" style="width: ${Math.min(100, Math.max(share > 0 ? 3 : 0, share))}%"></div>
            </div>
          </div>
        `;
        agentStatsGrid.appendChild(card);
      });
    } catch (err) {
      console.warn('Error loading agent stats:', err);
    }
  }

  if (btnRefreshStats) btnRefreshStats.addEventListener('click', loadAgentStats);
  if (statsProjSelect) statsProjSelect.addEventListener('change', loadAgentStats);

  // --- 7. Tab 4: Token & Cost Monitor Component ---
  const costProjSelect = document.getElementById('cost-project-select');
  const btnRefreshCost = document.getElementById('btn-refresh-cost');

  const agentIconsMap = {
    agente_00_ceo: '👔',
    agente_01_pm: '📋',
    agente_02_architect: '📐',
    agente_11_ui_ux: '🎨',
    agente_03_laravel: '🐘',
    agente_04_fastapi: '⚡',
    agente_05_qa_php: '🔬',
    agente_06_qa_python: '🐍',
    agente_07_devops: '⚙️',
    agente_10_ciso: '🛡️',
    agente_08_docs: '📚',
    agente_12_marketing: '📣',
    agente_13_sales_analytics: '💹',
    agente_09_growth: '📈'
  };

  async function loadCostBreakdown() {
    const costTokensIn = document.getElementById('cost-tokens-in');
    const costTokensOut = document.getElementById('cost-tokens-out');
    const costTotalUsd = document.getElementById('cost-total-usd');
    const costSavedUsd = document.getElementById('cost-saved-usd');
    const agentCostTbody = document.getElementById('agent-cost-tbody');
    const pricingTiersList = document.getElementById('pricing-tiers-list');
    const costProjSelect = document.getElementById('cost-project-select');

    const proj = costProjSelect ? costProjSelect.value : '';
    let url = '/api/v1/telemetry/cost-breakdown';
    if (proj) url += `?project_id=${encodeURIComponent(proj)}`;

    try {
      const resp = await fetch(url);
      if (!resp.ok) return;
      const data = await resp.json();

      if (costTokensIn) costTokensIn.textContent = (data.total_tokens_in || 0).toLocaleString();
      if (costTokensOut) costTokensOut.textContent = (data.total_tokens_out || 0).toLocaleString();
      if (costTotalUsd) {
        const c = data.total_cost_usd || 0;
        costTotalUsd.textContent = `$${c < 1 ? c.toFixed(4) : c.toFixed(2)}`;
      }
      if (costSavedUsd) costSavedUsd.textContent = `$${(data.saved_usd || 0).toFixed(2)}`;

      if (agentCostTbody) {
        agentCostTbody.innerHTML = '';
        (data.by_agent || []).forEach(ag => {
          const icon = agentIconsMap[ag.agent_id] || '🤖';
          const tr = document.createElement('tr');
          tr.className = 'hover:bg-slate-800/40 transition border-b border-[#1f2937]/50 font-mono';
          const costStr = ag.cost_usd < 1 ? ag.cost_usd.toFixed(4) : ag.cost_usd.toFixed(2);
          tr.innerHTML = `
            <td class="p-2.5">
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-base">${icon}</span>
                <div class="truncate">
                  <div class="font-bold text-white text-xs truncate">${ag.name}</div>
                  <div class="text-[10px] text-slate-500 font-mono truncate">${ag.agent_id}</div>
                </div>
              </div>
            </td>
            <td class="p-2.5 text-cyan-400 font-semibold">${ag.tokens.toLocaleString()}</td>
            <td class="p-2.5">
              <div class="flex items-center gap-2">
                <div class="w-20 bg-[#0b0f19] rounded-full h-1.5 overflow-hidden border border-[#1f2937]">
                  <div class="bg-gradient-to-r from-cyan-500 to-blue-500 h-1.5 rounded-full" style="width: ${ag.pct_of_total}%"></div>
                </div>
                <span class="text-slate-300 text-xs">${ag.pct_of_total}%</span>
              </div>
            </td>
            <td class="p-2.5 text-amber-400 font-semibold text-right">$${costStr}</td>
          `;
          agentCostTbody.appendChild(tr);
        });
      }

      if (pricingTiersList) {
        pricingTiersList.innerHTML = '';
        (data.pricing_tiers || []).forEach(tier => {
          const item = document.createElement('div');
          item.className = 'p-3 rounded-lg bg-[#0b0f19] border border-[#1f2937] flex flex-col gap-1.5 hover:border-cyan-500/40 transition shadow-sm font-mono';
          item.innerHTML = `
            <div class="flex justify-between items-center">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold text-white">${tier.name}</span>
                <span class="text-xs px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800 font-mono font-semibold">$${tier.price_usd}/mes</span>
              </div>
              <span class="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-600 font-bold font-mono">
                Margen: ${tier.net_margin_pct}%
              </span>
            </div>
            <div class="text-[11px] text-slate-400 flex justify-between font-mono pt-1 border-t border-[#1f2937]/50">
              <span>Stripe Fee: <strong class="text-slate-300">$${tier.stripe_fee_usd.toFixed(2)}</strong></span>
              <span>Max COGS: <strong class="text-slate-300">$${tier.max_cogs_usd.toFixed(2)}</strong></span>
              <span class="text-emerald-400 font-semibold flex items-center gap-1"><span>✓</span> Zero-Touch</span>
            </div>
          `;
          pricingTiersList.appendChild(item);
        });
      }
    } catch (err) {
      console.warn('Error loading cost breakdown:', err);
    }
  }

  if (costProjSelect) costProjSelect.addEventListener('change', loadCostBreakdown);
  if (btnRefreshCost) btnRefreshCost.addEventListener('click', loadCostBreakdown);

  // --- 8. Tab 5: Security & Circuit Breakers Component ---
  const circuitBreakersContainer = document.getElementById('circuit-breakers-container');
  const securityEventsContainer = document.getElementById('security-events-container');
  const secProjSelect = document.getElementById('sec-project-select');
  const btnRefreshSecurity = document.getElementById('btn-refresh-security');
  const breakersCountBadge = document.getElementById('breakers-count-badge');
  const securityEventsCountBadge = document.getElementById('security-events-count-badge');
  const securityShieldBadge = document.getElementById('security-shield-badge');

  async function loadSecurityStatus() {
    try {
      const selectedProj = secProjSelect ? secProjSelect.value : '';
      let url = '/api/v1/telemetry/security';
      if (selectedProj) {
        url += `?project_id=${encodeURIComponent(selectedProj)}`;
      }

      const resp = await fetch(url);
      if (!resp.ok) return;
      const data = await resp.json();

      // Top Security Shield Badge
      if (securityShieldBadge) {
        const tripped = data.circuit_breakers_tripped || 0;
        if (tripped > 0) {
          securityShieldBadge.className = 'px-3 py-1.5 rounded bg-red-950 text-red-400 border border-red-800 font-bold tracking-wider animate-pulse';
          securityShieldBadge.textContent = `⚠️ CIRCUIT BREAKER (${tripped} TRIPPED)`;
        } else {
          securityShieldBadge.className = 'px-3 py-1.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold tracking-wider';
          securityShieldBadge.textContent = '🛡️ SHIELD ACTIVE (0 TRIPPED)';
        }
      }

      // Circuit Breakers List
      if (circuitBreakersContainer) {
        circuitBreakersContainer.innerHTML = '';
        const monitored = data.projects_monitored || [];
        if (breakersCountBadge) {
          breakersCountBadge.textContent = `${monitored.length} ${monitored.length === 1 ? 'proyecto' : 'proyectos'}`;
        }

        if (monitored.length === 0) {
          circuitBreakersContainer.innerHTML = '<div class="p-4 text-slate-500 text-center font-mono">No hay proyectos activos registrados.</div>';
        } else {
          monitored.forEach(item => {
            const row = document.createElement('div');
            const isTripped = item.tripped;
            const isCompleted = item.status === 'LANZAMIENTO_AUTORIZADO' || item.status === 'CICLO_DE_SOFTWARE_COMPLETADO_100' || item.last_verdict === 'APROBADO';
            const borderCol = isTripped ? 'border-red-500/50 bg-red-950/20' : (isCompleted ? 'border-emerald-500/40 bg-[#0b0f19]' : 'border-[#1f2937] bg-[#0b0f19]');
            row.className = `p-3 rounded-lg border ${borderCol} flex items-center justify-between transition hover:border-slate-600`;
            row.innerHTML = `
              <div class="flex flex-col gap-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="font-bold text-white text-xs tracking-wide">${escapeHtml(item.project_id)}</span>
                  <span class="text-[10px] px-2 py-0.5 rounded font-mono ${isCompleted ? 'bg-emerald-950/80 text-emerald-400 border border-emerald-800/60' : (isTripped ? 'bg-red-950/80 text-red-400 border border-red-800/60' : 'bg-slate-800 text-slate-300')}">${escapeHtml(item.status)}</span>
                </div>
                <div class="text-[11px] text-slate-400 font-mono flex items-center gap-3">
                  <span>Loop: <strong class="text-cyan-400">${item.iteration}</strong>/${item.max_iterations}</span>
                  <span>•</span>
                  <span>Veredicto: <strong class="${isTripped ? 'text-red-400' : 'text-emerald-400'}">${escapeHtml(item.last_verdict)}</strong></span>
                </div>
              </div>
              <span class="px-2.5 py-1 rounded text-[10px] font-bold font-mono tracking-wider shrink-0 ${isTripped ? 'bg-red-950 text-red-400 border border-red-800 animate-pulse' : (isCompleted ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-slate-900 text-slate-300 border border-slate-700')}">
                ${isTripped ? '⚠️ TRIPPED' : (isCompleted ? '✅ RESOLVED' : '🟢 NORMAL')}
              </span>
            `;
            circuitBreakersContainer.appendChild(row);
          });
        }
      }

      // Security Events Audit Trail
      if (securityEventsContainer) {
        securityEventsContainer.innerHTML = '';
        const events = data.recent_security_events || [];
        if (securityEventsCountBadge) {
          securityEventsCountBadge.textContent = `${events.length} ${events.length === 1 ? 'evento' : 'eventos'}`;
        }

        if (events.length === 0) {
          securityEventsContainer.innerHTML = '<div class="p-4 text-slate-500 text-center font-mono">No se registran alertas de seguridad o vetos críticos para el filtro seleccionado.</div>';
        } else {
          events.forEach(ev => {
            const card = document.createElement('div');
            const isCrit = ev.level === 'CRITICAL';
            const isCiso = ev.agent_id.includes('ciso');
            const isPHP = ev.agent_id.includes('php');
            const isPython = ev.agent_id.includes('python');
            const agentIcon = isCiso ? '🛡️' : (isPHP ? '🐘' : (isPython ? '⚡' : '👔'));
            const borderCol = isCrit ? 'border-red-900/60 bg-red-950/20' : 'border-amber-900/60 bg-amber-950/20';

            card.className = `p-3 rounded-lg border ${borderCol} flex flex-col gap-2 transition hover:border-slate-500`;
            card.innerHTML = `
              <div class="flex items-center justify-between text-xs">
                <div class="flex items-center gap-1.5 font-bold ${isCrit ? 'text-red-400' : 'text-amber-400'}">
                  <span>${agentIcon}</span>
                  <span class="tracking-wide">[${escapeHtml(ev.level)}] ${escapeHtml(ev.agent_id)}</span>
                </div>
                <span class="text-[10px] text-slate-500 font-mono">${escapeHtml(ev.timestamp.replace('T', ' ').substring(0, 19))} UTC</span>
              </div>
              <p class="text-slate-300 text-xs leading-relaxed font-sans">${escapeHtml(ev.message)}</p>
              <div class="flex items-center justify-between text-[10px] pt-1.5 border-t border-slate-800/80 font-mono">
                <span class="text-slate-400">Proyecto: <strong class="text-slate-200">${escapeHtml(ev.project_id)}</strong></span>
                ${ev.culprit ? `<span class="px-2 py-0.5 rounded bg-red-950/90 text-red-300 border border-red-900/80 font-semibold font-mono">Culprit: ${escapeHtml(ev.culprit)}</span>` : '<span class="text-slate-500 font-mono">Sin responsable culpable</span>'}
              </div>
            `;
            securityEventsContainer.appendChild(card);
          });
        }
      }
    } catch (err) {
      console.warn('Error loading security status:', err);
    }
  }

  if (secProjSelect) secProjSelect.addEventListener('change', loadSecurityStatus);
  if (btnRefreshSecurity) btnRefreshSecurity.addEventListener('click', loadSecurityStatus);

  // --- 9. Tab 6: Database & Artifacts Inspector Component ---
  const dbTableSelect = document.getElementById('db-table-select');
  const dbSearchInput = document.getElementById('db-search-input');
  const btnDbRefresh = document.getElementById('btn-db-refresh');
  const dbTableHead = document.getElementById('db-table-head');
  const dbTableBody = document.getElementById('db-table-body');
  const dbRowsCount = document.getElementById('db-rows-count');
  const btnDbPrev = document.getElementById('btn-db-prev');
  const btnDbNext = document.getElementById('btn-db-next');
  const dbPageInfo = document.getElementById('db-page-info');

  const artProjectSelect = document.getElementById('artifacts-project-select');
  const artifactsFileList = document.getElementById('artifacts-file-list');
  const previewFilename = document.getElementById('preview-filename');
  const previewFilesize = document.getElementById('preview-filesize');
  const previewContent = document.getElementById('preview-content');
  const btnCopyArtifact = document.getElementById('btn-copy-artifact');

  let dbCurrentPage = 1;
  const dbPageSize = 25;
  let dbTotalRows = 0;
  let dbTablesLoaded = false;
  let currentActiveFileBtn = null;

  async function loadDatabaseTablesList() {
    if (!dbTableSelect) return;
    try {
      const resp = await fetch('/api/v1/telemetry/database/tables');
      if (!resp.ok) return;
      const data = await resp.json();
      const tables = data.tables || [];
      if (tables.length > 0) {
        const curVal = dbTableSelect.value;
        dbTableSelect.innerHTML = '';
        tables.forEach(t => {
          const opt = document.createElement('option');
          opt.value = t.name;
          opt.textContent = `${t.name} (${t.row_count.toLocaleString()} filas)`;
          dbTableSelect.appendChild(opt);
        });
        if (curVal && tables.some(t => t.name === curVal)) {
          dbTableSelect.value = curVal;
        }
        dbTablesLoaded = true;
      }
    } catch (err) {
      console.warn('Error querying tables list:', err);
    }
  }

  async function loadDatabaseTable(resetPage = false) {
    if (!dbTableSelect || !dbTableHead || !dbTableBody) return;
    if (!dbTablesLoaded) {
      await loadDatabaseTablesList();
    }
    if (resetPage) dbCurrentPage = 1;

    const table = dbTableSelect.value;
    const search = dbSearchInput ? dbSearchInput.value.trim() : '';
    const offset = (dbCurrentPage - 1) * dbPageSize;

    let url = `/api/v1/telemetry/database/query?table=${encodeURIComponent(table)}&limit=${dbPageSize}&offset=${offset}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;

    try {
      const resp = await fetch(url);
      if (!resp.ok) return;
      const data = await resp.json();

      dbTotalRows = data.total_rows || 0;
      const totalPages = Math.max(1, Math.ceil(dbTotalRows / dbPageSize));
      if (dbCurrentPage > totalPages) dbCurrentPage = totalPages;

      if (dbRowsCount) {
        const start = dbTotalRows === 0 ? 0 : offset + 1;
        const end = Math.min(offset + data.rows.length, dbTotalRows);
        dbRowsCount.textContent = `${start}-${end} de ${dbTotalRows.toLocaleString()}`;
      }

      if (dbPageInfo) {
        dbPageInfo.textContent = `Pág. ${dbCurrentPage} / ${totalPages}`;
      }
      if (btnDbPrev) btnDbPrev.disabled = dbCurrentPage <= 1;
      if (btnDbNext) btnDbNext.disabled = dbCurrentPage >= totalPages;

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
        dbTableBody.innerHTML = `<tr><td colspan="${(data.columns || []).length || 1}" class="p-4 text-center text-slate-500">Tabla vacía o sin coincidencias de búsqueda.</td></tr>`;
        return;
      }

      data.rows.forEach(row => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-900/50 transition';
        data.columns.forEach(col => {
          const td = document.createElement('td');
          td.className = 'p-2 whitespace-nowrap max-w-[220px] truncate text-[11px]';
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

  if (dbTableSelect) {
    dbTableSelect.addEventListener('change', () => loadDatabaseTable(true));
  }
  if (btnDbRefresh) {
    btnDbRefresh.addEventListener('click', async () => {
      await loadDatabaseTablesList();
      loadDatabaseTable(false);
    });
  }
  if (dbSearchInput) {
    dbSearchInput.addEventListener('keyup', (e) => {
      if (e.key === 'Enter') loadDatabaseTable(true);
    });
  }
  if (btnDbPrev) {
    btnDbPrev.addEventListener('click', () => {
      if (dbCurrentPage > 1) {
        dbCurrentPage--;
        loadDatabaseTable(false);
      }
    });
  }
  if (btnDbNext) {
    btnDbNext.addEventListener('click', () => {
      const totalPages = Math.max(1, Math.ceil(dbTotalRows / dbPageSize));
      if (dbCurrentPage < totalPages) {
        dbCurrentPage++;
        loadDatabaseTable(false);
      }
    });
  }

  // Artifacts Explorer
  let artifactsLoadedForProject = null;

  async function loadArtifactsProjectSelector() {
    if (!artProjectSelect) return;
    if (artProjectSelect.options.length <= 1) {
      await loadProjectsList();
    }
    if (!artProjectSelect.value && artProjectSelect.options.length > 1) {
      artProjectSelect.selectedIndex = 1;
    }
    if (artProjectSelect.value && artifactsLoadedForProject !== artProjectSelect.value) {
      artProjectSelect.dispatchEvent(new Event('change'));
    }
  }

  if (artProjectSelect) {
    artProjectSelect.addEventListener('change', async () => {
      const pid = artProjectSelect.value;
      if (!pid || !artifactsFileList) {
        artifactsLoadedForProject = null;
        if (artifactsFileList) artifactsFileList.innerHTML = '<div class="p-3 text-slate-500 text-center">Selecciona un proyecto arriba.</div>';
        return;
      }

      artifactsLoadedForProject = pid;
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

        let firstBtnToClick = null;

        files.forEach((f, idx) => {
          const btn = document.createElement('button');
          btn.className = 'w-full text-left p-1.5 rounded hover:bg-slate-800/80 flex items-center justify-between gap-1 text-slate-300 transition text-[11px] border border-transparent';

          let icon = '📄';
          if (f.file_type === 'json') icon = '⚙️';
          else if (f.file_type === 'markdown') icon = '📝';
          else if (f.file_type === 'code') icon = '⚡';
          else if (f.file_type === 'yaml') icon = '📋';

          btn.innerHTML = `
            <div class="flex items-center gap-1.5 truncate">
              <span>${icon}</span>
              <span class="truncate">${escapeHtml(f.relative_path)}</span>
            </div>
            <span class="text-slate-500 text-[10px] whitespace-nowrap">${formatBytes(f.size_bytes)}</span>
          `;

          btn.addEventListener('click', () => {
            if (currentActiveFileBtn) {
              currentActiveFileBtn.classList.remove('bg-cyan-950/60', 'text-cyan-300', 'border-cyan-800/60');
            }
            btn.classList.add('bg-cyan-950/60', 'text-cyan-300', 'border-cyan-800/60');
            currentActiveFileBtn = btn;
            loadArtifactContent(pid, f.relative_path, f.size_bytes);
          });

          artifactsFileList.appendChild(btn);

          // Auto-select the first markdown deliverable or the first file
          if (!firstBtnToClick && (f.relative_path.includes('03_agente_00_ceo') || idx === 0)) {
            firstBtnToClick = btn;
          }
        });

        if (firstBtnToClick) {
          firstBtnToClick.click();
        }

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

  if (btnCopyArtifact && previewContent) {
    btnCopyArtifact.addEventListener('click', async () => {
      const text = previewContent.textContent;
      if (!text || text.includes('Haz clic en un archivo') || text.includes('Selecciona un proyecto')) return;
      try {
        await navigator.clipboard.writeText(text);
        const origHtml = btnCopyArtifact.innerHTML;
        btnCopyArtifact.innerHTML = '<span>✅</span> Copiado';
        btnCopyArtifact.classList.add('text-emerald-400', 'border-emerald-700');
        setTimeout(() => {
          btnCopyArtifact.innerHTML = origHtml;
          btnCopyArtifact.classList.remove('text-emerald-400', 'border-emerald-700');
        }, 2000);
      } catch (err) {
        console.warn('Error copying artifact content:', err);
      }
    });
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

  // =========================================================================
  // 10. WhatsApp Hub & Management System
  // =========================================================================

  const waStatusBadge = document.getElementById('wa-status-badge');
  const waKpiSessions = document.getElementById('wa-kpi-sessions');
  const waBtnTestMeta = document.getElementById('wa-btn-test-meta');
  const waDiagnosticAlert = document.getElementById('wa-diagnostic-alert');

  const waConfigForm = document.getElementById('wa-config-form');
  const waCfgEnabled = document.getElementById('wa-cfg-enabled');
  const waCfgPhoneId = document.getElementById('wa-cfg-phone-id');
  const waCfgToken = document.getElementById('wa-cfg-token');
  const waBtnToggleToken = document.getElementById('wa-btn-toggle-token');
  const waTokenStatusLabel = document.getElementById('wa-token-status-label');
  const waCfgVerify = document.getElementById('wa-cfg-verify');
  const waCfgSecret = document.getElementById('wa-cfg-secret');
  const waCfgAllowed = document.getElementById('wa-cfg-allowed');
  const waBtnSaveCfg = document.getElementById('wa-btn-save-cfg');
  const waSaveStatus = document.getElementById('wa-save-status');

  const waDisplayWebhookUrl = document.getElementById('wa-display-webhook-url');
  const waBtnCopyUrl = document.getElementById('wa-btn-copy-url');
  const waDisplayVerifyToken = document.getElementById('wa-display-verify-token');
  const waBtnCopyToken = document.getElementById('wa-btn-copy-token');
  const waBtnTestHandshake = document.getElementById('wa-btn-test-handshake');
  const waHandshakeResult = document.getElementById('wa-handshake-result');

  const waSimPhone = document.getElementById('wa-sim-phone');
  const waSimText = document.getElementById('wa-sim-text');
  const waBtnSimulate = document.getElementById('wa-btn-simulate');
  const waBtnSimReset = document.getElementById('wa-btn-sim-reset');
  const waSimBadge = document.getElementById('wa-sim-badge');
  const waSimOutput = document.getElementById('wa-sim-output');

  const waBtnRefreshSessions = document.getElementById('wa-btn-refresh-sessions');
  const waSessionsTableBody = document.getElementById('wa-sessions-table-body');

  async function loadWhatsAppHub() {
    // 1. Set default Webhook URL based on window.location
    if (waDisplayWebhookUrl) {
      waDisplayWebhookUrl.value = `${window.location.origin}/webhook/whatsapp`;
    }

    // 2. Fetch Status & Config
    try {
      const resp = await fetch('/api/v1/whatsapp/status');
      if (resp.ok) {
        const data = await resp.json();
        renderWhatsAppStatus(data);
      }
    } catch (err) {
      console.warn('Error fetching WhatsApp status:', err);
    }

    // 3. Fetch Active Sessions
    loadWhatsAppSessions();
  }

  function renderWhatsAppStatus(data) {
    const config = data.config || {};
    const isOnline = data.status === 'online';

    // Status Badge
    if (waStatusBadge) {
      if (isOnline && config.has_access_token && config.phone_number_id) {
        waStatusBadge.className = 'px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-400 border border-emerald-500/40';
        waStatusBadge.innerHTML = '🟢 GATEWAY ACTIVO (Meta Cloud API)';
      } else if (!isOnline) {
        waStatusBadge.className = 'px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-800 text-slate-400 border border-slate-700';
        waStatusBadge.innerHTML = '⚪ GATEWAY DESACTIVADO';
      } else {
        waStatusBadge.className = 'px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-600/50';
        waStatusBadge.innerHTML = '🟡 CREDENCIALES PENDIENTES';
      }
    }

    // KPIs
    if (waKpiSessions) {
      waKpiSessions.textContent = config.active_sessions_count || '0';
    }

    // Form inputs
    if (waCfgEnabled) waCfgEnabled.checked = !!config.enabled;
    if (waCfgPhoneId && !waCfgPhoneId.value) waCfgPhoneId.value = config.phone_number_id || '';
    if (waCfgVerify) waCfgVerify.value = config.verify_token || 'agentoffice_verify_2026';
    if (waDisplayVerifyToken) waDisplayVerifyToken.value = config.verify_token || 'agentoffice_verify_2026';
    if (waCfgAllowed && !waCfgAllowed.value) {
      waCfgAllowed.value = (config.allowed_phones || []).join(', ');
    }

    if (waTokenStatusLabel) {
      if (config.has_access_token) {
        waTokenStatusLabel.innerHTML = `<span class="text-emerald-400 font-semibold">✓ ${config.access_token_masked}</span>`;
      } else {
        waTokenStatusLabel.innerHTML = '<span class="text-amber-400">Sin configurar</span>';
      }
    }
  }

  async function loadWhatsAppSessions() {
    if (!waSessionsTableBody) return;
    try {
      const resp = await fetch('/api/v1/whatsapp/sessions');
      if (!resp.ok) {
        waSessionsTableBody.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-slate-500">Error al cargar sesiones.</td></tr>';
        return;
      }
      const sessions = await resp.json();
      if (!sessions || sessions.length === 0) {
        waSessionsTableBody.innerHTML = '<tr><td colspan="6" class="py-6 text-center text-slate-500">No hay sesiones activas de clientes aún. Usa el Sandbox arriba o envía un mensaje real.</td></tr>';
        return;
      }

      waSessionsTableBody.innerHTML = sessions.map(s => {
        let phaseColor = 'bg-slate-800 text-slate-300 border-slate-700';
        if (s.phase === 'INTAKE') phaseColor = 'bg-cyan-950 text-cyan-300 border-cyan-700/60';
        else if (s.phase === 'BUILDING') phaseColor = 'bg-amber-950 text-amber-300 border-amber-600/60';
        else if (s.phase === 'DEPLOYING') phaseColor = 'bg-purple-950 text-purple-300 border-purple-600/60';
        else if (s.phase === 'COMPLETED') phaseColor = 'bg-emerald-950 text-emerald-300 border-emerald-600/60';
        else if (s.phase === 'ERROR') phaseColor = 'bg-rose-950 text-rose-300 border-rose-600/60';

        const updatedStr = s.updated_at ? new Date(s.updated_at).toLocaleString() : '-';
        const projectDisplay = s.project_id ? `<span class="text-cyan-400 font-semibold">${escapeHtml(s.project_id)}</span>` : '<span class="text-slate-500">En definición</span>';

        return `
          <tr class="hover:bg-slate-800/30 transition">
            <td class="py-2.5 px-3 font-semibold text-white">${escapeHtml(s.phone_number)}</td>
            <td class="py-2.5 px-3">
              <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${phaseColor}">${escapeHtml(s.phase)}</span>
            </td>
            <td class="py-2.5 px-3">${projectDisplay}</td>
            <td class="py-2.5 px-3 text-center text-slate-300">${s.message_count || 0}</td>
            <td class="py-2.5 px-3 text-slate-400 text-[11px]">${updatedStr}</td>
            <td class="py-2.5 px-3 text-right">
              <button onclick="window.viewWhatsAppSession('${escapeHtml(s.phone_number)}')" class="px-2 py-1 rounded bg-[#0b0f19] hover:bg-slate-800 text-cyan-300 border border-[#1f2937] text-[11px] mr-1">
                Ver Chat
              </button>
              <button onclick="window.resetWhatsAppSession('${escapeHtml(s.phone_number)}')" class="px-2 py-1 rounded bg-rose-950/50 hover:bg-rose-900 text-rose-300 border border-rose-800/40 text-[11px]">
                Reset
              </button>
            </td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      console.warn('Error loading sessions:', err);
    }
  }

  // Window helper for row clicks
  window.viewWhatsAppSession = async function(phone) {
    try {
      const resp = await fetch(`/api/v1/whatsapp/sessions/${encodeURIComponent(phone)}`);
      if (!resp.ok) return;
      const session = await resp.json();
      if (waSimPhone) waSimPhone.value = phone;
      if (waSimOutput) {
        let historyText = `--- HISTORIAL DE SESIÓN (${phone}) ---\nFase: ${session.phase} | Proyecto: ${session.project_id || 'N/A'}\n\n`;
        (session.conversation_history || []).forEach(m => {
          const role = m.role === 'user' ? '👤 Usuario' : '🤖 Intake Agent';
          historyText += `${role}:\n${m.content}\n\n`;
        });
        waSimOutput.textContent = historyText.trim();
        waSimOutput.classList.remove('text-center', 'text-slate-500');
        waSimOutput.classList.add('text-slate-200');
      }
    } catch (err) {
      console.warn('Error viewing session:', err);
    }
  };

  window.resetWhatsAppSession = async function(phone) {
    if (!confirm(`¿Estás seguro de que deseas reiniciar la sesión de ${phone}?`)) return;
    try {
      const resp = await fetch(`/api/v1/whatsapp/sessions/${encodeURIComponent(phone)}/reset`, { method: 'POST' });
      if (resp.ok) {
        loadWhatsAppSessions();
        if (waSimPhone && waSimPhone.value === phone && waSimOutput) {
          waSimOutput.textContent = `Sesión reiniciada para ${phone}. Listo para una nueva idea.`;
        }
      }
    } catch (err) {
      console.warn('Error resetting session:', err);
    }
  };

  // Toggle show/hide token
  if (waBtnToggleToken && waCfgToken) {
    waBtnToggleToken.addEventListener('click', () => {
      if (waCfgToken.type === 'password') {
        waCfgToken.type = 'text';
        waBtnToggleToken.textContent = '🔒';
      } else {
        waCfgToken.type = 'password';
        waBtnToggleToken.textContent = '👁️';
      }
    });
  }

  // Save Config Form
  if (waConfigForm) {
    waConfigForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (waBtnSaveCfg) {
        waBtnSaveCfg.disabled = true;
        waBtnSaveCfg.innerHTML = '<span>⏳</span> Guardando...';
      }

      const payload = {
        enabled: waCfgEnabled ? waCfgEnabled.checked : false,
        phone_number_id: waCfgPhoneId ? waCfgPhoneId.value.trim() : '',
        access_token: waCfgToken ? waCfgToken.value.trim() : '',
        verify_token: waCfgVerify ? waCfgVerify.value.trim() : 'agentoffice_verify_2026',
        app_secret: waCfgSecret ? waCfgSecret.value.trim() : '',
        allowed_phones: waCfgAllowed ? waCfgAllowed.value.split(',').map(p => p.trim()).filter(Boolean) : []
      };

      try {
        const resp = await fetch('/api/v1/whatsapp/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const resData = await resp.json();
        if (resp.ok) {
          if (waSaveStatus) {
            waSaveStatus.textContent = '✅ Guardado correctamente en .env';
            waSaveStatus.classList.remove('hidden', 'text-rose-400');
            waSaveStatus.classList.add('text-emerald-400');
            setTimeout(() => waSaveStatus.classList.add('hidden'), 4000);
          }
          loadWhatsAppHub();
        } else {
          throw new Error(resData.detail || 'Error al guardar');
        }
      } catch (err) {
        if (waSaveStatus) {
          waSaveStatus.textContent = `❌ ${err.message}`;
          waSaveStatus.classList.remove('hidden', 'text-emerald-400');
          waSaveStatus.classList.add('text-rose-400');
        }
      } finally {
        if (waBtnSaveCfg) {
          waBtnSaveCfg.disabled = false;
          waBtnSaveCfg.innerHTML = '<span>💾</span> Guardar en .env y Aplicar';
        }
      }
    });
  }

  // Test Meta Ping Button
  if (waBtnTestMeta) {
    waBtnTestMeta.addEventListener('click', async () => {
      const origHtml = waBtnTestMeta.innerHTML;
      waBtnTestMeta.innerHTML = '<span>⏳</span> Probando Meta...';
      waBtnTestMeta.disabled = true;
      if (waDiagnosticAlert) waDiagnosticAlert.classList.add('hidden');

      try {
        const resp = await fetch('/api/v1/whatsapp/status?test_meta=true');
        const data = await resp.json();
        const meta = data.meta_connectivity;

        if (waDiagnosticAlert) {
          waDiagnosticAlert.classList.remove('hidden');
          if (meta && meta.connected) {
            const d = meta.details || {};
            waDiagnosticAlert.className = 'p-3.5 rounded-xl border border-emerald-500/40 bg-emerald-950/70 text-emerald-200 text-xs font-mono';
            waDiagnosticAlert.innerHTML = `
              <div class="font-bold text-emerald-300 flex items-center gap-2">
                <span>✅</span> Conexión con Meta Graph API v21.0 Exitosa
              </div>
              <div class="mt-1 text-slate-300">
                • <strong>Teléfono Registrado:</strong> ${escapeHtml(d.display_phone_number)} | <strong>Nombre:</strong> ${escapeHtml(d.verified_name)}<br>
                • <strong>ID:</strong> ${escapeHtml(d.id)} | <strong>Calidad:</strong> ${escapeHtml(d.quality_rating)}
              </div>
            `;
          } else {
            const err = (meta && meta.error) || 'Fallo de conexión';
            waDiagnosticAlert.className = 'p-3.5 rounded-xl border border-rose-500/40 bg-rose-950/70 text-rose-200 text-xs font-mono';
            waDiagnosticAlert.innerHTML = `
              <div class="font-bold text-rose-300 flex items-center gap-2">
                <span>❌</span> No se pudo conectar con Meta
              </div>
              <div class="mt-1 text-slate-300">
                ${escapeHtml(err)}<br>
                <span class="text-[11px] text-slate-400">Verifica que el Phone Number ID y el Access Token sean válidos y no hayan caducado.</span>
              </div>
            `;
          }
        }
      } catch (err) {
        if (waDiagnosticAlert) {
          waDiagnosticAlert.classList.remove('hidden');
          waDiagnosticAlert.className = 'p-3.5 rounded-xl border border-rose-500/40 bg-rose-950/70 text-rose-200 text-xs font-mono';
          waDiagnosticAlert.innerHTML = `❌ Error de red local: ${escapeHtml(err.message)}`;
        }
      } finally {
        waBtnTestMeta.innerHTML = origHtml;
        waBtnTestMeta.disabled = false;
      }
    });
  }

  // Copy URL and Token buttons
  if (waBtnCopyUrl && waDisplayWebhookUrl) {
    waBtnCopyUrl.addEventListener('click', async () => {
      await navigator.clipboard.writeText(waDisplayWebhookUrl.value);
      waBtnCopyUrl.textContent = '✅';
      setTimeout(() => waBtnCopyUrl.textContent = '📋', 2000);
    });
  }

  if (waBtnCopyToken && waDisplayVerifyToken) {
    waBtnCopyToken.addEventListener('click', async () => {
      await navigator.clipboard.writeText(waDisplayVerifyToken.value);
      waBtnCopyToken.textContent = '✅';
      setTimeout(() => waBtnCopyToken.textContent = '📋', 2000);
    });
  }

  // Test Handshake Local button
  if (waBtnTestHandshake) {
    waBtnTestHandshake.addEventListener('click', async () => {
      const token = waDisplayVerifyToken ? waDisplayVerifyToken.value : 'agentoffice_verify_2026';
      const challenge = '123456';
      if (!waHandshakeResult) return;
      waHandshakeResult.classList.remove('hidden');
      waHandshakeResult.textContent = 'Ejecutando handshake GET /webhook/whatsapp...';

      try {
        const resp = await fetch(`/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=${encodeURIComponent(token)}&hub.challenge=${challenge}`);
        const text = await resp.text();
        if (resp.ok && text.trim() === challenge) {
          waHandshakeResult.className = 'text-[11px] font-mono p-2 rounded bg-emerald-950/60 border border-emerald-500/40 text-emerald-300';
          waHandshakeResult.textContent = `✅ Handshake exitoso (HTTP 200). Meta validará este webhook correctamente.`;
        } else {
          waHandshakeResult.className = 'text-[11px] font-mono p-2 rounded bg-rose-950/60 border border-rose-500/40 text-rose-300';
          waHandshakeResult.textContent = `❌ Error en handshake (HTTP ${resp.status}): ${text}`;
        }
      } catch (err) {
        waHandshakeResult.className = 'text-[11px] font-mono p-2 rounded bg-rose-950/60 border border-rose-500/40 text-rose-300';
        waHandshakeResult.textContent = `❌ Error: ${err.message}`;
      }
    });
  }

  // Simulate Message in Sandbox
  if (waBtnSimulate) {
    waBtnSimulate.addEventListener('click', async () => {
      const phone = waSimPhone ? waSimPhone.value.trim() : '+34600123456';
      const text = waSimText ? waSimText.value.trim() : '';
      if (!text) {
        alert('Por favor ingresa un mensaje para simular.');
        return;
      }

      if (waSimBadge) {
        waSimBadge.textContent = '⏳ Procesando con Intake Agent...';
        waSimBadge.className = 'text-cyan-400 font-bold';
      }
      if (waSimOutput) {
        waSimOutput.classList.remove('text-center', 'text-slate-500');
        waSimOutput.classList.add('text-slate-300');
        waSimOutput.textContent = `[Simulando mensaje de ${phone}]...\n"${text}"\n\nEsperando respuesta del Intake Agent...`;
      }
      waBtnSimulate.disabled = true;

      try {
        const resp = await fetch('/api/v1/whatsapp/simulate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ phone, text })
        });
        const data = await resp.json();
        if (resp.ok) {
          if (waSimBadge) {
            const phase = data.session ? data.session.phase : 'OK';
            waSimBadge.textContent = `Fase: ${phase}`;
            waSimBadge.className = 'text-emerald-400 font-bold';
          }
          if (waSimOutput) {
            waSimOutput.textContent = `🤖 Respuesta del Intake Agent:\n\n${data.reply || 'Mensaje procesado'}`;
          }
          if (waSimText) waSimText.value = '';
          loadWhatsAppSessions();
        } else {
          throw new Error(data.detail || 'Error al simular');
        }
      } catch (err) {
        if (waSimBadge) {
          waSimBadge.textContent = 'Error';
          waSimBadge.className = 'text-rose-400 font-bold';
        }
        if (waSimOutput) {
          waSimOutput.textContent = `❌ Error en simulación: ${err.message}`;
        }
      } finally {
        waBtnSimulate.disabled = false;
      }
    });
  }

  // Sim Reset button
  if (waBtnSimReset) {
    waBtnSimReset.addEventListener('click', async () => {
      const phone = waSimPhone ? waSimPhone.value.trim() : '+34600123456';
      if (!confirm(`¿Reiniciar conversación (/reset) para ${phone}?`)) return;
      try {
        const resp = await fetch(`/api/v1/whatsapp/sessions/${encodeURIComponent(phone)}/reset`, { method: 'POST' });
        if (resp.ok) {
          if (waSimOutput) {
            waSimOutput.textContent = `🔄 Sesión reiniciada para ${phone}. Puedes empezar una nueva idea de proyecto.`;
          }
          loadWhatsAppSessions();
        }
      } catch (err) {
        alert(`Error al reiniciar: ${err.message}`);
      }
    });
  }

  if (waBtnRefreshSessions) {
    waBtnRefreshSessions.addEventListener('click', () => loadWhatsAppSessions());
  }

  // Deep linking: activate tab from URL query param (e.g. ?tab=tab-thoughts) or hash (e.g. #tab-thoughts)
  const urlParamTab = new URLSearchParams(window.location.search).get('tab');
  const hashTab = window.location.hash ? window.location.hash.replace('#', '') : null;
  const initialTarget = urlParamTab || hashTab;
  if (initialTarget && document.getElementById(initialTarget)) {
    switchTab(initialTarget);
  }

})();
