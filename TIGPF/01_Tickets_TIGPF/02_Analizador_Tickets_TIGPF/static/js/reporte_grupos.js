/* --------------------------------------------------------------------------
   REPORTE CASOS POR GRUPOS - REPORTE_GRUPOS.JS
   Corporación GPF | Dashboard Analítico de Tickets TI_GPF
   -------------------------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
  let reporteData = null;
  let currentPreset = 'actual';

  const fechaInicioInput = document.getElementById('fecha-inicio');
  const fechaFinInput = document.getElementById('fecha-fin');
  const btnFiltrarFechas = document.getElementById('btn-filtrar-fechas');
  const presetButtons = document.querySelectorAll('.tab-btn[data-preset]');
  const btnExportarExcel = document.getElementById('btn-exportar-excel');
  const reporteTbody = document.getElementById('reporte-tbody');
  const rangoFechasLabel = document.getElementById('rango-fechas-label');

  // Helper: Format number or empty space if 0 (matching original report screenshot)
  function fmtNum(val) {
    if (val === 0 || val === '0' || val === null || val === undefined) {
      return '';
    }
    return val.toLocaleString();
  }

  // Fetch Report API
  async function fetchReporteData(useDates = false) {
    reporteTbody.innerHTML = `
      <tr>
        <td colspan="6" class="loading-spinner">
          <div class="spinner"></div>
          Generando reporte de casos por grupos...
        </td>
      </tr>
    `;

    try {
      let url = `/api/reporte_casos_grupos?temporalidad=${currentPreset}`;
      if (useDates && fechaInicioInput.value && fechaFinInput.value) {
        url = `/api/reporte_casos_grupos?fecha_inicio=${fechaInicioInput.value}&fecha_fin=${fechaFinInput.value}`;
      }

      const response = await fetch(url);
      if (!response.ok) throw new Error('Error al consultar datos del servidor');

      reporteData = await response.json();

      if (!fechaInicioInput.value && reporteData.fecha_inicio) {
        fechaInicioInput.value = reporteData.fecha_inicio;
      }
      if (!fechaFinInput.value && reporteData.fecha_fin) {
        fechaFinInput.value = reporteData.fecha_fin;
      }

      rangoFechasLabel.textContent = `Periodo del ${reporteData.fecha_inicio || 'Inicio'} al ${reporteData.fecha_fin || 'Actualidad'}`;
      renderReporteTable();
    } catch (error) {
      console.error(error);
      reporteTbody.innerHTML = `
        <tr>
          <td colspan="6" style="color: var(--status-red); text-align: center; padding: 20px;">
            ❌ Error al cargar reporte: ${error.message}
          </td>
        </tr>
      `;
    }
  }

  // Render Table Matching Original Excel Image Layout
  function renderReporteTable() {
    if (!reporteData || !reporteData.grupos) return;

    const grupos = reporteData.grupos;
    const granTotal = reporteData.gran_total;

    if (grupos.length === 0) {
      reporteTbody.innerHTML = `
        <tr>
          <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 30px;">
            No se encontraron casos registrados para el rango de fechas seleccionado.
          </td>
        </tr>
      `;
      return;
    }

    let html = '';

    grupos.forEach(g => {
      const analistas = g.analistas || [];
      const subtotal = g.subtotal;
      const rowSpanCount = analistas.length + 1; // Analistas + Fila Subtotal

      analistas.forEach((a, idx) => {
        html += `<tr>`;
        if (idx === 0) {
          html += `<td rowspan="${rowSpanCount}" class="group-cell">${g.assign_to_group}</td>`;
        }
        html += `
          <td>
            <a href="/analista?nombre=${encodeURIComponent(a.assign_to_individual)}" target="_blank" class="analyst-name-link">
              ${a.assign_to_individual}
            </a>
          </td>
          <td class="right">${fmtNum(a.pending)}</td>
          <td class="right">${fmtNum(a.queued)}</td>
          <td class="right">${fmtNum(a.resolved)}</td>
          <td class="right"><strong>${a.total}</strong></td>
        </tr>`;
      });

      // Subtotal por Grupo (Matching Screenshot: "Total", subtotal values)
      html += `
        <tr class="group-subtotal">
          <td style="font-weight: 800;">Total</td>
          <td class="right">${fmtNum(subtotal.pending)}</td>
          <td class="right">${fmtNum(subtotal.queued)}</td>
          <td class="right">${fmtNum(subtotal.resolved)}</td>
          <td class="right" style="font-weight: 900;">${subtotal.total}</td>
        </tr>
      `;
    });

    // Gran Total (Matching Screenshot: Total | Total | 32 | 35 | 58 | 125)
    html += `
      <tr class="grand-total">
        <td>Total</td>
        <td>Total</td>
        <td class="right">${fmtNum(granTotal.pending)}</td>
        <td class="right">${fmtNum(granTotal.queued)}</td>
        <td class="right">${fmtNum(granTotal.resolved)}</td>
        <td class="right" style="font-size: 16px;">${granTotal.total}</td>
      </tr>
    `;

    reporteTbody.innerHTML = html;
  }

  // Quick Preset Handlers
  presetButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      presetButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentPreset = btn.getAttribute('data-preset');

      // Clear date inputs when using quick preset
      if (currentPreset !== 'custom') {
        fechaInicioInput.value = '';
        fechaFinInput.value = '';
      }
      fetchReporteData(false);
    });
  });

  // Filter By Date Button
  btnFiltrarFechas.addEventListener('click', () => {
    presetButtons.forEach(b => b.classList.remove('active'));
    currentPreset = 'custom';
    fetchReporteData(true);
  });

  // Export to Excel / CSV
  btnExportarExcel.addEventListener('click', () => {
    if (!reporteData) return;
    const table = document.querySelector('.excel-report-table');
    const html = table.outerHTML;
    const blob = new Blob(['\ufeff' + html], { type: 'application/vnd.ms-excel' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Reporte_Casos_por_Grupos_${reporteData.fecha_inicio}_al_${reporteData.fecha_fin}.xls`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  });

  // Initial Load
  fetchReporteData(false);
});
