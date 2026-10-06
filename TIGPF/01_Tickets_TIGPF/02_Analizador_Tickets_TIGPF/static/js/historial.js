/* --------------------------------------------------------------------------
   HISTORIAL DE EJECUCIONES & CONTROL DE INGESTA - HISTORIAL.JS
   Corporación GPF | Monitoreo Analítico de Tickets TI_GPF
   -------------------------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
  let ejecucionesData = [];
  let schedulerData = null;
  let pollingInterval = null;

  // DOM Elements - KPIs
  const kpiSchedulerStatus = document.getElementById('kpi-scheduler-status');
  const kpiSchedulerNext = document.getElementById('kpi-scheduler-next');
  const kpiLastRunDate = document.getElementById('kpi-last-run-date');
  const kpiLastRunStatus = document.getElementById('kpi-last-run-status');
  const kpiTotalRuns = document.getElementById('kpi-total-runs');
  const kpiRunsBreakdown = document.getElementById('kpi-runs-breakdown');
  const kpiAvgDuration = document.getElementById('kpi-avg-duration');
  const executionCountLabel = document.getElementById('execution-count-label');

  // DOM Elements - Actions & Table
  const btnSyncManual = document.getElementById('btn-sync-manual');
  const syncIcon = document.getElementById('sync-icon');
  const syncText = document.getElementById('sync-text');
  const btnRefreshHistory = document.getElementById('btn-refresh-history');
  const filterEstado = document.getElementById('filter-estado');
  const historialTbody = document.getElementById('historial-tbody');

  // DOM Elements - Modal
  const logModal = document.getElementById('log-modal');
  const modalTitle = document.getElementById('modal-title');
  const modalSubtitle = document.getElementById('modal-subtitle');
  const modalLogContent = document.getElementById('modal-log-content');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalCloseFooter = document.getElementById('modal-close-footer');
  const btnCopyLog = document.getElementById('btn-copy-log');

  // Helper: Status badge generator
  function getEstadoBadge(estado) {
    if (estado === 'EXITO') {
      return '<span class="badge-threshold badge-green">🟢 Éxito</span>';
    } else if (estado === 'ERROR') {
      return '<span class="badge-threshold badge-red">🔴 Error</span>';
    } else if (estado === 'EN_PROCESO') {
      return '<span class="badge-threshold badge-yellow">🟡 En Proceso</span>';
    } else {
      return `<span class="badge-threshold" style="background: rgba(255,255,255,0.1);">${estado}</span>`;
    }
  }

  // Helper: Tipo de ejecución badge generator
  function getTipoBadge(tipo) {
    if (tipo === 'AUTOMATICA_HORARIA') {
      return '<span style="color: #93c5fd; font-weight: 600;">⏰ Automática (Cada hora)</span>';
    } else if (tipo === 'MANUAL_WEB') {
      return '<span style="color: #c084fc; font-weight: 600;">👤 Manual (Web)</span>';
    }
    return `<span>${tipo}</span>`;
  }

  // Fetch Scheduler Status & KPIs
  async function fetchSchedulerStatus() {
    try {
      const res = await fetch('/api/estado_scheduler');
      if (!res.ok) return;
      schedulerData = await res.json();

      // Próxima ejecución
      if (schedulerData.proxima_ejecucion) {
        kpiSchedulerNext.textContent = `Próxima: ${schedulerData.proxima_ejecucion}`;
      } else {
        kpiSchedulerNext.textContent = 'En espera de programación';
      }

      // Última ejecución
      if (schedulerData.ultima_ejecucion) {
        const ult = schedulerData.ultima_ejecucion;
        kpiLastRunDate.textContent = ult.fecha_inicio || 'Sin registros';
        const dur = ult.duracion_segundos ? `${ult.duracion_segundos}s` : '-';
        kpiLastRunStatus.innerHTML = `Estado: ${getEstadoBadge(ult.estado)} | ${dur}`;
      } else {
        kpiLastRunDate.textContent = 'Ninguna corrida';
        kpiLastRunStatus.textContent = 'Aún no se han ejecutado sincronizaciones';
      }

      // Métricas globales
      if (schedulerData.metricas) {
        const m = schedulerData.metricas;
        kpiTotalRuns.textContent = m.total || 0;
        kpiRunsBreakdown.textContent = `${m.exitosas || 0} exitosas | ${m.errores || 0} errores`;
      }

      // Estado de ejecución activa en botón
      if (schedulerData.en_proceso) {
        setSyncButtonRunning(true);
      } else {
        setSyncButtonRunning(false);
      }
    } catch (e) {
      console.warn('Error consultando scheduler:', e);
    }
  }

  // Fetch Execution History List
  async function fetchHistorialData() {
    historialTbody.innerHTML = `
      <tr>
        <td colspan="9" class="loading-spinner">
          <div class="spinner"></div>
          Consultando registros de ejecución desde SQLite TI_GPF...
        </td>
      </tr>
    `;

    try {
      const res = await fetch('/api/historial_ejecuciones');
      if (!res.ok) throw new Error('Error al conectar con la API de historial');
      const data = await res.json();
      ejecucionesData = data.ejecuciones || [];

      // Calcular duración promedio
      const terminadas = ejecucionesData.filter(e => e.duracion_segundos > 0);
      if (terminadas.length > 0) {
        const avg = terminadas.reduce((sum, e) => sum + e.duracion_segundos, 0) / terminadas.length;
        kpiAvgDuration.textContent = `${avg.toFixed(1)}s`;
      }

      renderHistorialTable();
    } catch (error) {
      console.error(error);
      historialTbody.innerHTML = `
        <tr>
          <td colspan="9" style="color: var(--status-red); text-align: center; padding: 24px;">
            ❌ Error al cargar historial: ${error.message}
          </td>
        </tr>
      `;
    }
  }

  // Render Table
  function renderHistorialTable() {
    const estadoFiltro = filterEstado.value;
    let list = ejecucionesData;

    if (estadoFiltro !== 'TODOS') {
      list = list.filter(e => e.estado === estadoFiltro);
    }

    executionCountLabel.textContent = `${list.length} ejecuciones visualizadas`;

    if (list.length === 0) {
      historialTbody.innerHTML = `
        <tr>
          <td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">
            No se encontraron ejecuciones para el filtro seleccionado.
          </td>
        </tr>
      `;
      return;
    }

    historialTbody.innerHTML = list.map(e => {
      const estadoBadge = getEstadoBadge(e.estado);
      const tipoBadge = getTipoBadge(e.tipo);
      const duracionStr = e.duracion_segundos !== null ? `${e.duracion_segundos}s` : 'En curso...';
      const metricasInfo = `${e.correos_procesados || 0} archivos / ${e.filas_insertadas || 0} tickets`;

      return `
        <tr>
          <td><strong style="color: #93c5fd;">#${e.id}</strong></td>
          <td>${e.fecha_inicio}</td>
          <td>${e.fecha_fin || '<em style="color: var(--text-muted);">En proceso</em>'}</td>
          <td>${tipoBadge}</td>
          <td><strong>${duracionStr}</strong></td>
          <td>${estadoBadge}</td>
          <td><span style="font-weight: 600; color: #f3f4f6;">${metricasInfo}</span></td>
          <td style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${e.mensaje || ''}">
            ${e.mensaje || '-'}
          </td>
          <td style="text-align: center;">
            <button class="btn-action-small btn-view-log" data-id="${e.id}">
              📄 Ver Log
            </button>
          </td>
        </tr>
      `;
    }).join('');

    // Attach click events to "Ver Log" buttons
    document.querySelectorAll('.btn-view-log').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        openLogModal(id);
      });
    });
  }

  // Set Sync Button State
  function setSyncButtonRunning(isRunning) {
    if (isRunning) {
      btnSyncManual.disabled = true;
      syncIcon.textContent = '⏳';
      syncText.textContent = 'Sincronizando correos de Outlook...';
      btnSyncManual.style.background = 'linear-gradient(135deg, #f59e0b, #d97706)';
      btnSyncManual.style.boxShadow = '0 0 16px rgba(245, 158, 11, 0.4)';
    } else {
      btnSyncManual.disabled = false;
      syncIcon.textContent = '▶️';
      syncText.textContent = 'Sincronizar Correos Ahora (Manual)';
      btnSyncManual.style.background = 'linear-gradient(135deg, #3b82f6, #2563eb)';
      btnSyncManual.style.boxShadow = '0 4px 12px rgba(37, 99, 235, 0.35)';
    }
  }

  // Trigger Manual Sync
  async function triggerManualSync() {
    setSyncButtonRunning(true);
    try {
      const res = await fetch('/api/ejecutar_ingesta', { method: 'POST' });
      const data = await res.json();

      if (res.status === 409) {
        alert('⚠️ ' + data.mensaje);
        return;
      }

      // Start polling to detect completion
      if (pollingInterval) clearInterval(pollingInterval);
      pollingInterval = setInterval(async () => {
        const checkRes = await fetch('/api/estado_scheduler');
        if (checkRes.ok) {
          const s = await checkRes.json();
          if (!s.en_proceso) {
            clearInterval(pollingInterval);
            pollingInterval = null;
            setSyncButtonRunning(false);
            fetchSchedulerStatus();
            fetchHistorialData();
          }
        }
      }, 2500);

    } catch (e) {
      console.error(e);
      alert('Error al iniciar sincronización: ' + e.message);
      setSyncButtonRunning(false);
    }
  }

  // Open Log Modal
  async function openLogModal(id) {
    modalTitle.textContent = `Log de Ejecución #${id}`;
    modalSubtitle.textContent = 'Consultando detalle desde la base de datos...';
    modalLogContent.textContent = 'Cargando salida del terminal...';
    logModal.style.display = 'flex';

    try {
      const res = await fetch(`/api/historial_ejecuciones/${id}`);
      if (!res.ok) throw new Error('No se pudo obtener el detalle de la corrida');
      const item = await res.json();

      modalSubtitle.textContent = `Inicio: ${item.fecha_inicio} | Duración: ${item.duracion_segundos || 0}s | Estado: ${item.estado}`;
      modalLogContent.textContent = item.log_salida || 'Sin salida de terminal registrada.';
    } catch (err) {
      modalLogContent.textContent = '❌ Error al cargar log: ' + err.message;
    }
  }

  function closeLogModal() {
    logModal.style.display = 'none';
  }

  // Event Listeners
  btnSyncManual.addEventListener('click', triggerManualSync);
  btnRefreshHistory.addEventListener('click', () => {
    fetchSchedulerStatus();
    fetchHistorialData();
  });
  filterEstado.addEventListener('change', renderHistorialTable);

  modalCloseBtn.addEventListener('click', closeLogModal);
  modalCloseFooter.addEventListener('click', closeLogModal);
  logModal.addEventListener('click', (e) => {
    if (e.target === logModal) closeLogModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && logModal.style.display === 'flex') {
      closeLogModal();
    }
  });

  btnCopyLog.addEventListener('click', () => {
    navigator.clipboard.writeText(modalLogContent.textContent).then(() => {
      const orig = btnCopyLog.textContent;
      btnCopyLog.textContent = '✅ ¡Copiado!';
      setTimeout(() => { btnCopyLog.textContent = orig; }, 2000);
    });
  });

  // Initial Data Load
  fetchSchedulerStatus();
  fetchHistorialData();

  // Auto-refresh scheduler status every 30s
  setInterval(fetchSchedulerStatus, 30000);
});
