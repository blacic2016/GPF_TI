/* --------------------------------------------------------------------------
   DASHBOARD CLIENT-SIDE LOGIC - APP.JS
   Corporación GPF | Dashboard Analítico de Tickets TI_GPF
   -------------------------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
  let currentTemporalidad = 'actual';
  let selectedSpecificDate = '';
  let ticketsData = null;
  let currentSortColumn = 'total';
  let currentSortDir = 'desc';

  // DOM Elements
  const tabButtons = document.querySelectorAll('.tab-btn[data-temporalidad]');
  const groupFilter = document.getElementById('group-filter');
  const searchInput = document.getElementById('search-analyst');
  const btnRefresh = document.getElementById('btn-refresh');
  const updateTimestamp = document.getElementById('update-timestamp');
  const selectFechaCorte = document.getElementById('select-fecha-corte');
  const fechaCorteBadge = document.getElementById('fecha-corte-badge');

  const kpiTotal = document.getElementById('kpi-total-tickets');
  const kpiReportesCount = document.getElementById('kpi-reportes-count');
  const kpiCierrePct = document.getElementById('kpi-cierre-pct');
  const kpiCierreBar = document.getElementById('kpi-cierre-bar');
  const kpiPending = document.getElementById('kpi-pending');
  const kpiPendingStatus = document.getElementById('kpi-pending-status');
  const kpiQueued = document.getElementById('kpi-queued');

  const analystsTbody = document.getElementById('analysts-tbody');
  const analystCountLabel = document.getElementById('analyst-count-label');
  const groupListContainer = document.getElementById('group-list-container');
  const sortableHeaders = document.querySelectorAll('th.sortable');

  // Helper: Get color threshold class & badge text based on pending count
  function getPendingThresholdBadge(pendingCount) {
    if (pendingCount > 15) {
      return `<span class="badge-threshold badge-red">🔴 ${pendingCount} Crítico (>15)</span>`;
    } else if (pendingCount >= 10 && pendingCount <= 14) {
      return `<span class="badge-threshold badge-yellow">🟡 ${pendingCount} Medio (10-14)</span>`;
    } else {
      return `<span class="badge-threshold badge-green">🟢 ${pendingCount} Verde (0-9)</span>`;
    }
  }

  // Fetch data from backend Flask API
  async function fetchTicketsData() {
    analystsTbody.innerHTML = `
      <tr>
        <td colspan="7" class="loading-spinner">
          <div class="spinner"></div>
          Consultando datos desde base de datos TI_GPF...
        </td>
      </tr>
    `;

    try {
      let endpoint = `/api/tickets?temporalidad=${currentTemporalidad}`;
      if (selectedSpecificDate) {
        endpoint = `/api/tickets?fecha=${encodeURIComponent(selectedSpecificDate)}`;
      }

      const response = await fetch(endpoint);
      if (!response.ok) throw new Error('Error al consultar servidor');
      
      ticketsData = await response.json();
      updateTimestamp.textContent = new Date().toLocaleTimeString('es-EC');

      // Actualizar badge de corte
      if (fechaCorteBadge) {
        const corteLabel = ticketsData.fecha_activa_label || ticketsData.fecha_corte || '';
        const esHoy = ticketsData.es_corte_actual;
        fechaCorteBadge.textContent = `${corteLabel} ${esHoy ? '(Hoy)' : '(Último corte)'}`;
      }

      // Llenar selector de fechas disponibles
      populateFechasDropdown(ticketsData.fechas_disponibles, ticketsData.fecha_corte);

      populateGroupDropdown(ticketsData.grupos);
      renderDashboard();
    } catch (error) {
      console.error(error);
      analystsTbody.innerHTML = `
        <tr>
          <td colspan="7" style="color: var(--status-red); text-align: center; padding: 20px;">
            ❌ Error al cargar datos: ${error.message}
          </td>
        </tr>
      `;
    }
  }

  // Populate Date Selector
  function populateFechasDropdown(fechas, fechaCorte) {
    if (!selectFechaCorte || !fechas) return;
    const currentVal = selectFechaCorte.value;
    selectFechaCorte.innerHTML = '<option value="">(Corte Actual Automático)</option>';
    fechas.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f;
      opt.textContent = `Reporte del ${f}${f === fechaCorte ? ' (Activo)' : ''}`;
      selectFechaCorte.appendChild(opt);
    });
    selectFechaCorte.value = selectedSpecificDate || currentVal || '';
  }

  // Populate Group Filter Dropdown
  function populateGroupDropdown(grupos) {
    const currentVal = groupFilter.value;
    groupFilter.innerHTML = '<option value="todos">Todos los Grupos</option>';
    if (grupos) {
      grupos.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.assign_to_group;
        opt.textContent = `${g.assign_to_group} (${g.total} tickets)`;
        groupFilter.appendChild(opt);
      });
    }
    groupFilter.value = currentVal;
  }

  // Render KPIs & Tables
  function renderDashboard() {
    if (!ticketsData) return;

    const selectedGroup = groupFilter.value;
    const searchTerm = searchInput.value.toLowerCase().trim();

    // Filter analysts
    let filteredAnalysts = ticketsData.analistas || [];
    if (selectedGroup !== 'todos') {
      filteredAnalysts = filteredAnalysts.filter(a => a.assign_to_group === selectedGroup);
    }
    if (searchTerm) {
      filteredAnalysts = filteredAnalysts.filter(a => 
        (a.assign_to_individual || '').toLowerCase().includes(searchTerm) ||
        (a.assign_to_group || '').toLowerCase().includes(searchTerm)
      );
    }

    // Sort analysts dynamically by column
    filteredAnalysts.sort((a, b) => {
      let valA = a[currentSortColumn];
      let valB = b[currentSortColumn];

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
    const totalTickets = filteredAnalysts.reduce((sum, a) => sum + (a.total || 0), 0);
    const totalResolved = filteredAnalysts.reduce((sum, a) => sum + (a.resolved || 0), 0);
    const totalPending = filteredAnalysts.reduce((sum, a) => sum + (a.pending || 0), 0);
    const totalQueued = filteredAnalysts.reduce((sum, a) => sum + (a.queued || 0), 0);
    const cierrePct = totalTickets > 0 ? ((totalResolved / totalTickets) * 100).toFixed(1) : 0.0;

    // Update KPI Cards
    kpiTotal.textContent = totalTickets.toLocaleString();
    const corteTxt = (ticketsData && (ticketsData.fecha_activa_label || ticketsData.fecha_corte)) || currentTemporalidad.toUpperCase();
    kpiReportesCount.textContent = `Corte: ${corteTxt} | ${filteredAnalysts.length} especialistas`;
    kpiCierrePct.textContent = `${cierrePct}%`;
    kpiCierreBar.style.width = `${cierrePct}%`;
    kpiPending.textContent = totalPending.toLocaleString();
    kpiQueued.textContent = totalQueued.toLocaleString();

    // Overall Pending status evaluation
    if (totalPending > 15) {
      kpiPendingStatus.innerHTML = `<span style="color: var(--status-red); font-weight:700;">🔴 Nivel de Alerta Crítica (>15)</span>`;
    } else if (totalPending >= 10) {
      kpiPendingStatus.innerHTML = `<span style="color: var(--status-yellow); font-weight:700;">🟡 Nivel de Alerta Media (10-14)</span>`;
    } else {
      kpiPendingStatus.innerHTML = `<span style="color: var(--status-green); font-weight:700;">🟢 Estado Óptimo (0-9)</span>`;
    }

    analystCountLabel.textContent = `${filteredAnalysts.length} Especialistas`;

    // Render Analyst Table Rows
    if (filteredAnalysts.length === 0) {
      analystsTbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">
            No se encontraron especialistas para los filtros o búsqueda ingresada.
          </td>
        </tr>
      `;
    } else {
      analystsTbody.innerHTML = filteredAnalysts.map(a => {
        const thresholdBadge = getPendingThresholdBadge(a.pending || 0);
        const closurePct = a.tasa_cierre_pct || 0.0;
        const isCritical = (a.pending || 0) > 15;

        return `
          <tr class="${isCritical ? 'row-critical' : ''}">
            <td>
              <a href="/analista?nombre=${encodeURIComponent(a.assign_to_individual)}" target="_blank" class="analyst-name-link" title="Ver análisis de gráficos en nueva pestaña">
                ${a.assign_to_individual} ↗️
              </a>
            </td>
            <td>
              <div class="analyst-group">${a.assign_to_group}</div>
            </td>
            <td>${thresholdBadge}</td>
            <td><strong>${a.queued || 0}</strong></td>
            <td><strong style="color: var(--status-green);">${a.resolved || 0}</strong></td>
            <td><strong>${a.total || 0}</strong></td>
            <td>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-weight: 700; width: 45px;">${closurePct}%</span>
                <div class="progress-bar-bg" style="flex: 1; margin: 0; height: 5px;">
                  <div class="progress-bar-fill" style="width: ${closurePct}%;"></div>
                </div>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }

    // Render Group Breakdown List
    const grupos = ticketsData.grupos || [];
    groupListContainer.innerHTML = grupos.map(g => {
      return `
        <div class="group-item">
          <div class="group-header">
            <span class="group-name">${g.assign_to_group}</span>
            <span class="badge-threshold badge-green">${g.tasa_cierre_pct}% Resuelto</span>
          </div>
          <div class="group-stats">
            <div class="stat-box">
              <span class="stat-label">Analistas</span>
              <span class="stat-val">${g.total_analistas}</span>
            </div>
            <div class="stat-box">
              <span class="stat-label">Pendientes</span>
              <span class="stat-val" style="color: ${g.pending > 15 ? 'var(--status-red)' : (g.pending >= 10 ? 'var(--status-yellow)' : 'var(--status-green)')};">${g.pending}</span>
            </div>
            <div class="stat-box">
              <span class="stat-label">En Cola</span>
              <span class="stat-val">${g.queued}</span>
            </div>
            <div class="stat-box">
              <span class="stat-label">Total</span>
              <span class="stat-val">${g.total}</span>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // Event Listeners for Column Headers Sorting
  sortableHeaders.forEach(th => {
    th.addEventListener('click', () => {
      const col = th.getAttribute('data-sort');
      if (currentSortColumn === col) {
        currentSortDir = currentSortDir === 'asc' ? 'desc' : 'asc';
      } else {
        currentSortColumn = col;
        currentSortDir = 'desc';
      }
      renderDashboard();
    });
  });

  // Event Listeners for Temporalidad Tabs
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTemporalidad = btn.getAttribute('data-temporalidad');
      selectedSpecificDate = '';
      if (selectFechaCorte) selectFechaCorte.value = '';
      fetchTicketsData();
    });
  });

  // Event Listener for Specific Date Selector
  if (selectFechaCorte) {
    selectFechaCorte.addEventListener('change', (e) => {
      selectedSpecificDate = e.target.value;
      if (selectedSpecificDate) {
        tabButtons.forEach(b => b.classList.remove('active'));
      } else {
        tabButtons.forEach(b => {
          if (b.getAttribute('data-temporalidad') === 'actual') b.classList.add('active');
          else b.classList.remove('active');
        });
        currentTemporalidad = 'actual';
      }
      fetchTicketsData();
    });
  }

  // Event Listeners for Filters
  groupFilter.addEventListener('change', renderDashboard);
  searchInput.addEventListener('input', renderDashboard);
  btnRefresh.addEventListener('click', fetchTicketsData);

  // Initial Load
  fetchTicketsData();
});
