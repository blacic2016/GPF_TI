/* --------------------------------------------------------------------------
   WORKLOAD DASHBOARD CLIENT-SIDE LOGIC - CARGA_TRABAJO.JS
   Corporación GPF | Dashboard Analítico de Tickets TI_GPF
   -------------------------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
  let selectedArchivoId = '';
  let workloadData = null;
  let currentSortColumn = 'carga_activa';
  let currentSortDir = 'desc';

  // Chart configuration state
  let currentChartView = 'all'; // 'all', 'pending', 'active', 'resolved'
  let currentChartSort = 'desc'; // 'desc', 'asc', 'alpha'
  let currentChartLimit = '10';  // '10', 'all'
  let selectedAnalystTimeline = '__ALL__';
  let timelineChartType = 'bar'; // 'bar', 'line'

  // Chart instances
  let chartPendingBarInstance = null;
  let chartActiveBarInstance = null;
  let chartResolvedBarInstance = null;
  let chartTimelineInstance = null;
  let chartGroupWorkloadInstance = null;
  let chartWorkloadComparisonInstance = null;

  // DOM Elements
  const groupFilter = document.getElementById('group-filter');
  const searchInput = document.getElementById('search-analyst');
  const btnRefresh = document.getElementById('btn-refresh');
  const selectArchivoCorte = document.getElementById('select-archivo-corte');
  const btnUltimoArchivo = document.getElementById('btn-ultimo-archivo');
  const fechaCorteBadge = document.getElementById('fecha-corte-badge');
  const badgeEsUltimoHeader = document.getElementById('badge-es-ultimo-header');

  const badgeArchivoStatus = document.getElementById('badge-archivo-status');
  const badgeArchivoFechaRec = document.getElementById('badge-archivo-fecha-rec');
  const labelArchivoNombre = document.getElementById('label-archivo-nombre');
  const labelArchivoAsunto = document.getElementById('label-archivo-asunto');
  const statArchivoAnalistas = document.getElementById('stat-archivo-analistas');
  const statArchivoTickets = document.getElementById('stat-archivo-tickets');
  const statArchivoActiva = document.getElementById('stat-archivo-activa');

  const kpiCargaActiva = document.getElementById('kpi-carga-activa');
  const kpiPendingTotal = document.getElementById('kpi-pending-total');
  const kpiPendingStatus = document.getElementById('kpi-pending-status');
  const kpiQueuedTotal = document.getElementById('kpi-queued-total');
  const kpiResolvedTotal = document.getElementById('kpi-resolved-total');
  const kpiDesahogoPct = document.getElementById('kpi-desahogo-pct');

  const workloadTbody = document.getElementById('workload-tbody');
  const workloadCountLabel = document.getElementById('workload-count-label');
  const sortableHeaders = document.querySelectorAll('th.sortable');

  // Chart control DOM Elements
  const chartViewButtons = document.querySelectorAll('#chart-view-mode-tabs .tab-btn');
  const selectChartSort = document.getElementById('select-chart-sort');
  const selectChartLimit = document.getElementById('select-chart-limit');
  const tripleChartsGrid = document.getElementById('triple-charts-grid');
  const cardChartPending = document.getElementById('card-chart-pending');
  const cardChartActive = document.getElementById('card-chart-active');
  const cardChartResolved = document.getElementById('card-chart-resolved');

  // Timeline DOM Elements
  const selectAnalystTimeline = document.getElementById('select-analyst-timeline');
  const timelineTypeButtons = document.querySelectorAll('#timeline-chart-type-tabs .tab-btn');
  const timeKpiTendencia = document.getElementById('time-kpi-tendencia');
  const timeKpiTendenciaSub = document.getElementById('time-kpi-tendencia-sub');
  const timeKpiAvgPending = document.getElementById('time-kpi-avg-pending');
  const timeKpiPicoActive = document.getElementById('time-kpi-pico-active');
  const timeKpiPicoDate = document.getElementById('time-kpi-pico-date');
  const timeKpiEfectividad = document.getElementById('time-kpi-efectividad');

  // Diagnostic DOM Elements
  const diagTopPendingName = document.getElementById('diag-top-pending-name');
  const diagTopPendingDesc = document.getElementById('diag-top-pending-desc');
  const diagTopActiveName = document.getElementById('diag-top-active-name');
  const diagTopActiveDesc = document.getElementById('diag-top-active-desc');
  const diagTopResolvedName = document.getElementById('diag-top-resolved-name');
  const diagTopResolvedDesc = document.getElementById('diag-top-resolved-desc');
  const badgeDiagBalance = document.getElementById('badge-diag-balance');
  const diagBalanceMessage = document.getElementById('diag-balance-message');
  const btnExportCsv = document.getElementById('btn-export-csv');

  // Helper: Get Workload Badge HTML
  function getWorkloadBadgeHTML(nivelCarga, nivelTexto, cargaActiva) {
    if (nivelCarga === 'CRITICA') {
      return `<span class="badge-threshold badge-red">🔴 ${cargaActiva} Activos (Sobrecargado)</span>`;
    } else if (nivelCarga === 'MODERADA') {
      return `<span class="badge-threshold badge-yellow">🟡 ${cargaActiva} Activos (Moderado)</span>`;
    } else {
      return `<span class="badge-threshold badge-green">🟢 ${cargaActiva} Activos (Balanceado)</span>`;
    }
  }

  // Fetch Workload API Data
  async function fetchWorkloadData() {
    workloadTbody.innerHTML = `
      <tr>
        <td colspan="10" class="loading-spinner">
          <div class="spinner"></div>
          Consultando análisis de carga del archivo procesado desde TI_GPF...
        </td>
      </tr>
    `;

    try {
      let endpoint = `/api/carga_trabajo`;
      if (selectedArchivoId) {
        endpoint += `?archivo_id=${encodeURIComponent(selectedArchivoId)}`;
      }

      const response = await fetch(endpoint);
      if (!response.ok) throw new Error('Error al conectar con la base de datos');

      workloadData = await response.json();
      const aInfo = workloadData.archivo_info || {};

      // Actualizar badges en Header
      if (fechaCorteBadge) {
        fechaCorteBadge.textContent = `${aInfo.nombre_archivo || ''} (${aInfo.fecha_recepcion || workloadData.fecha_corte || ''})`;
      }
      if (badgeEsUltimoHeader) {
        if (aInfo.es_ultimo) {
          badgeEsUltimoHeader.className = 'badge-threshold badge-green';
          badgeEsUltimoHeader.textContent = '🟢 Último Archivo Cargado';
        } else {
          badgeEsUltimoHeader.className = 'badge-threshold badge-yellow';
          badgeEsUltimoHeader.textContent = '📁 Archivo Histórico';
        }
      }

      // Actualizar Banner de Archivo Cargado
      if (labelArchivoNombre) {
        labelArchivoNombre.textContent = aInfo.nombre_archivo || 'Reporte de Tickets';
      }
      if (labelArchivoAsunto) {
        labelArchivoAsunto.textContent = `Asunto: ${aInfo.asunto_correo || 'Reporte Diario tickets Analistas'}${aInfo.remitente_correo ? ' | Remitente: ' + aInfo.remitente_correo : ''}`;
      }
      if (badgeArchivoStatus) {
        if (aInfo.es_ultimo) {
          badgeArchivoStatus.className = 'badge-threshold badge-green';
          badgeArchivoStatus.textContent = '🟢 Último Archivo Cargado';
        } else {
          badgeArchivoStatus.className = 'badge-threshold badge-yellow';
          badgeArchivoStatus.textContent = '📁 Archivo Histórico Seleccionado';
        }
      }
      if (badgeArchivoFechaRec) {
        badgeArchivoFechaRec.textContent = `🕒 Recepción: ${aInfo.fecha_recepcion || ''}`;
      }
      if (statArchivoAnalistas) {
        statArchivoAnalistas.textContent = `${workloadData.analistas ? workloadData.analistas.length : 0}`;
      }
      if (statArchivoTickets) {
        statArchivoTickets.textContent = `${workloadData.resumen_carga ? workloadData.resumen_carga.total_tickets : 0}`;
      }
      if (statArchivoActiva) {
        statArchivoActiva.textContent = `${workloadData.resumen_carga ? workloadData.resumen_carga.carga_activa_total : 0}`;
      }

      const tableArchivoSub = document.getElementById('table-archivo-sub');
      if (tableArchivoSub) {
        tableArchivoSub.textContent = `${aInfo.nombre_archivo || 'Archivo'} (${aInfo.fecha_recepcion || ''})${aInfo.es_ultimo ? ' [Último Cargado]' : ''}`;
      }

      // Actualizar Banner Dinámico de Flujo Diferencial
      const dg = workloadData.diferencial_global || {};
      const kpiDifResueltos = document.getElementById('kpi-dif-resueltos');
      const kpiDifInflow = document.getElementById('kpi-dif-inflow');
      const kpiDifActiva = document.getElementById('kpi-dif-activa');
      const kpiDifActivaSub = document.getElementById('kpi-dif-activa-sub');
      const kpiDifAlertas = document.getElementById('kpi-dif-alertas');
      const kpiDifAlertasSub = document.getElementById('kpi-dif-alertas-sub');
      const labelComparativaCortes = document.getElementById('label-comparativa-cortes');
      const badgeBalanceEquipo = document.getElementById('badge-balance-equipo');

      if (labelComparativaCortes) {
        if (dg.tiene_anterior && dg.archivo_anterior) {
          labelComparativaCortes.innerHTML = `Comparando <strong>${aInfo.nombre_archivo || 'Corte Actual'}</strong> vs. corte anterior <strong>${dg.archivo_anterior.nombre_archivo}</strong> (${dg.archivo_anterior.fecha_recepcion})`;
        } else {
          labelComparativaCortes.textContent = 'Primer corte registrado en sistema (sin archivo anterior para diferencial)';
        }
      }

      if (kpiDifResueltos) {
        kpiDifResueltos.textContent = `+${dg.total_resueltos_periodo || 0}`;
      }
      if (kpiDifInflow) {
        kpiDifInflow.textContent = `+${dg.total_inflow_periodo || 0}`;
      }
      if (kpiDifActiva) {
        const bal = dg.balance_neto_activa || 0;
        kpiDifActiva.textContent = `${bal >= 0 ? '+' : ''}${bal}`;
        if (bal > 0) {
          kpiDifActiva.style.color = '#f59e0b';
          if (kpiDifActivaSub) kpiDifActivaSub.textContent = `Acumulación neta en equipo`;
        } else if (bal < 0) {
          kpiDifActiva.style.color = '#10b981';
          if (kpiDifActivaSub) kpiDifActivaSub.textContent = `Desahogo neto exitoso`;
        } else {
          kpiDifActiva.style.color = '#94a3b8';
          if (kpiDifActivaSub) kpiDifActivaSub.textContent = `Flujo neto balanceado (=)`;
        }
      }

      if (kpiDifAlertas) {
        const alertasCount = (dg.total_atascos || 0) + (dg.total_estancados || 0);
        kpiDifAlertas.textContent = `${alertasCount}`;
        if (kpiDifAlertasSub) {
          kpiDifAlertasSub.textContent = `${dg.total_atascos || 0} atascos, ${dg.total_estancados || 0} sin avance`;
        }
      }

      if (badgeBalanceEquipo) {
        if (!dg.tiene_anterior) {
          badgeBalanceEquipo.className = 'badge-threshold badge-blue';
          badgeBalanceEquipo.textContent = 'ℹ️ Registro Base Inicial';
        } else if (dg.balance_neto_activa <= 0) {
          badgeBalanceEquipo.className = 'badge-threshold badge-green';
          badgeBalanceEquipo.textContent = '🟢 Desahogo Efectivo del Equipo';
        } else {
          badgeBalanceEquipo.className = 'badge-threshold badge-yellow';
          badgeBalanceEquipo.textContent = '🟡 Carga Creciente (+tickets entrantes)';
        }
      }

      // Llenar selector de archivos procesados
      populateArchivosDropdown(workloadData.archivos_disponibles, aInfo.id);

      // Llenar selector de grupos
      populateGroupDropdown(workloadData.grupos);

      // Llenar selector de analistas para evolución en el tiempo
      populateAnalystTimelineDropdown(workloadData.analistas || []);

      // Renderizar Dashboard completo
      renderWorkloadDashboard();
      renderTimelineModule();
      renderDiagnosticModule();
    } catch (error) {
      console.error(error);
      workloadTbody.innerHTML = `
        <tr>
          <td colspan="10" style="color: var(--status-red); text-align: center; padding: 20px;">
            ❌ Error al cargar análisis de carga: ${error.message}
          </td>
        </tr>
      `;
    }
  }

  // Populate Processed Files Selector
  function populateArchivosDropdown(archivos, selectedId) {
    if (!selectArchivoCorte || !archivos) return;
    selectArchivoCorte.innerHTML = '';
    archivos.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.textContent = a.label || `${a.nombre_archivo} (${a.fecha_recepcion})`;
      if (String(a.id) === String(selectedId)) {
        opt.selected = true;
      }
      selectArchivoCorte.appendChild(opt);
    });

    if (btnUltimoArchivo) {
      const isLatest = archivos.length > 0 && String(archivos[0].id) === String(selectedId);
      if (isLatest) {
        btnUltimoArchivo.classList.add('active');
        btnUltimoArchivo.style.opacity = '1';
      } else {
        btnUltimoArchivo.classList.remove('active');
        btnUltimoArchivo.style.opacity = '0.75';
      }
    }
  }

  // Populate Group Filter Dropdown
  function populateGroupDropdown(grupos) {
    const currentVal = groupFilter.value;
    groupFilter.innerHTML = '<option value="todos">Todos los Grupos</option>';
    if (grupos) {
      grupos.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.assign_to_group;
        opt.textContent = `${g.assign_to_group} (${g.carga_activa} activos)`;
        groupFilter.appendChild(opt);
      });
    }
    groupFilter.value = currentVal;
  }

  // Populate Analyst Timeline Dropdown
  function populateAnalystTimelineDropdown(analysts) {
    if (!selectAnalystTimeline) return;
    const prevSelected = selectAnalystTimeline.value || selectedAnalystTimeline;
    selectAnalystTimeline.innerHTML = '<option value="__ALL__">🌐 Todo el Equipo (Consolidado Global)</option>';
    
    // Sort alphabetically for clean UI
    const sorted = [...analysts].sort((a, b) => a.assign_to_individual.localeCompare(b.assign_to_individual));
    sorted.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.assign_to_individual;
      opt.textContent = `${a.assign_to_individual} (${a.assign_to_group})`;
      selectAnalystTimeline.appendChild(opt);
    });

    if (prevSelected && Array.from(selectAnalystTimeline.options).some(o => o.value === prevSelected)) {
      selectAnalystTimeline.value = prevSelected;
      selectedAnalystTimeline = prevSelected;
    } else {
      selectAnalystTimeline.value = '__ALL__';
      selectedAnalystTimeline = '__ALL__';
    }
  }

  // Filter analysts based on group and search text
  function getFilteredAnalysts() {
    if (!workloadData) return [];
    const selectedGroup = groupFilter.value;
    const searchTerm = searchInput.value.toLowerCase().trim();

    let filtered = workloadData.analistas || [];
    if (selectedGroup !== 'todos') {
      filtered = filtered.filter(a => a.assign_to_group === selectedGroup);
    }
    if (searchTerm) {
      filtered = filtered.filter(a => 
        (a.assign_to_individual || '').toLowerCase().includes(searchTerm) ||
        (a.assign_to_group || '').toLowerCase().includes(searchTerm)
      );
    }
    return filtered;
  }

  // Helper to extract sort value dynamically
  function getAnalystSortVal(a, col) {
    const dif = a.diferencial_corte || {};
    if (col === 'u_pending') return a.ultimo_corte ? a.ultimo_corte.pending : a.pending;
    if (col === 'u_carga_activa') return a.ultimo_corte ? a.ultimo_corte.carga_activa : a.carga_activa;
    if (col === 'diff_resolved') return dif.diff_resolved || 0;
    if (col === 'diff_activa') return dif.diff_activa || 0;
    if (col === 'estado_flujo') return dif.diff_resolved || 0;
    if (col === 'w_total') return a.carga_semanal ? a.carga_semanal.total : 0;
    if (col === 'w_resolved') return a.carga_semanal ? a.carga_semanal.resolved : 0;
    if (col === 'w_tasa') return a.carga_semanal ? a.carga_semanal.tasa_cierre_pct : 0;
    if (col === 'indice_saturacion_pct') return a.indice_saturacion_pct || 0;
    if (col === 'nivel_saturacion') return a.indice_saturacion_pct || 0;
    return a[col];
  }

  // Render Workload Dashboard
  function renderWorkloadDashboard() {
    if (!workloadData) return;

    let filteredAnalysts = getFilteredAnalysts();

    // Sort analysts for table
    filteredAnalysts.sort((a, b) => {
      let valA = getAnalystSortVal(a, currentSortColumn);
      let valB = getAnalystSortVal(b, currentSortColumn);

      if (typeof valA === 'string') {
        valA = valA.toLowerCase();
        valB = (valB || '').toLowerCase();
        return currentSortDir === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }

      valA = Number(valA) || 0;
      valB = Number(valB) || 0;
      return currentSortDir === 'asc' ? valA - valB : valB - valA;
    });

    // Update Header Sort Icons
    sortableHeaders.forEach(th => {
      const col = th.getAttribute('data-sort');
      const iconSpan = th.querySelector('.sort-icon');
      if (iconSpan) {
        if (col === currentSortColumn) {
          iconSpan.textContent = currentSortDir === 'asc' ? '▲' : '▼';
          th.style.color = '#ffffff';
        } else {
          iconSpan.textContent = '⇅';
          th.style.color = 'var(--text-secondary)';
        }
      }
    });

    // Recalculate KPIs based on filtered analysts
    const cargaActivaTotal = filteredAnalysts.reduce((sum, a) => sum + a.carga_activa, 0);
    const pendingTotal = filteredAnalysts.reduce((sum, a) => sum + a.pending, 0);
    const queuedTotal = filteredAnalysts.reduce((sum, a) => sum + a.queued, 0);
    const resolvedTotal = filteredAnalysts.reduce((sum, a) => sum + a.resolved, 0);
    const totalTickets = filteredAnalysts.reduce((sum, a) => sum + a.total, 0);
    const desahogoPct = totalTickets > 0 ? ((resolvedTotal / totalTickets) * 100).toFixed(1) : 0.0;

    const sobrecargados = filteredAnalysts.filter(a => a.nivel_saturacion === 'SOBRECARGA_CRITICA' || a.nivel_carga === 'CRITICA').length;

    // Update KPI Cards
    kpiCargaActiva.textContent = cargaActivaTotal.toLocaleString();
    kpiPendingTotal.textContent = pendingTotal.toLocaleString();
    kpiQueuedTotal.textContent = queuedTotal.toLocaleString();
    kpiResolvedTotal.textContent = resolvedTotal.toLocaleString();
    kpiDesahogoPct.textContent = `${desahogoPct}% ratio de desahogo`;

    if (sobrecargados > 0) {
      kpiPendingStatus.innerHTML = `<span style="color: var(--status-red); font-weight: 700;">🔴 ${sobrecargados} Especialistas Sobrecargados</span>`;
    } else {
      kpiPendingStatus.innerHTML = `<span style="color: var(--status-green); font-weight: 700;">🟢 Distribución de Carga Saludable</span>`;
    }

    workloadCountLabel.textContent = `${filteredAnalysts.length} Especialistas Evaluados`;

    // Render Weekly Standby Banner
    renderWeeklyStandbyBanner();

    // Render Table
    if (filteredAnalysts.length === 0) {
      workloadTbody.innerHTML = `
        <tr>
          <td colspan="10" style="text-align: center; color: var(--text-muted); padding: 30px;">
            No se encontraron registros para los filtros ingresados.
          </td>
        </tr>
      `;
    } else {
      workloadTbody.innerHTML = filteredAnalysts.map(a => {
        const u = a.ultimo_corte || { pending: a.pending, queued: a.queued, resolved: a.resolved, carga_activa: a.carga_activa, total: a.total };
        const w = a.carga_semanal || { pending: 0, queued: 0, resolved: 0, carga_activa: 0, total: 0, tasa_cierre_pct: 0 };
        const dif = a.diferencial_corte || {};
        const isCrit = a.nivel_saturacion === 'SOBRECARGA_CRITICA' || a.nivel_carga === 'CRITICA' || dif.estado_flujo === 'CUELLO_BOTELLA';
        
        const standbyBadge = a.en_standby 
          ? `<span class="badge-standby-active" title="Especialista de guardia standby activa">🛡️ STANDBY</span>`
          : '';

        const scoreColor = a.nivel_saturacion_color || '#3b82f6';
        const scoreVal = a.indice_saturacion_pct || 0;

        // Indicador de delta en carga activa
        let deltaActivaBadge = '';
        if (dif.tiene_anterior) {
          if (dif.diff_activa > 0) {
            deltaActivaBadge = `<span class="badge-threshold badge-red" style="padding: 2px 6px; font-size: 11px; margin-left: 6px;" title="Aumentó +${dif.diff_activa} tickets activos vs. corte anterior">▲ +${dif.diff_activa}</span>`;
          } else if (dif.diff_activa < 0) {
            deltaActivaBadge = `<span class="badge-threshold badge-green" style="padding: 2px 6px; font-size: 11px; margin-left: 6px;" title="Redujo ${dif.diff_activa} tickets activos vs. corte anterior">▼ ${dif.diff_activa}</span>`;
          } else {
            deltaActivaBadge = `<span style="color: var(--text-muted); font-size: 11px; margin-left: 6px;" title="Misma carga activa que corte anterior">• 0</span>`;
          }
        }

        // Indicador de delta en pendientes
        let deltaPendingBadge = '';
        if (dif.tiene_anterior) {
          if (dif.diff_pending > 0) {
            deltaPendingBadge = `<span style="color: var(--status-red); font-size: 11px; margin-left: 4px; font-weight: 700;">(+${dif.diff_pending})</span>`;
          } else if (dif.diff_pending < 0) {
            deltaPendingBadge = `<span style="color: var(--status-green); font-size: 11px; margin-left: 4px; font-weight: 700;">(${dif.diff_pending})</span>`;
          }
        }

        // Tickets cerrados en periodo (Throughput)
        let cerradosHtml = '';
        if (dif.tiene_anterior) {
          if (dif.diff_resolved > 0) {
            cerradosHtml = `<span class="badge-threshold badge-green" style="font-weight: 800; font-size: 12px; padding: 3px 8px;">🚀 +${dif.diff_resolved} cerrados</span>`;
          } else {
            cerradosHtml = `<span style="color: var(--text-muted); font-size: 12px;">0 cerrados</span>`;
          }
        } else {
          cerradosHtml = `<span style="color: var(--text-muted); font-size: 12px;">-</span>`;
        }

        // Variación de flujo neto
        let flujoNetoHtml = '';
        if (dif.tiene_anterior) {
          if (dif.diff_activa > 0) {
            flujoNetoHtml = `<span style="color: var(--status-red); font-weight: 700; font-size: 12px;">▲ +${dif.diff_activa} acumula</span>`;
          } else if (dif.diff_activa < 0) {
            flujoNetoHtml = `<span style="color: var(--status-green); font-weight: 700; font-size: 12px;">▼ ${dif.diff_activa} desahogo</span>`;
          } else {
            flujoNetoHtml = `<span style="color: #94a3b8; font-weight: 600; font-size: 12px;">• Estable</span>`;
          }
        } else {
          flujoNetoHtml = `<span style="color: var(--text-muted); font-size: 12px;">-</span>`;
        }

        // Diagnóstico de flujo
        let estadoFlujoHtml = '';
        if (dif.tiene_anterior) {
          estadoFlujoHtml = `<span class="badge-threshold" style="border: 1px solid ${dif.estado_flujo_color || '#94a3b8'}; color: ${dif.estado_flujo_color || '#94a3b8'}; background: rgba(0,0,0,0.45); font-size: 11px; font-weight: 700; white-space: nowrap;" title="${dif.estado_flujo_desc || ''}">${dif.estado_flujo_label || 'Estable'}</span>`;
        } else {
          estadoFlujoHtml = `<span style="color: var(--text-muted); font-size: 11px;">Primer registro</span>`;
        }

        return `
          <tr class="${isCrit ? 'row-critical' : ''}">
            <td>
              <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <a href="/analista?nombre=${encodeURIComponent(a.assign_to_individual)}" target="_blank" class="analyst-name-link" title="Ver análisis individual">
                  ${a.assign_to_individual} ↗️
                </a>
                ${standbyBadge}
              </div>
            </td>
            <td><div class="analyst-group">${a.assign_to_group}</div></td>
            <td>
              <div style="display: flex; align-items: center;">
                <strong style="color: var(--status-yellow); font-size: 15px;">${u.carga_activa}</strong>
                ${deltaActivaBadge}
              </div>
            </td>
            <td>
              <div style="display: flex; align-items: center;">
                <strong style="color: ${u.pending > 15 ? 'var(--status-red)' : 'var(--text-primary)'}">${u.pending}</strong>
                ${deltaPendingBadge}
              </div>
            </td>
            <td>${cerradosHtml}</td>
            <td>${flujoNetoHtml}</td>
            <td>${estadoFlujoHtml}</td>
            <td><strong style="color: var(--status-green);">${w.resolved}</strong></td>
            <td>
              <div class="gauge-score-box">
                <div class="gauge-score-header">
                  <span class="gauge-score-val" style="color: ${scoreColor};">${scoreVal}%</span>
                  <span style="font-size: 10px; color: var(--text-muted);">${a.nivel_saturacion || ''}</span>
                </div>
                <div class="gauge-bar-track">
                  <div class="gauge-bar-fill" style="width: ${Math.min(100, Math.max(5, scoreVal))}%; background: ${scoreColor};"></div>
                </div>
              </div>
            </td>
            <td>
              <div class="obs-cell-wrapper" data-analyst="${encodeURIComponent(a.assign_to_individual)}">
                <div class="obs-input-row">
                  <textarea class="obs-textarea" placeholder="Escribir nota / observación..." rows="1">${a.observacion || ''}</textarea>
                  <button class="btn-save-obs" title="Guardar observación">💾</button>
                </div>
                <div class="obs-meta-info">
                  <span class="obs-timestamp">${a.fecha_observacion ? 'Actualizado: ' + a.fecha_observacion.substring(0, 16) : 'Sin notas'}</span>
                  <span class="obs-status"></span>
                </div>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }

    // Render Workload Comparison Chart (Último Dato vs Carga Semanal)
    renderWorkloadComparisonChart(filteredAnalysts);

    // Render Triple Bar Charts (un gráfico por cada estado)
    renderTripleBarCharts(filteredAnalysts, workloadData.promedios_equipo || {});

    // Render Group Workload Chart
    renderGroupWorkloadChart(workloadData.grupos || []);
  }

  // --------------------------------------------------------------------------
  // RENDER WEEKLY STANDBY BANNER
  // --------------------------------------------------------------------------
  function renderWeeklyStandbyBanner() {
    if (!workloadData) return;
    const infoSemanal = workloadData.info_semanal || {};
    const turnosStandby = infoSemanal.turnos_standby_activos || [];

    const bannerSemanaLabel = document.getElementById('banner-semana-label');
    const bannerStandbyBadge = document.getElementById('banner-standby-badge');
    const bannerStandbyAnalyst = document.getElementById('banner-standby-analyst');
    const bannerStandbyDetail = document.getElementById('banner-standby-detail');

    if (bannerSemanaLabel) {
      bannerSemanaLabel.textContent = `📅 ${infoSemanal.label || 'Semana en Curso'}`;
    }

    if (turnosStandby.length > 0) {
      const actual = turnosStandby[0];
      if (bannerStandbyBadge) {
        bannerStandbyBadge.className = 'badge-standby-active';
        bannerStandbyBadge.innerHTML = `🟢 Guardia Activa: ${actual.tipo_periodo || 'SEMANAL'}`;
      }
      if (bannerStandbyAnalyst) {
        bannerStandbyAnalyst.innerHTML = `🛡️ ${actual.assign_to_individual} <span style="font-size: 13px; font-weight: normal; color: #93c5fd; margin-left: 8px;">(${actual.assign_to_group || 'TI'})</span>`;
      }
      if (bannerStandbyDetail) {
        bannerStandbyDetail.innerHTML = `Período: <strong>${actual.fecha_inicio} al ${actual.fecha_fin}</strong> • Teléfono: <strong>${actual.telefono_contacto || 'No registrado'}</strong> ${actual.notas ? ' • ' + actual.notas : ''}`;
      }
    } else {
      if (bannerStandbyBadge) {
        bannerStandbyBadge.className = 'badge-threshold badge-blue';
        bannerStandbyBadge.textContent = '⚪ Sin Guardia Activa';
      }
      if (bannerStandbyAnalyst) {
        bannerStandbyAnalyst.textContent = 'No hay turno de standby asignado para esta semana';
      }
      if (bannerStandbyDetail) {
        bannerStandbyDetail.textContent = 'Haga clic en Administrar Standby para programar el turno de la semana.';
      }
    }
  }

  // Helper for shortening long names in X-axis (e.g. "Paredes Recalde,Marco Antonio" -> "Paredes, Marco")
  function formatAnalystLabel(fullName) {
    if (!fullName) return '';
    const parts = fullName.split(',');
    if (parts.length === 2) {
      const apellido = parts[0].trim().split(' ')[0];
      const nombre = parts[1].trim().split(' ')[0];
      return `${apellido}, ${nombre}`;
    }
    return fullName.length > 15 ? fullName.substring(0, 14) + '…' : fullName;
  }

  // --------------------------------------------------------------------------
  // RENDER WORKLOAD COMPARISON CHART (MEDICIÓN DINÁMICA DE FLUJO: Δ RESUELTOS VS Δ ACTIVA VS CARGA)
  // --------------------------------------------------------------------------
  function renderWorkloadComparisonChart(analysts) {
    const canvas = document.getElementById('chart-workload-comparison');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (chartWorkloadComparisonInstance) chartWorkloadComparisonInstance.destroy();

    const topAnalysts = analysts.slice(0, 12);
    const labels = topAnalysts.map(a => formatAnalystLabel(a.assign_to_individual));
    const fullNames = topAnalysts.map(a => a.assign_to_individual);

    const dataDiffResolved = topAnalysts.map(a => (a.diferencial_corte && a.diferencial_corte.diff_resolved !== undefined) ? a.diferencial_corte.diff_resolved : 0);
    const dataDiffActiva = topAnalysts.map(a => (a.diferencial_corte && a.diferencial_corte.diff_activa !== undefined) ? a.diferencial_corte.diff_activa : 0);
    const dataCargaActiva = topAnalysts.map(a => (a.ultimo_corte ? a.ultimo_corte.carga_activa : a.carga_activa) || 0);

    chartWorkloadComparisonInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Cerrados en Periodo (Δ Resueltos)',
            data: dataDiffResolved,
            backgroundColor: 'rgba(16, 185, 129, 0.85)',
            borderColor: '#10b981',
            borderWidth: 1.5,
            borderRadius: 4,
            maxBarThickness: 22
          },
          {
            label: 'Variación Carga Activa (Δ Activa)',
            data: dataDiffActiva,
            backgroundColor: dataDiffActiva.map(v => v > 0 ? 'rgba(239, 68, 68, 0.85)' : (v < 0 ? 'rgba(52, 211, 153, 0.85)' : 'rgba(245, 158, 11, 0.85)')),
            borderColor: dataDiffActiva.map(v => v > 0 ? '#ef4444' : (v < 0 ? '#10b981' : '#f59e0b')),
            borderWidth: 1.5,
            borderRadius: 4,
            maxBarThickness: 22
          },
          {
            label: 'Carga Activa Actual Total',
            data: dataCargaActiva,
            backgroundColor: 'rgba(59, 130, 246, 0.85)',
            borderColor: '#3b82f6',
            borderWidth: 1.5,
            borderRadius: 4,
            maxBarThickness: 22
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: { color: '#9ca3af', font: { family: 'Inter', size: 12 } }
          },
          tooltip: {
            backgroundColor: 'rgba(17, 24, 39, 0.95)',
            titleColor: '#ffffff',
            bodyColor: '#93c5fd',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              title: function(items) {
                const idx = items[0].dataIndex;
                const a = topAnalysts[idx];
                const diag = (a && a.diferencial_corte && a.diferencial_corte.estado_flujo_label) ? ` [${a.diferencial_corte.estado_flujo_label}]` : '';
                return (fullNames[idx] || items[0].label) + diag;
              },
              label: function(item) {
                const idx = item.dataIndex;
                const a = topAnalysts[idx];
                if (item.datasetIndex === 0) {
                  return ` 🟢 Cerrados en Periodo (Δ Res): +${item.raw} tickets`;
                } else if (item.datasetIndex === 1) {
                  const sign = item.raw > 0 ? '+' : '';
                  const desc = item.raw > 0 ? ' (Acumulación neta)' : (item.raw < 0 ? ' (Desahogo neto)' : ' (Sin cambio neto)');
                  return ` ⚖️ Variación Carga (Δ Act): ${sign}${item.raw} tickets${desc}`;
                } else {
                  const p = (a && a.ultimo_corte ? a.ultimo_corte.pending : (a ? a.pending : 0)) || 0;
                  const q = (a && a.ultimo_corte ? a.ultimo_corte.queued : (a ? a.queued : 0)) || 0;
                  return ` 🔵 Carga Activa Actual: ${item.raw} tickets (Pend: ${p}, Cola: ${q})`;
                }
              }
            }
          }
        },
        scales: {
          x: {
            ticks: {
              color: '#9ca3af',
              font: { family: 'Inter', size: 11 },
              maxRotation: 45,
              minRotation: 20
            },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          },
          y: {
            ticks: { color: '#9ca3af', font: { family: 'Inter' } },
            grid: { 
              color: (context) => context.tick.value === 0 ? 'rgba(255, 255, 255, 0.3)' : 'rgba(255, 255, 255, 0.05)',
              lineWidth: (context) => context.tick.value === 0 ? 1.5 : 1
            },
            suggestedMin: -2
          }
        }
      }
    });
  }

  // --------------------------------------------------------------------------
  // RENDER TRIPLE BAR CHARTS (UN GRÁFICO POR CADA ESTADO: PENDIENTES, ACTIVAS, RESUELTAS)
  // --------------------------------------------------------------------------
  function renderTripleBarCharts(analysts, benchmarks) {
    if (!tripleChartsGrid) return;

    // Apply view switcher classes
    if (currentChartView === 'all') {
      tripleChartsGrid.classList.remove('view-single');
      cardChartPending.style.display = 'flex';
      cardChartActive.style.display = 'flex';
      cardChartResolved.style.display = 'flex';
    } else {
      tripleChartsGrid.classList.add('view-single');
      cardChartPending.style.display = (currentChartView === 'pending') ? 'flex' : 'none';
      cardChartActive.style.display = (currentChartView === 'active') ? 'flex' : 'none';
      cardChartResolved.style.display = (currentChartView === 'resolved') ? 'flex' : 'none';
    }

    // Update benchmark badges
    const benchPendingLabel = document.getElementById('bench-pending-label');
    const benchActiveLabel = document.getElementById('bench-active-label');
    const benchResolvedLabel = document.getElementById('bench-resolved-label');
    if (benchPendingLabel) benchPendingLabel.textContent = `Media: ${benchmarks.avg_pending || 0}`;
    if (benchActiveLabel) benchActiveLabel.textContent = `Media: ${benchmarks.avg_carga_activa || 0}`;
    if (benchResolvedLabel) benchResolvedLabel.textContent = `Media: ${benchmarks.avg_resolved || 0}`;

    // Helper: sort and slice analysts for each specific metric
    function prepareDataset(metricKey) {
      let list = [...analysts];
      if (currentChartSort === 'desc') {
        list.sort((a, b) => b[metricKey] - a[metricKey]);
      } else if (currentChartSort === 'asc') {
        list.sort((a, b) => a[metricKey] - b[metricKey]);
      } else if (currentChartSort === 'alpha') {
        list.sort((a, b) => a.assign_to_individual.localeCompare(b.assign_to_individual));
      }

      if (currentChartLimit === '10') {
        list = list.slice(0, 10);
      }
      return list;
    }

    // --- 1. GRÁFICO PENDIENTES ---
    const pendingList = prepareDataset('pending');
    renderSingleStateBarChart({
      canvasId: 'chart-bar-pending',
      instanceVar: chartPendingBarInstance,
      setInstance: (inst) => { chartPendingBarInstance = inst; },
      labels: pendingList.map(a => formatAnalystLabel(a.assign_to_individual)),
      fullNames: pendingList.map(a => a.assign_to_individual),
      data: pendingList.map(a => a.pending),
      label: 'Tickets Pendientes',
      bgColor: 'rgba(239, 68, 68, 0.85)',
      borderColor: '#ef4444',
      avgVal: benchmarks.avg_pending || 0
    });

    // --- 2. GRÁFICO ACTIVAS (CARGA ACTIVA) ---
    const activeList = prepareDataset('carga_activa');
    renderSingleStateBarChart({
      canvasId: 'chart-bar-active',
      instanceVar: chartActiveBarInstance,
      setInstance: (inst) => { chartActiveBarInstance = inst; },
      labels: activeList.map(a => formatAnalystLabel(a.assign_to_individual)),
      fullNames: activeList.map(a => a.assign_to_individual),
      data: activeList.map(a => a.carga_activa),
      label: 'Carga Activa (P + Q)',
      bgColor: 'rgba(245, 158, 11, 0.85)',
      borderColor: '#f59e0b',
      avgVal: benchmarks.avg_carga_activa || 0
    });

    // --- 3. GRÁFICO RESUELTAS ---
    const resolvedList = prepareDataset('resolved');
    renderSingleStateBarChart({
      canvasId: 'chart-bar-resolved',
      instanceVar: chartResolvedBarInstance,
      setInstance: (inst) => { chartResolvedBarInstance = inst; },
      labels: resolvedList.map(a => formatAnalystLabel(a.assign_to_individual)),
      fullNames: resolvedList.map(a => a.assign_to_individual),
      data: resolvedList.map(a => a.resolved),
      label: 'Tickets Resueltos',
      bgColor: 'rgba(16, 185, 129, 0.85)',
      borderColor: '#10b981',
      avgVal: benchmarks.avg_resolved || 0
    });
  }

  // Generic renderer for single state bar charts
  function renderSingleStateBarChart({ canvasId, instanceVar, setInstance, labels, fullNames, data, label, bgColor, borderColor, avgVal }) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (instanceVar) instanceVar.destroy();

    const newInst = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: label,
            data: data,
            backgroundColor: bgColor,
            borderColor: borderColor,
            borderWidth: 1.5,
            borderRadius: 5,
            maxBarThickness: 34
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: 'rgba(17, 24, 39, 0.95)',
            titleColor: '#ffffff',
            bodyColor: '#93c5fd',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            padding: 10,
            callbacks: {
              title: function(items) {
                const idx = items[0].dataIndex;
                return fullNames[idx] || items[0].label;
              },
              label: function(item) {
                return ` ${item.dataset.label}: ${item.raw} tickets`;
              }
            }
          }
        },
        scales: {
          x: {
            ticks: {
              color: '#9ca3af',
              font: { family: 'Inter', size: 11 },
              maxRotation: 45,
              minRotation: 25
            },
            grid: { color: 'rgba(255, 255, 255, 0.04)' }
          },
          y: {
            ticks: { color: '#9ca3af', font: { family: 'Inter' } },
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            beginAtZero: true
          }
        }
      }
    });

    setInstance(newInst);
  }

  // --------------------------------------------------------------------------
  // RENDER ANÁLISIS EN EL TIEMPO POR ESPECIALISTA (EVOLUCIÓN TEMPORAL)
  // --------------------------------------------------------------------------
  function renderTimelineModule() {
    if (!workloadData) return;

    const timelineData = workloadData.evolucion_analistas || {};
    const consolidadoGlobal = workloadData.consolidado_temporal || [];

    let records = [];
    let isConsolidated = (selectedAnalystTimeline === '__ALL__');

    if (isConsolidated) {
      records = consolidadoGlobal;
    } else {
      records = timelineData[selectedAnalystTimeline] || [];
    }

    // Sort chronologically by date
    records = [...records].sort((a, b) => a.fecha.localeCompare(b.fecha));

    // Update KPI summary for the selected analyst in time
    if (records.length === 0) {
      timeKpiTendencia.innerHTML = '<span class="badge-threshold badge-blue">Sin Datos</span>';
      timeKpiAvgPending.textContent = '0.0';
      timeKpiPicoActive.textContent = '0';
      timeKpiPicoDate.textContent = 'Fecha: -';
      timeKpiEfectividad.textContent = '0.0%';
    } else {
      const totalPending = records.reduce((s, r) => s + r.pending, 0);
      const totalActive = records.reduce((s, r) => s + r.carga_activa, 0);
      const totalResolved = records.reduce((s, r) => s + r.resolved, 0);
      const totalTickets = records.reduce((s, r) => s + r.total, 0);

      const avgPending = (totalPending / records.length).toFixed(1);
      const efectividad = totalTickets > 0 ? ((totalResolved / totalTickets) * 100).toFixed(1) : 0.0;

      // Find peak active load
      let pico = records[0];
      for (let r of records) {
        if (r.carga_activa > pico.carga_activa) pico = r;
      }

      // Compute trend between the last two cuts
      let trendHTML = '<span class="badge-threshold badge-blue">⚖️ Estable</span>';
      let trendSub = 'Variación vs. corte anterior';
      if (records.length >= 2) {
        const last = records[records.length - 1];
        const prev = records[records.length - 2];
        const diffAct = last.carga_activa - prev.carga_activa;
        const diffPend = last.pending - prev.pending;

        if (diffAct > 0) {
          trendHTML = `<span class="badge-threshold badge-red">🔺 Carga en Aumento (+${diffAct})</span>`;
          trendSub = `Pendientes: ${diffPend >= 0 ? '+' : ''}${diffPend} tickets`;
        } else if (diffAct < 0) {
          trendHTML = `<span class="badge-threshold badge-green">🔻 En Desahogo (${diffAct})</span>`;
          trendSub = `Pendientes: ${diffPend >= 0 ? '+' : ''}${diffPend} tickets`;
        } else {
          trendHTML = `<span class="badge-threshold badge-blue">⚖️ Carga Estable (0)</span>`;
          trendSub = `Mismo volumen que corte ${prev.fecha}`;
        }
      }

      timeKpiTendencia.innerHTML = trendHTML;
      timeKpiTendenciaSub.textContent = trendSub;
      timeKpiAvgPending.textContent = avgPending;
      timeKpiPicoActive.textContent = pico.carga_activa;
      timeKpiPicoDate.textContent = `Fecha: ${pico.fecha}`;
      timeKpiEfectividad.textContent = `${efectividad}%`;
    }

    // Render Timeline Chart
    const canvas = document.getElementById('chart-analyst-timeline');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (chartTimelineInstance) chartTimelineInstance.destroy();

    const labels = records.map(r => r.fecha);
    const dataPending = records.map(r => r.pending);
    const dataActive = records.map(r => r.carga_activa);
    const dataResolved = records.map(r => r.resolved);

    if (timelineChartType === 'line') {
      chartTimelineInstance = new Chart(ctx, {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Pendientes (Pending)',
              data: dataPending,
              borderColor: '#ef4444',
              backgroundColor: 'rgba(239, 68, 68, 0.12)',
              tension: 0.35,
              fill: true,
              pointRadius: 4,
              pointHoverRadius: 6,
              borderWidth: 2.5
            },
            {
              label: 'Carga Activa (P + Q)',
              data: dataActive,
              borderColor: '#f59e0b',
              backgroundColor: 'rgba(245, 158, 11, 0.12)',
              tension: 0.35,
              fill: true,
              pointRadius: 4,
              pointHoverRadius: 6,
              borderWidth: 2.5
            },
            {
              label: 'Resueltos (Resolved)',
              data: dataResolved,
              borderColor: '#10b981',
              backgroundColor: 'rgba(16, 185, 129, 0.12)',
              tension: 0.35,
              fill: true,
              pointRadius: 4,
              pointHoverRadius: 6,
              borderWidth: 2.5
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: {
              position: 'top',
              labels: { color: '#9ca3af', font: { family: 'Inter', size: 12 } }
            },
            tooltip: {
              backgroundColor: 'rgba(17, 24, 39, 0.95)',
              titleColor: '#ffffff',
              borderColor: 'rgba(255, 255, 255, 0.1)',
              borderWidth: 1
            }
          },
          scales: {
            x: {
              ticks: { color: '#9ca3af', font: { family: 'Inter', size: 11 } },
              grid: { color: 'rgba(255, 255, 255, 0.05)' }
            },
            y: {
              ticks: { color: '#9ca3af', font: { family: 'Inter' } },
              grid: { color: 'rgba(255, 255, 255, 0.05)' },
              beginAtZero: true
            }
          }
        }
      });
    } else {
      // Grouped Bar Chart by Date
      chartTimelineInstance = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Pendientes',
              data: dataPending,
              backgroundColor: '#ef4444',
              borderRadius: 4
            },
            {
              label: 'Carga Activa',
              data: dataActive,
              backgroundColor: '#f59e0b',
              borderRadius: 4
            },
            {
              label: 'Resueltos',
              data: dataResolved,
              backgroundColor: '#10b981',
              borderRadius: 4
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'top',
              labels: { color: '#9ca3af', font: { family: 'Inter', size: 12 } }
            }
          },
          scales: {
            x: {
              ticks: { color: '#9ca3af', font: { family: 'Inter', size: 11 } },
              grid: { color: 'rgba(255, 255, 255, 0.05)' }
            },
            y: {
              ticks: { color: '#9ca3af', font: { family: 'Inter' } },
              grid: { color: 'rgba(255, 255, 255, 0.05)' },
              beginAtZero: true
            }
          }
        }
      });
    }
  }

  // --------------------------------------------------------------------------
  // RENDER DIAGNOSTIC MODULE & RECOMMENDATIONS
  // --------------------------------------------------------------------------
  function renderDiagnosticModule() {
    if (!workloadData) return;
    const diag = workloadData.diagnostico || {};
    const promedios = workloadData.promedios_equipo || {};

    if (diagTopPendingName && diag.top_pending) {
      diagTopPendingName.textContent = diag.top_pending.assign_to_individual;
      diagTopPendingDesc.textContent = `${diag.top_pending.pending} pendientes • Grupo: ${diag.top_pending.assign_to_group} • Carga Activa: ${diag.top_pending.carga_activa}`;
    }

    if (diagTopActiveName && diag.top_active) {
      diagTopActiveName.textContent = diag.top_active.assign_to_individual;
      diagTopActiveDesc.textContent = `${diag.top_active.carga_activa} carga viva (${diag.top_active.pending} pendientes + ${diag.top_active.queued} en cola)`;
    }

    if (diagTopResolvedName && diag.top_resolved) {
      diagTopResolvedName.textContent = diag.top_resolved.assign_to_individual;
      diagTopResolvedDesc.textContent = `${diag.top_resolved.resolved} resueltos (${diag.top_resolved.tasa_desahogo_pct}% ratio de efectividad)`;
    }

    if (badgeDiagBalance) {
      if (diag.carga_concentrada) {
        badgeDiagBalance.className = 'badge-threshold badge-yellow';
        badgeDiagBalance.innerHTML = `⚠️ Concentración Alta: ${diag.pct_concentracion_top2}% en 2 especialistas`;
      } else {
        badgeDiagBalance.className = 'badge-threshold badge-green';
        badgeDiagBalance.innerHTML = `🟢 Distribución de Carga Equilibrada`;
      }
    }

    if (diagBalanceMessage) {
      diagBalanceMessage.innerHTML = `
        <strong>Promedio del Equipo:</strong> ${promedios.avg_pending || 0} pendientes, ${promedios.avg_carga_activa || 0} carga activa y ${promedios.avg_resolved || 0} resueltos por analista.
      `;
    }
  }

  // --------------------------------------------------------------------------
  // RENDER GROUP WORKLOAD CHART
  // --------------------------------------------------------------------------
  function renderGroupWorkloadChart(grupos) {
    const canvas = document.getElementById('chart-group-workload');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (chartGroupWorkloadInstance) chartGroupWorkloadInstance.destroy();

    const labels = grupos.map(g => g.assign_to_group);
    const dataActive = grupos.map(g => g.carga_activa);

    chartGroupWorkloadInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          label: 'Carga Activa',
          data: dataActive,
          backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#8b5cf6'],
          borderColor: '#111827',
          borderWidth: 3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#9ca3af', font: { family: 'Inter', size: 12 } }
          },
          tooltip: {
            callbacks: {
              label: function(item) {
                return ` ${item.label}: ${item.raw} casos activos`;
              }
            }
          }
        }
      }
    });
  }

  // --------------------------------------------------------------------------
  // EXPORT TO CSV
  // --------------------------------------------------------------------------
  function exportWorkloadToCSV() {
    const analysts = getFilteredAnalysts();
    if (!analysts || analysts.length === 0) {
      alert('No hay datos disponibles para exportar.');
      return;
    }

    const headers = [
      'Especialista / Analista',
      'Grupo',
      'En Standby',
      'Último Dato: Pendientes',
      'Último Dato: Carga Activa (P+Q)',
      'Carga Semanal Total',
      'Resueltos Semanales',
      '% Desahogo Semanal',
      'Medición Gráfica Saturación %',
      'Nivel de Carga',
      'Observaciones Supervisor'
    ];

    const rows = analysts.map(a => {
      const u = a.ultimo_corte || { pending: a.pending, carga_activa: a.carga_activa };
      const w = a.carga_semanal || { total: 0, resolved: 0, tasa_cierre_pct: 0 };
      return [
        `"${a.assign_to_individual.replace(/"/g, '""')}"`,
        `"${a.assign_to_group.replace(/"/g, '""')}"`,
        a.en_standby ? 'SÍ' : 'NO',
        u.pending,
        u.carga_activa,
        w.total,
        w.resolved,
        `${w.tasa_cierre_pct}%`,
        `${a.indice_saturacion_pct || 0}%`,
        `"${a.nivel_saturacion_label || a.nivel_texto || ''}"`,
        `"${(a.observacion || '').replace(/"/g, '""')}"`
      ];
    });

    const csvContent = '\uFEFF' + [headers.join(','), ...rows.map(r => r.join(','))].join('\r\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const fechaStr = workloadData ? (workloadData.fecha_activa_label || 'Reporte') : 'Reporte';
    link.setAttribute('href', url);
    link.setAttribute('download', `Matriz_Carga_Trabajo_TIGPF_${fechaStr}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  // --------------------------------------------------------------------------
  // EVENT LISTENERS
  // --------------------------------------------------------------------------

  // Chart View Mode Tabs (All, Pending, Active, Resolved)
  chartViewButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      chartViewButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentChartView = btn.getAttribute('data-chart-view');
      renderTripleBarCharts(getFilteredAnalysts(), workloadData ? (workloadData.promedios_equipo || {}) : {});
    });
  });

  // Chart Sorting & Limit Selectors
  if (selectChartSort) {
    selectChartSort.addEventListener('change', (e) => {
      currentChartSort = e.target.value;
      renderTripleBarCharts(getFilteredAnalysts(), workloadData ? (workloadData.promedios_equipo || {}) : {});
    });
  }

  if (selectChartLimit) {
    selectChartLimit.addEventListener('change', (e) => {
      currentChartLimit = e.target.value;
      renderTripleBarCharts(getFilteredAnalysts(), workloadData ? (workloadData.promedios_equipo || {}) : {});
    });
  }

  // Analyst Timeline Selector
  if (selectAnalystTimeline) {
    selectAnalystTimeline.addEventListener('change', (e) => {
      selectedAnalystTimeline = e.target.value;
      renderTimelineModule();
    });
  }

  // Timeline Chart Type Tabs (Bar vs Line)
  timelineTypeButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      timelineTypeButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      timelineChartType = btn.getAttribute('data-type');
      renderTimelineModule();
    });
  });

  // Export to CSV button
  if (btnExportCsv) {
    btnExportCsv.addEventListener('click', exportWorkloadToCSV);
  }

  // Column Sorting in Table
  sortableHeaders.forEach(th => {
    th.addEventListener('click', () => {
      const col = th.getAttribute('data-sort');
      if (currentSortColumn === col) {
        currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
      } else {
        currentSortColumn = col;
        currentSortDir = 'desc';
      }
      renderWorkloadDashboard();
    });
  });

  // Selector de Archivo Cargado
  if (selectArchivoCorte) {
    selectArchivoCorte.addEventListener('change', (e) => {
      selectedArchivoId = e.target.value;
      fetchWorkloadData();
    });
  }

  // Botón Solo Último Archivo
  if (btnUltimoArchivo) {
    btnUltimoArchivo.addEventListener('click', () => {
      selectedArchivoId = '';
      fetchWorkloadData();
    });
  }

  // Filter & Search Events
  groupFilter.addEventListener('change', () => {
    renderWorkloadDashboard();
  });
  searchInput.addEventListener('input', () => {
    renderWorkloadDashboard();
  });
  if (btnRefresh) {
    btnRefresh.addEventListener('click', fetchWorkloadData);
  }

  // Save Observation Event Delegation
  if (workloadTbody) {
    workloadTbody.addEventListener('click', async (e) => {
      const btn = e.target.closest('.btn-save-obs');
      if (!btn) return;

      const wrapper = btn.closest('.obs-cell-wrapper');
      if (!wrapper) return;

      const analyst = decodeURIComponent(wrapper.getAttribute('data-analyst'));
      const textarea = wrapper.querySelector('.obs-textarea');
      const timestampSpan = wrapper.querySelector('.obs-timestamp');
      const observacionText = textarea ? textarea.value.trim() : '';

      btn.disabled = true;
      btn.textContent = '⏳';

      try {
        const response = await fetch('/api/observaciones_carga', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            assign_to_individual: analyst,
            observacion: observacionText,
            usuario_registro: 'Supervisor TI'
          })
        });

        const resJson = await response.json();
        if (response.ok && resJson.status === 'ok') {
          btn.textContent = '✓';
          btn.classList.add('saved');
          const reg = resJson.registro;
          if (reg && reg.fecha_actualizacion && timestampSpan) {
            timestampSpan.textContent = `Actualizado: ${reg.fecha_actualizacion.substring(0, 16)}`;
          }
          if (workloadData && workloadData.analistas) {
            const target = workloadData.analistas.find(a => a.assign_to_individual === analyst);
            if (target) {
              target.observacion = observacionText;
              target.fecha_observacion = reg ? reg.fecha_actualizacion : '';
            }
          }
          setTimeout(() => {
            btn.textContent = '💾';
            btn.classList.remove('saved');
            btn.disabled = false;
          }, 2000);
        } else {
          alert('Error al guardar observación: ' + (resJson.error || 'Error desconocido'));
          btn.textContent = '💾';
          btn.disabled = false;
        }
      } catch (err) {
        console.error('Error al guardar observación:', err);
        alert('Error de conexión al guardar la observación.');
        btn.textContent = '💾';
        btn.disabled = false;
      }
    });
  }

  // Initial Load
  fetchWorkloadData();
});
