/* --------------------------------------------------------------------------
   INDIVIDUAL ANALYST DASHBOARD LOGIC - ANALISTA.JS
   Corporación GPF | Dashboard Analítico de Tickets TI_GPF
   -------------------------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
  let currentTemporalidad = 'todos';
  let analystData = null;
  let chartTimelineInstance = null;
  let chartDistributionInstance = null;

  // DOM Elements
  const analystTitle = document.getElementById('analyst-page-title');
  const analystGroup = document.getElementById('analyst-page-group');
  const alertBadge = document.getElementById('analyst-alert-badge');
  const tabButtons = document.querySelectorAll('.tab-btn[data-temporalidad]');

  const kpiTotal = document.getElementById('kpi-ind-total');
  const kpiCierre = document.getElementById('kpi-ind-cierre');
  const kpiCierreBar = document.getElementById('kpi-ind-cierre-bar');
  const kpiPending = document.getElementById('kpi-ind-pending');
  const kpiPendingAlert = document.getElementById('kpi-ind-pending-alert');
  const kpiResolved = document.getElementById('kpi-ind-resolved');

  const historyTbody = document.getElementById('history-tbody');
  const recordsCountLabel = document.getElementById('records-count-label');

  if (!ANALYST_NAME) {
    analystTitle.textContent = "Error: Nombre de especialista no provisto";
    return;
  }

  analystTitle.textContent = ANALYST_NAME;

  // Helper: Get color threshold badge for pending count
  function getThresholdBadgeHTML(pendingCount) {
    if (pendingCount > 15) {
      return `<span class="badge-threshold badge-red">🔴 ${pendingCount} Crítico (>15)</span>`;
    } else if (pendingCount >= 10 && pendingCount <= 14) {
      return `<span class="badge-threshold badge-yellow">🟡 ${pendingCount} Medio (10-14)</span>`;
    } else {
      return `<span class="badge-threshold badge-green">🟢 ${pendingCount} Verde (0-9)</span>`;
    }
  }

  // Fetch API data for specific analyst
  async function fetchAnalystData() {
    historyTbody.innerHTML = `
      <tr>
        <td colspan="7" class="loading-spinner">
          <div class="spinner"></div>
          Consultando histórico para ${ANALYST_NAME}...
        </td>
      </tr>
    `;

    try {
      const url = `/api/analista/${encodeURIComponent(ANALYST_NAME)}?temporalidad=${currentTemporalidad}`;
      const response = await fetch(url);
      if (!response.ok) throw new Error('Error al conectar con la base de datos');

      analystData = await response.json();
      renderAnalystDashboard();
    } catch (error) {
      console.error(error);
      historyTbody.innerHTML = `
        <tr>
          <td colspan="7" style="color: var(--status-red); text-align: center; padding: 20px;">
            ❌ Error al cargar datos: ${error.message}
          </td>
        </tr>
      `;
    }
  }

  // Render KPIs, Charts, and History Table
  function renderAnalystDashboard() {
    if (!analystData) return;

    const totales = analystData.totales || {};
    const historico = analystData.historico || [];

    analystGroup.textContent = `Grupo: ${analystData.grupo || 'Desconocido'}`;
    alertBadge.innerHTML = getThresholdBadgeHTML(totales.pending || 0);

    // Update KPI Cards
    kpiTotal.textContent = (totales.total || 0).toLocaleString();
    kpiCierre.textContent = `${totales.tasa_cierre_pct || 0.0}%`;
    kpiCierreBar.style.width = `${totales.tasa_cierre_pct || 0.0}%`;
    kpiPending.textContent = (totales.pending || 0).toLocaleString();
    kpiResolved.textContent = (totales.resolved || 0).toLocaleString();

    if (totales.pending > 15) {
      kpiPendingAlert.innerHTML = `<span style="color: #ff4d4d; font-weight:700;">🔴 Nivel Crítico Vibrando (>15)</span>`;
    } else if (totales.pending >= 10) {
      kpiPendingAlert.innerHTML = `<span style="color: var(--status-yellow); font-weight:700;">🟡 Nivel Medio (10-14)</span>`;
    } else {
      kpiPendingAlert.innerHTML = `<span style="color: var(--status-green); font-weight:700;">🟢 Estado Óptimo (0-9)</span>`;
    }

    recordsCountLabel.textContent = `${historico.length} Reportes Registrados`;

    // Render History Table
    if (historico.length === 0) {
      historyTbody.innerHTML = `
        <tr>
          <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">
            No hay registros de reportes para los filtros seleccionados.
          </td>
        </tr>
      `;
    } else {
      historyTbody.innerHTML = historico.map(r => {
        const badge = getThresholdBadgeHTML(r.pending);
        const cierre = r.total > 0 ? ((r.resolved / r.total) * 100).toFixed(1) : 0.0;
        const isCrit = r.pending > 15;

        return `
          <tr class="${isCrit ? 'row-critical' : ''}">
            <td><strong>${r.fecha_recepcion_str || r.fecha_corta || r.fecha_recepcion || 'Sin Fecha'}</strong></td>
            <td><code>${r.id_unico}</code></td>
            <td>${badge}</td>
            <td><strong>${r.queued}</strong></td>
            <td><strong style="color: var(--status-green);">${r.resolved}</strong></td>
            <td><strong>${r.total}</strong></td>
            <td>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-weight:700; width: 45px;">${cierre}%</span>
                <div class="progress-bar-bg" style="flex: 1; margin: 0; height: 5px;">
                  <div class="progress-bar-fill" style="width: ${cierre}%;"></div>
                </div>
              </div>
            </td>
          </tr>
        `;
      }).join('');
    }

    // Render Chart 1: Timeline Line Chart
    renderTimelineChart(historico);

    // Render Chart 2: Distribution Doughnut Chart
    renderDistributionChart(totales);
  }

  // Render Chart.js Timeline Chart
  function renderTimelineChart(historico) {
    const ctx = document.getElementById('chart-timeline').getContext('2d');
    if (chartTimelineInstance) chartTimelineInstance.destroy();

    const labels = historico.map(r => r.fecha_corta || r.fecha_recepcion_str || r.fecha_recepcion || 'Reporte');
    const dataResolved = historico.map(r => r.resolved);
    const dataPending = historico.map(r => r.pending);
    const dataQueued = historico.map(r => r.queued);

    chartTimelineInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Resueltos (Resolved)',
            data: dataResolved,
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.15)',
            fill: true,
            tension: 0.3,
            borderWidth: 2
          },
          {
            label: 'Pendientes (Pending)',
            data: dataPending,
            borderColor: '#ef4444',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            fill: true,
            tension: 0.3,
            borderWidth: 2
          },
          {
            label: 'En Cola (Queued)',
            data: dataQueued,
            borderColor: '#f59e0b',
            backgroundColor: 'rgba(245, 158, 11, 0.15)',
            fill: true,
            tension: 0.3,
            borderWidth: 2
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: '#9ca3af', font: { family: 'Inter', size: 12 } }
          }
        },
        scales: {
          x: {
            ticks: { color: '#9ca3af', font: { family: 'Inter' } },
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

  // Render Chart.js Distribution Doughnut Chart
  function renderDistributionChart(totales) {
    const ctx = document.getElementById('chart-distribution').getContext('2d');
    if (chartDistributionInstance) chartDistributionInstance.destroy();

    chartDistributionInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Resueltos (Resolved)', 'Pendientes (Pending)', 'En Cola (Queued)'],
        datasets: [{
          data: [totales.resolved || 0, totales.pending || 0, totales.queued || 0],
          backgroundColor: ['#10b981', '#ef4444', '#f59e0b'],
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
          }
        }
      }
    });
  }

  // Event Listeners for Temporalidad Tabs
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      tabButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTemporalidad = btn.getAttribute('data-temporalidad');
      fetchAnalystData();
    });
  });

  // Initial Load
  fetchAnalystData();
});
