/* --------------------------------------------------------------------------
   STANDBY SHIFTS MANAGEMENT CLIENT-SIDE LOGIC - STANDBY.JS
   Corporación GPF | Dashboard Analítico de Tickets TI_GPF
   -------------------------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', () => {
  let standbyData = [];
  let turnoActual = null;
  let analistasList = [];
  let currentTipoPeriodo = 'TODOS';

  // DOM Elements
  const standbySearch = document.getElementById('standby-search');
  const standbyFilterAnio = document.getElementById('standby-filter-anio');
  const standbyFilterMes = document.getElementById('standby-filter-mes');
  const standbyFilterEstado = document.getElementById('standby-filter-estado');
  const standbyTipoTabs = document.querySelectorAll('#standby-tipo-tabs .tab-btn');
  const btnRefreshStandby = document.getElementById('btn-refresh-standby');
  const standbyCountLabel = document.getElementById('standby-count-label');
  const standbyTbody = document.getElementById('standby-tbody');

  // Hero Card DOM Elements
  const heroAnalystName = document.getElementById('hero-analyst-name');
  const heroGroupName = document.getElementById('hero-group-name');
  const heroStatusBadge = document.getElementById('hero-status-badge');
  const heroPeriodoBadge = document.getElementById('hero-periodo-badge');
  const heroFechas = document.getElementById('hero-fechas');
  const heroSemanaAnio = document.getElementById('hero-semana-anio');
  const heroTelefono = document.getElementById('hero-telefono');
  const heroNotas = document.getElementById('hero-notas');
  const heroBtnEdit = document.getElementById('hero-btn-edit');

  // Modal DOM Elements
  const standbyModal = document.getElementById('standby-modal');
  const modalTitle = document.getElementById('modal-title');
  const btnOpenCreateModal = document.getElementById('btn-open-create-modal');
  const modalBtnClose = document.getElementById('modal-btn-close');
  const modalBtnCancel = document.getElementById('modal-btn-cancel');
  const standbyForm = document.getElementById('standby-form');

  // Form Inputs
  const formTurnoId = document.getElementById('form-turno-id');
  const formAnalista = document.getElementById('form-analista');
  const formGrupo = document.getElementById('form-grupo');
  const formTipoPeriodo = document.getElementById('form-tipo-periodo');
  const formEstado = document.getElementById('form-estado');
  const formFechaInicio = document.getElementById('form-fecha-inicio');
  const formFechaFin = document.getElementById('form-fecha-fin');
  const formSemana = document.getElementById('form-semana');
  const formMes = document.getElementById('form-mes');
  const formAnio = document.getElementById('form-anio');
  const formDias = document.getElementById('form-dias');
  const formTelefono = document.getElementById('form-telefono');
  const formNotas = document.getElementById('form-notas');

  // Helper: Format month name
  const MESES = [
    '', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
  ];

  function getStatusBadgeHTML(estado) {
    const est = (estado || '').toUpperCase();
    if (est === 'ACTIVO') {
      return '<span class="badge-standby-active">🟢 ACTIVO</span>';
    } else if (est === 'PROGRAMADO') {
      return '<span class="badge-standby-prog">🔵 PROGRAMADO</span>';
    } else if (est === 'COMPLETADO') {
      return '<span class="badge-standby-done">⚪ COMPLETADO</span>';
    } else if (est === 'CANCELADO') {
      return '<span class="badge-threshold badge-red">🔴 CANCELADO</span>';
    }
    return `<span class="badge-threshold">${est}</span>`;
  }

  // --------------------------------------------------------------------------
  // CARGA DE DATOS: ANALISTAS & TURNOS
  // --------------------------------------------------------------------------
  async function loadAnalistasList() {
    try {
      const res = await fetch('/api/analistas_lista');
      const data = await res.json();
      if (res.ok && data.analistas) {
        analistasList = data.analistas;
        formAnalista.innerHTML = '<option value="">Seleccione especialista...</option>';
        analistasList.forEach(a => {
          const opt = document.createElement('option');
          opt.value = a.assign_to_individual;
          opt.textContent = `${a.assign_to_individual} (${a.assign_to_group})`;
          opt.dataset.group = a.assign_to_group;
          formAnalista.appendChild(opt);
        });
      }
    } catch (err) {
      console.error('Error al cargar analistas:', err);
    }
  }

  async function fetchStandbyData() {
    standbyTbody.innerHTML = `
      <tr>
        <td colspan="11" class="loading-spinner">
          <div class="spinner"></div>
          Consultando cronograma de standby desde SQLite TI_GPF...
        </td>
      </tr>
    `;

    try {
      const anio = standbyFilterAnio.value;
      const mes = standbyFilterMes.value;
      const estado = standbyFilterEstado.value;

      const params = new URLSearchParams();
      if (currentTipoPeriodo !== 'TODOS') params.append('tipo_periodo', currentTipoPeriodo);
      if (anio !== 'TODOS') params.append('anio', anio);
      if (mes !== 'TODOS') params.append('mes', mes);
      if (estado !== 'TODOS') params.append('estado', estado);

      const res = await fetch(`/api/standby?${params.toString()}`);
      const data = await res.json();

      if (res.ok) {
        standbyData = data.turnos || [];
        turnoActual = data.turno_actual || null;
        renderHeroCard();
        renderStandbyTable();
      } else {
        standbyTbody.innerHTML = `
          <tr>
            <td colspan="11" style="text-align: center; color: var(--status-red); padding: 25px;">
              Error al consultar turnos de standby: ${data.error || 'Error de servidor'}
            </td>
          </tr>
        `;
      }
    } catch (err) {
      console.error('Error al cargar standby:', err);
      standbyTbody.innerHTML = `
        <tr>
          <td colspan="11" style="text-align: center; color: var(--status-red); padding: 25px;">
            Error de conexión al servidor al cargar el cronograma de standby.
          </td>
        </tr>
      `;
    }
  }

  // --------------------------------------------------------------------------
  // RENDER HERO CARD (QUIÉN ESTÁ DE TURNO ESTA SEMANA)
  // --------------------------------------------------------------------------
  function renderHeroCard() {
    if (turnoActual) {
      heroAnalystName.textContent = turnoActual.assign_to_individual;
      heroGroupName.textContent = turnoActual.assign_to_group || 'Especialista TI GPF';
      heroStatusBadge.className = turnoActual.estado === 'ACTIVO' ? 'badge-standby-active' : 'badge-standby-prog';
      heroStatusBadge.innerHTML = turnoActual.estado === 'ACTIVO' ? '🟢 ACTIVO EN GUARDIA' : `🔵 ${turnoActual.estado}`;
      heroPeriodoBadge.textContent = `Turno ${turnoActual.tipo_periodo || 'SEMANAL'}`;

      heroFechas.textContent = `${turnoActual.fecha_inicio} al ${turnoActual.fecha_fin}`;
      heroSemanaAnio.textContent = `Semana ${turnoActual.semana_anio || '-'} • Año ${turnoActual.anio || '-'} (${turnoActual.dia_semana || 'Lunes a Domingo'})`;
      
      heroTelefono.textContent = turnoActual.telefono_contacto || 'No registrado';
      heroNotas.textContent = turnoActual.notas ? `Nota: ${turnoActual.notas}` : 'Sin observaciones adicionales';
      heroNotas.title = turnoActual.notas || '';

      heroBtnEdit.style.display = 'inline-flex';
      heroBtnEdit.onclick = () => openEditModal(turnoActual.id);
    } else {
      heroAnalystName.textContent = 'Sin Guardia Asignada Actualmente';
      heroGroupName.textContent = 'Ningún especialista se encuentra marcado en Standby para la fecha actual';
      heroStatusBadge.className = 'badge-threshold';
      heroStatusBadge.textContent = '⚪ Inactivo';
      heroPeriodoBadge.textContent = 'Sin Turno';
      heroFechas.textContent = 'No hay vigencia activa';
      heroSemanaAnio.textContent = 'Haga clic en "+ Programar Nuevo Turno" para asignar una guardia';
      heroTelefono.textContent = 'N/A';
      heroNotas.textContent = 'N/A';
      heroBtnEdit.style.display = 'none';
    }
  }

  // --------------------------------------------------------------------------
  // RENDER TABLA DE STANDBY
  // --------------------------------------------------------------------------
  function renderStandbyTable() {
    const searchTerm = (standbySearch.value || '').trim().toLowerCase();

    let filtered = standbyData.filter(t => {
      if (!searchTerm) return true;
      return (
        (t.assign_to_individual || '').toLowerCase().includes(searchTerm) ||
        (t.assign_to_group || '').toLowerCase().includes(searchTerm) ||
        (t.telefono_contacto || '').toLowerCase().includes(searchTerm) ||
        (t.notas || '').toLowerCase().includes(searchTerm)
      );
    });

    standbyCountLabel.textContent = `${filtered.length} Turno(s) Registrado(s)`;

    if (filtered.length === 0) {
      standbyTbody.innerHTML = `
        <tr>
          <td colspan="11" style="text-align: center; color: var(--text-muted); padding: 30px;">
            No se encontraron turnos de standby con los filtros seleccionados.
          </td>
        </tr>
      `;
      return;
    }

    standbyTbody.innerHTML = filtered.map(t => {
      const isAct = t.estado === 'ACTIVO';
      const mesNombre = MESES[t.mes] || `Mes ${t.mes || '-'}`;
      const statusBadge = getStatusBadgeHTML(t.estado);

      return `
        <tr class="${isAct ? 'row-standby-active' : ''}" style="${isAct ? 'background: rgba(16, 185, 129, 0.06);' : ''}">
          <td><strong>${t.anio || '-'}</strong></td>
          <td><span style="color: #93c5fd; font-weight: 600;">${mesNombre}</span></td>
          <td><span class="badge-threshold badge-blue" style="font-size: 11px;">Semana ${t.semana_anio || '-'}</span></td>
          <td>
            <div style="font-weight: 700; color: #ffffff;">${t.fecha_inicio} al ${t.fecha_fin}</div>
            <div style="font-size: 11px; color: var(--text-muted);">${t.dia_semana || 'Lunes a Domingo'}</div>
          </td>
          <td><span class="badge-threshold badge-yellow" style="font-size: 11px;">${t.tipo_periodo}</span></td>
          <td>
            <div style="font-weight: 700; font-size: 13px; color: #ffffff;">
              ${t.assign_to_individual}
              ${isAct ? ' <span style="font-size: 11px; color: #6ee7b7;">(Actual)</span>' : ''}
            </div>
          </td>
          <td><div class="analyst-group">${t.assign_to_group || '-'}</div></td>
          <td>
            <strong style="color: #6ee7b7; font-size: 13px;">${t.telefono_contacto || '-'}</strong>
          </td>
          <td>${statusBadge}</td>
          <td>
            <div style="font-size: 12px; color: var(--text-secondary); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${t.notas || ''}">
              ${t.notas || '<span style="color: var(--text-muted);">Sin notas</span>'}
            </div>
          </td>
          <td style="text-align: center;">
            <div style="display: inline-flex; align-items: center; gap: 6px;">
              <button class="btn-action-small btn-edit-standby" data-id="${t.id}" title="Editar este turno">
                ✏️
              </button>
              <button class="btn-action-small btn-delete-standby" data-id="${t.id}" data-name="${t.assign_to_individual}" data-week="${t.semana_anio}" style="color: #ef4444; border-color: rgba(239, 68, 68, 0.4);" title="Eliminar este turno">
                🗑️
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  }

  // --------------------------------------------------------------------------
  // MODAL LOGIC: CREATE & EDIT
  // --------------------------------------------------------------------------
  function openCreateModal() {
    formTurnoId.value = '';
    standbyForm.reset();
    modalTitle.textContent = 'Programar Nuevo Turno de Standby';

    // Prepopulate default dates (current week: Monday to Sunday)
    const now = new Date();
    const dayOfWeek = (now.getDay() + 6) % 7; // Monday = 0
    const monday = new Date(now);
    monday.setDate(now.getDate() - dayOfWeek);
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);

    formFechaInicio.value = formatDateToYMD(monday);
    formFechaFin.value = formatDateToYMD(sunday);
    formTipoPeriodo.value = 'SEMANAL';
    formEstado.value = 'PROGRAMADO';
    formDias.value = 'Lunes a Domingo';

    calculateAutoFields(monday);

    standbyModal.classList.add('show');
  }

  async function openEditModal(turnoId) {
    try {
      const res = await fetch(`/api/standby/${turnoId}`);
      const t = await res.json();
      if (!res.ok) {
        alert('Error al consultar datos del turno: ' + (t.error || 'No encontrado'));
        return;
      }

      formTurnoId.value = t.id;
      modalTitle.textContent = `Modificar Turno de Standby #${t.id}`;

      formAnalista.value = t.assign_to_individual;
      formGrupo.value = t.assign_to_group || '';
      formTipoPeriodo.value = t.tipo_periodo || 'SEMANAL';
      formEstado.value = t.estado || 'PROGRAMADO';
      formFechaInicio.value = t.fecha_inicio || '';
      formFechaFin.value = t.fecha_fin || '';
      formSemana.value = t.semana_anio || '';
      formMes.value = t.mes || '';
      formAnio.value = t.anio || '';
      formDias.value = t.dia_semana || 'Lunes a Domingo';
      formTelefono.value = t.telefono_contacto || '';
      formNotas.value = t.notas || '';

      standbyModal.classList.add('show');
    } catch (err) {
      console.error('Error al abrir modal de edición:', err);
      alert('Error de conexión al consultar turno');
    }
  }

  function closeModal() {
    standbyModal.classList.remove('show');
  }

  function formatDateToYMD(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
  }

  function getISOWeek(date) {
    const target = new Date(date.valueOf());
    const dayNr = (date.getDay() + 6) % 7;
    target.setDate(target.getDate() - dayNr + 3);
    const firstThursday = target.valueOf();
    target.setMonth(0, 1);
    if (target.getDay() !== 4) {
      target.setMonth(0, 1 + ((4 - target.getDay()) + 7) % 7);
    }
    return 1 + Math.ceil((firstThursday - target) / 604800000);
  }

  function calculateAutoFields(dateObj) {
    if (!dateObj || isNaN(dateObj.getTime())) return;
    formSemana.value = getISOWeek(dateObj);
    formMes.value = dateObj.getMonth() + 1;
    formAnio.value = dateObj.getFullYear();
  }

  // Auto-complete group when analyst is selected
  formAnalista.addEventListener('change', () => {
    const selectedOpt = formAnalista.options[formAnalista.selectedIndex];
    if (selectedOpt && selectedOpt.dataset.group) {
      formGrupo.value = selectedOpt.dataset.group;
    }
  });

  // Auto-calculate week/month/year when start date changes
  formFechaInicio.addEventListener('change', () => {
    if (!formFechaInicio.value) return;
    const parts = formFechaInicio.value.split('-');
    const dt = new Date(parts[0], parts[1] - 1, parts[2]);
    calculateAutoFields(dt);

    if (formTipoPeriodo.value === 'SEMANAL') {
      const sunday = new Date(dt);
      sunday.setDate(dt.getDate() + 6);
      formFechaFin.value = formatDateToYMD(sunday);
      formDias.value = 'Lunes a Domingo';
    } else if (formTipoPeriodo.value === 'DIARIO') {
      formFechaFin.value = formFechaInicio.value;
      const diasNombres = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
      formDias.value = diasNombres[dt.getDay()];
    }
  });

  formTipoPeriodo.addEventListener('change', () => {
    if (!formFechaInicio.value) return;
    const parts = formFechaInicio.value.split('-');
    const dt = new Date(parts[0], parts[1] - 1, parts[2]);

    if (formTipoPeriodo.value === 'SEMANAL') {
      const sunday = new Date(dt);
      sunday.setDate(dt.getDate() + 6);
      formFechaFin.value = formatDateToYMD(sunday);
      formDias.value = 'Lunes a Domingo';
    } else if (formTipoPeriodo.value === 'DIARIO') {
      formFechaFin.value = formFechaInicio.value;
      const diasNombres = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
      formDias.value = diasNombres[dt.getDay()];
    } else if (formTipoPeriodo.value === 'MENSUAL') {
      formDias.value = 'Mes Completo';
    }
  });

  // --------------------------------------------------------------------------
  // SUBMIT FORM (CREATE OR UPDATE)
  // --------------------------------------------------------------------------
  standbyForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const turnoId = formTurnoId.value;
    const isEdit = Boolean(turnoId);

    const payload = {
      assign_to_individual: formAnalista.value.trim(),
      assign_to_group: formGrupo.value.trim(),
      tipo_periodo: formTipoPeriodo.value,
      estado: formEstado.value,
      fecha_inicio: formFechaInicio.value,
      fecha_fin: formFechaFin.value,
      semana_anio: parseInt(formSemana.value, 10) || 1,
      mes: parseInt(formMes.value, 10) || 1,
      anio: parseInt(formAnio.value, 10) || 2026,
      dia_semana: formDias.value.trim() || 'Lunes a Domingo',
      telefono_contacto: formTelefono.value.trim(),
      notas: formNotas.value.trim()
    };

    if (!payload.assign_to_individual || !payload.fecha_inicio || !payload.fecha_fin) {
      alert('Por favor complete los campos obligatorios: Especialista, Fecha de Inicio y Fecha de Fin.');
      return;
    }

    const btnSubmit = document.getElementById('modal-btn-save');
    btnSubmit.disabled = true;
    btnSubmit.textContent = 'Guardando...';

    try {
      const url = isEdit ? `/api/standby/${turnoId}` : '/api/standby';
      const method = isEdit ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const resJson = await res.json();
      if (res.ok) {
        closeModal();
        fetchStandbyData();
      } else {
        alert('Error al guardar turno: ' + (resJson.error || 'Error desconocido'));
      }
    } catch (err) {
      console.error('Error al guardar:', err);
      alert('Error de conexión al servidor.');
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.textContent = '💾 Guardar Turno';
    }
  });

  // --------------------------------------------------------------------------
  // EVENT DELEGATION: EDIT AND DELETE
  // --------------------------------------------------------------------------
  standbyTbody.addEventListener('click', async (e) => {
    const btnEdit = e.target.closest('.btn-edit-standby');
    if (btnEdit) {
      const id = btnEdit.dataset.id;
      openEditModal(id);
      return;
    }

    const btnDelete = e.target.closest('.btn-delete-standby');
    if (btnDelete) {
      const id = btnDelete.dataset.id;
      const name = btnDelete.dataset.name;
      const week = btnDelete.dataset.week;

      const confirmDelete = confirm(`¿Está seguro de ELIMINAR el turno de Standby de ${name} (Semana ${week})? Esta acción no se puede revertir.`);
      if (!confirmDelete) return;

      try {
        const res = await fetch(`/api/standby/${id}`, { method: 'DELETE' });
        const resJson = await res.json();
        if (res.ok && resJson.status === 'eliminado') {
          fetchStandbyData();
        } else {
          alert('Error al eliminar turno: ' + (resJson.error || 'Error desconocido'));
        }
      } catch (err) {
        console.error('Error al eliminar:', err);
        alert('Error de conexión al servidor al intentar eliminar.');
      }
    }
  });

  // --------------------------------------------------------------------------
  // MODAL OPEN / CLOSE EVENTS
  // --------------------------------------------------------------------------
  btnOpenCreateModal.addEventListener('click', openCreateModal);
  modalBtnClose.addEventListener('click', closeModal);
  modalBtnCancel.addEventListener('click', closeModal);

  // Close modal on click outside card
  standbyModal.addEventListener('click', (e) => {
    if (e.target === standbyModal) closeModal();
  });

  // --------------------------------------------------------------------------
  // FILTER BAR EVENT LISTENERS
  // --------------------------------------------------------------------------
  standbyTipoTabs.forEach(btn => {
    btn.addEventListener('click', () => {
      standbyTipoTabs.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTipoPeriodo = btn.getAttribute('data-tipo');
      fetchStandbyData();
    });
  });

  standbyFilterAnio.addEventListener('change', fetchStandbyData);
  standbyFilterMes.addEventListener('change', fetchStandbyData);
  standbyFilterEstado.addEventListener('change', fetchStandbyData);
  standbySearch.addEventListener('input', renderStandbyTable);
  btnRefreshStandby.addEventListener('click', fetchStandbyData);

  // Initial Data Load
  loadAnalistasList();
  fetchStandbyData();
});
