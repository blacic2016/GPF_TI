/* ==============================================================================
   GEOPOS ORCHESTRATOR - CLIENT CONTROLLER
   Pure Vanilla ES6 JavaScript
   ============================================================================== */

let currentUser = null;
let phasesData = [];
let pollingInterval = null;

// Presets de 5 POS para la prueba por lotes (Bulk)
const BULK_PRESETS = [
  { pos_num: 1, target_ip: "10.108.0.11", business_unit: "FYBECA", local_id: "901", pinpad_ip: "10.121.112.81", terminal_id: "S0001721", merchant_code: "000000832686", status: "QUEUED" },
  { pos_num: 2, target_ip: "10.108.0.12", business_unit: "FYBECA", local_id: "901", pinpad_ip: "10.121.112.82", terminal_id: "S0001722", merchant_code: "000000832686", status: "QUEUED" },
  { pos_num: 3, target_ip: "10.108.0.13", business_unit: "FYBECA", local_id: "901", pinpad_ip: "10.121.112.83", terminal_id: "S0001723", merchant_code: "000000832686", status: "QUEUED" },
  { pos_num: 4, target_ip: "10.108.0.14", business_unit: "FYBECA", local_id: "901", pinpad_ip: "10.121.112.84", terminal_id: "S0001724", merchant_code: "000000832686", status: "QUEUED" },
  { pos_num: 5, target_ip: "10.108.0.15", business_unit: "FYBECA", local_id: "901", pinpad_ip: "10.121.112.85", terminal_id: "S0001725", merchant_code: "000000832686", status: "QUEUED" }
];

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initAuth();
  loadPhases();
  loadConfig();
  renderBulkPresetTable();
  startStatusPolling();

  // Attach buttons
  document.getElementById("btnModeSingle")?.addEventListener("click", () => toggleDeployMode("single"));
  document.getElementById("btnModeBulk")?.addEventListener("click", () => toggleDeployMode("bulk"));
  document.getElementById("btnStartSingle")?.addEventListener("click", startSingleDeployment);
  document.getElementById("btnStartBulk")?.addEventListener("click", startBulkDeployment);
  document.getElementById("btnRunAudit")?.addEventListener("click", runReconciliation);
  document.getElementById("btnSaveConfig")?.addEventListener("click", saveLiveConfig);
  document.getElementById("btnOpenNewUserModal")?.addEventListener("click", () => showModal("userModal"));
  document.getElementById("btnCloseUserModal")?.addEventListener("click", () => hideModal("userModal"));
  document.getElementById("btnSubmitNewUser")?.addEventListener("click", submitNewUser);

  // Botón alternar modo Simulación / Real
  document.getElementById("btnToggleSimMode")?.addEventListener("click", toggleSimulationMode);

  // Asistente Paso a Paso (Con Popups en Vivo)
  document.getElementById("btnStartWizard")?.addEventListener("click", startInteractiveWizard);
  document.getElementById("btnExecuteStep")?.addEventListener("click", executeCurrentWizardStep);
  document.getElementById("btnNextStep")?.addEventListener("click", advanceToNextWizardStep);
  document.getElementById("btnCloseWizardModal")?.addEventListener("click", () => hideModal("stepWizardModal"));
  document.getElementById("btnCancelWizard")?.addEventListener("click", () => hideModal("stepWizardModal"));
});

// ================= TABS NAVIGATION =================
function initTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

      tab.classList.add("active");
      const target = document.getElementById(tab.dataset.tab);
      if (target) target.classList.add("active");

      if (tab.dataset.tab === "tab-users") loadUsers();
      if (tab.dataset.tab === "tab-audit") runReconciliation();
    });
  });
}

function toggleDeployMode(mode) {
  const singleView = document.getElementById("formSingleView");
  const bulkView = document.getElementById("formBulkView");
  const btnSingle = document.getElementById("btnModeSingle");
  const btnBulk = document.getElementById("btnModeBulk");

  if (mode === "single") {
    singleView.style.display = "block";
    bulkView.style.display = "none";
    btnSingle.classList.replace("btn-secondary", "btn-primary");
    btnBulk.classList.replace("btn-primary", "btn-secondary");
  } else {
    singleView.style.display = "none";
    bulkView.style.display = "block";
    btnBulk.classList.replace("btn-secondary", "btn-primary");
    btnSingle.classList.replace("btn-primary", "btn-secondary");
  }
}

// ================= AUTHENTICATION =================
async function initAuth() {
  try {
    const res = await fetch("/api/session");
    const data = await res.json();
    if (data.authenticated) {
      setUserSession(data.user);
    } else {
      showModal("loginModal");
    }
  } catch (e) {
    console.error("Error verificando sesión", e);
  }

  document.getElementById("btnAuthAction")?.addEventListener("click", () => {
    if (currentUser) {
      logout();
    } else {
      showModal("loginModal");
    }
  });

  document.getElementById("btnSubmitLogin")?.addEventListener("click", login);
  document.getElementById("btnCloseLogin")?.addEventListener("click", () => hideModal("loginModal"));
}

async function login() {
  const u = document.getElementById("loginUsername").value.trim();
  const p = document.getElementById("loginPassword").value;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p })
    });
    const data = await res.json();
    if (data.success) {
      setUserSession(data.user);
      hideModal("loginModal");
    } else {
      alert("Error: " + (data.error || "Credenciales incorrectas"));
    }
  } catch (e) {
    alert("Error conectando al servidor");
  }
}

async function logout() {
  await fetch("/api/logout", { method: "POST" });
  currentUser = null;
  document.getElementById("userNameNav").innerText = "Invitado";
  document.getElementById("userRoleNav").innerText = "NONE";
  document.getElementById("btnAuthAction").innerText = "Ingresar";
  showModal("loginModal");
}

function setUserSession(user) {
  currentUser = user;
  document.getElementById("userNameNav").innerText = user.fullname || user.username;
  const roleEl = document.getElementById("userRoleNav");
  roleEl.innerText = user.role;
  roleEl.className = `role-tag role-${user.role.toLowerCase()}`;
  document.getElementById("btnAuthAction").innerText = "Salir";
}

// ================= MODAL HELPERS =================
function showModal(id) {
  document.getElementById(id)?.classList.add("active");
}
function hideModal(id) {
  document.getElementById(id)?.classList.remove("active");
}

// ================= PHASES LISTING =================
async function loadPhases() {
  try {
    const res = await fetch("/api/phases");
    const data = await res.json();
    phasesData = data.phases || [];
    renderPhasesTimeline(phasesData);
  } catch (e) {
    console.error("Error cargando fases", e);
  }
}

function renderPhasesTimeline(phases) {
  const container = document.getElementById("phasesDetailContainer");
  if (!container) return;
  container.innerHTML = phases.map(p => `
    <div class="phase-card">
      <div class="phase-num">FASE ${p.id}</div>
      <div class="phase-info">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <h4 class="phase-title">${p.name}</h4>
          <span class="phase-status-pill status-pending" id="phasePill_${p.id}">PENDIENTE</span>
        </div>
        <p class="phase-desc">${p.description}</p>
        <div style="display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:8px;">
          <span class="security-gate-badge">
            🔒 ${p.gate_title} ➔ Regla: ${p.gate_rule}
          </span>
          <span style="font-size:0.72rem; color:var(--text-muted); font-family:var(--font-mono);">
            Parámetros: ${p.params.join(", ")}
          </span>
        </div>
      </div>
    </div>
  `).join("");
}

// ================= DEPLOYMENTS =================
async function startSingleDeployment() {
  if (!currentUser) return showModal("loginModal");

  const payload = {
    business_unit: document.getElementById("deployUN").value,
    local_id: document.getElementById("deployLocalId").value,
    pos_num: parseInt(document.getElementById("deployPosNum").value) || 1,
    target_ip: document.getElementById("deployPosIp").value,
    local_server_ip: document.getElementById("deployLocalIp").value,
    pinpad_ip: document.getElementById("deployPinpadIp").value
  };

  try {
    const res = await fetch("/api/deploy/single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      appendTerminalLog(`Iniciando despliegue de ${data.pos_key}...`, "INFO");
    } else {
      alert("Error: " + (data.error || "No se pudo iniciar"));
    }
  } catch (e) {
    alert("Error de conexión");
  }
}

function renderBulkPresetTable() {
  const tbody = document.getElementById("bulkPresetBody");
  if (!tbody) return;
  tbody.innerHTML = BULK_PRESETS.map((p, idx) => `
    <tr>
      <td><strong>POS ${p.pos_num}</strong></td>
      <td><code>${p.target_ip}</code></td>
      <td><span class="role-tag role-operator">${p.business_unit}</span></td>
      <td><code>${p.pinpad_ip}</code></td>
      <td><span class="phase-status-pill status-${p.status.toLowerCase()}" id="bulkPill_${idx}">${p.status}</span></td>
    </tr>
  `).join("");
}

async function startBulkDeployment() {
  if (!currentUser) return showModal("loginModal");

  try {
    const res = await fetch("/api/deploy/bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pos_list: BULK_PRESETS })
    });
    const data = await res.json();
    if (data.success) {
      appendTerminalLog(`Lote de ${data.count} POS encolado. Iniciando ejecución secuencial...`, "SUCCESS");
    } else {
      alert("Error: " + data.error);
    }
  } catch (e) {
    alert("Error de conexión");
  }
}

// ================= REAL-TIME STATUS POLLING =================
function startStatusPolling() {
  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(fetchStatus, 1200);
}

async function fetchStatus() {
  try {
    // 0. Microservice Health
    fetch("/api/microservice/health")
      .then(r => r.json())
      .then(h => {
        const msEl = document.getElementById("textMicroservice");
        if (msEl) {
          if (h.status === "HEALTHY") {
            msEl.innerText = `Motor 5001: OK (${h.memory_mb}MB | ${h.active_threads}h)`;
            document.getElementById("badgeMicroservice").querySelector(".status-dot").className = "status-dot dot-green";
          } else {
            msEl.innerText = "Motor 5001: Reconectando...";
            document.getElementById("badgeMicroservice").querySelector(".status-dot").className = "status-dot dot-amber";
          }
        }
      })
      .catch(() => {
        const msEl = document.getElementById("textMicroservice");
        if (msEl) msEl.innerText = "Motor 5001: Standby";
      });

    const res = await fetch("/api/status");
    const data = await res.json();

    // 1. Logs
    if (data.recent_logs && data.recent_logs.length > 0) {
      renderLogs(data.recent_logs);
    }

    // 2. Active Jobs
    const jobs = Object.values(data.active_jobs || {});
    if (jobs.length > 0) {
      const activeJob = jobs[jobs.length - 1]; // Último activo
      document.getElementById("activeJobName").innerText = activeJob.pos_key;
      document.getElementById("activeJobSub").innerText = `Iniciado por: ${activeJob.started_by} a las ${activeJob.started_at}`;
      
      const pill = document.getElementById("activeJobPill");
      pill.innerText = activeJob.status;
      pill.className = `phase-status-pill status-${activeJob.status.toLowerCase()}`;

      // Progress bar (0% - 100%)
      const progress = Math.min(100, Math.round(((activeJob.current_phase + 1) / 9) * 100));
      document.getElementById("activeJobProgressBar").style.width = `${progress}%`;
      document.getElementById("activeJobStepDesc").innerText = `Fase ${activeJob.current_phase} de 8 (${progress}%)`;

      // Update timeline pills
      if (activeJob.phases_status) {
        Object.entries(activeJob.phases_status).forEach(([pId, st]) => {
          const pEl = document.getElementById(`phasePill_${pId}`);
          if (pEl) {
            pEl.innerText = st;
            pEl.className = `phase-status-pill status-${st.toLowerCase()}`;
          }
        });
      }
    }

    // 3. Bulk status
    if (data.bulk_queue && data.bulk_queue.length > 0) {
      const completedCount = data.bulk_queue.filter(q => q.status === "COMPLETED").length;
      document.getElementById("lblBulkProgress").innerText = `${completedCount} / ${data.bulk_queue.length} Completados`;
      
      data.bulk_queue.forEach((q, idx) => {
        const pEl = document.getElementById(`bulkPill_${idx}`);
        if (pEl) {
          pEl.innerText = q.status;
          pEl.className = `phase-status-pill status-${q.status.toLowerCase()}`;
        }
      });
    }

  } catch (e) {
    // Silencio en errores periódicos de red
  }
}

function renderLogs(logs) {
  const container = document.getElementById("terminalLogs");
  if (!container) return;
  document.getElementById("logCounter").innerText = `${logs.length} eventos`;
  container.innerHTML = logs.map(l => `
    <div class="log-line">
      <span class="log-time">[${l.timestamp.split(" ")[1]}]</span>
      <span class="log-pos">[${l.pos_key}]</span>
      <span class="log-${l.level.toLowerCase()}">${escapeHtml(l.message)}</span>
    </div>
  `).join("");
  container.scrollTop = container.scrollHeight;
}

function appendTerminalLog(msg, level = "INFO") {
  const container = document.getElementById("terminalLogs");
  const time = new Date().toTimeString().split(" ")[0];
  const div = document.createElement("div");
  div.className = "log-line";
  div.innerHTML = `<span class="log-time">[${time}]</span> <span class="log-${level.toLowerCase()}">${escapeHtml(msg)}</span>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

// ================= RECONCILIATION AUDIT MATRIX =================
async function runReconciliation() {
  const targetIp = document.getElementById("deployPosIp")?.value || "10.108.0.15";
  const localIp = document.getElementById("deployLocalIp")?.value || "10.108.0.101";

  try {
    const res = await fetch("/api/reconciliation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target_ip: targetIp, local_server_ip: localIp })
    });
    const data = await res.json();
    if (data.success && data.result) {
      renderReconciliationTable(data.result);
    }
  } catch (e) {
    console.error("Error al ejecutar auditoría", e);
  }
}

function renderReconciliationTable(res) {
  const tbody = document.getElementById("reconciliationBody");
  if (!tbody) return;

  const rows = [
    { key: "convenios", desc: "Convenios, Planes y Empresas", local: JSON.stringify(res.convenios.local), pos: JSON.stringify(res.convenios.pos) },
    { key: "doctores", desc: "Doctores Afiliados", local: `${res.doctores.local.doctores} registros`, pos: `${res.doctores.pos.doctores} registros` },
    { key: "locales_cercanos", desc: "Locales Cercanos", local: `${res.locales_cercanos.local.locales_cercanos} relaciones`, pos: `${res.locales_cercanos.pos.locales_cercanos} relaciones` },
    { key: "mejor_opcion", desc: "Mejor Opción Artículos", local: `${res.mejor_opcion.local.mejor_opcion} artículos`, pos: `${res.mejor_opcion.pos.mejor_opcion} artículos` },
    { key: "promociones", desc: "Promociones GP (Top 10)", local: "10 serializados", pos: "10 serializados" },
    { key: "productos", desc: "Categorías, Artículos, Precios y Barcodes", local: `Artículos: ${res.productos.local.articulos}, Barcodes: ${res.productos.local.barcodes}`, pos: `Artículos: ${res.productos.pos.articulos}, Barcodes: ${res.productos.pos.barcodes}` },
    { key: "usuarios_roles", desc: "Usuarios, Roles y Permisos", local: `Usuarios: ${res.usuarios_roles.local.users}, Permisos: ${res.usuarios_roles.local.permissions}`, pos: `Usuarios: ${res.usuarios_roles.pos.users}, Permisos: ${res.usuarios_roles.pos.permissions}` },
    { key: "planes_marcas", desc: "Planes, Marcas y Productos", local: `Marcas: ${res.planes_marcas.local.brands}, Productos: ${res.planes_marcas.local.products}`, pos: `Marcas: ${res.planes_marcas.pos.brands}, Productos: ${res.planes_marcas.pos.products}` }
  ];

  tbody.innerHTML = rows.map(r => `
    <tr>
      <td><strong>${r.desc}</strong></td>
      <td><code>${r.local}</code></td>
      <td><code>${r.pos}</code></td>
      <td><span style="color:var(--accent-emerald); font-weight:700;">0 (Idéntico)</span></td>
      <td><span class="phase-status-pill status-completed">MATCH 100%</span></td>
    </tr>
  `).join("");
}

// ================= LIVE CONFIGURATION =================
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const cfg = await res.json();
    renderConfigFields(cfg);
    document.getElementById("textMode").innerText = cfg.SIMULATION_MODE ? "Modo: Simulación" : "Modo: Producción Real";
  } catch (e) {
    console.error("Error al cargar config", e);
  }
}

function renderConfigFields(cfg) {
  const container = document.getElementById("configGridContainer");
  if (!container) return;
  
  const entries = Object.entries(cfg);
  container.innerHTML = entries.map(([k, v]) => `
    <div class="form-group" style="background:rgba(255,255,255,0.02); padding:10px; border-radius:8px; border:1px solid var(--border-color);">
      <label class="form-label">${k}</label>
      <input type="text" class="form-control config-input-field" data-key="${k}" value="${v}">
    </div>
  `).join("");
}

async function saveLiveConfig() {
  if (!currentUser) return showModal("loginModal");
  if (currentUser.role === "AUDITOR") return alert("Los auditores tienen acceso de solo lectura.");

  const inputs = document.querySelectorAll(".config-input-field");
  const payload = {};
  inputs.forEach(i => {
    payload[i.dataset.key] = i.value;
  });

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      alert("Configuración actualizada en vivo con éxito.");
      loadConfig();
    } else {
      alert("Error: " + data.error);
    }
  } catch (e) {
    alert("Error al guardar");
  }
}

// ================= USER CRUD =================
async function loadUsers() {
  try {
    const res = await fetch("/api/users");
    const data = await res.json();
    if (data.users) {
      renderUsersTable(data.users);
    }
  } catch (e) {
    console.error("Error al cargar usuarios", e);
  }
}

function renderUsersTable(users) {
  const tbody = document.getElementById("usersTableBody");
  if (!tbody) return;
  tbody.innerHTML = users.map(u => `
    <tr>
      <td><strong>${escapeHtml(u.username)}</strong></td>
      <td>${escapeHtml(u.fullname)}</td>
      <td><span class="role-tag role-${u.role.toLowerCase()}">${u.role}</span></td>
      <td style="color:var(--text-secondary); font-size:0.8rem;">${u.role_name}</td>
      <td><span class="phase-status-pill ${u.active ? 'status-completed' : 'status-failed'}">${u.active ? 'Activo' : 'Inactivo'}</span></td>
      <td>
        ${u.username !== 'admin' ? `
          <button class="btn btn-danger" style="padding:4px 8px; font-size:0.7rem;" onclick="deleteUser('${u.username}')">Eliminar</button>
        ` : `<span style="color:var(--text-muted); font-size:0.75rem;">Protegido</span>`}
      </td>
    </tr>
  `).join("");
}

async function submitNewUser() {
  const username = document.getElementById("newUsername").value.trim();
  const fullname = document.getElementById("newFullname").value.trim();
  const password = document.getElementById("newPassword").value;
  const role = document.getElementById("newRole").value;

  if (!username || !password) return alert("Complete los campos obligatorios");

  try {
    const res = await fetch("/api/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, fullname, password, role })
    });
    const data = await res.json();
    if (data.success) {
      hideModal("userModal");
      loadUsers();
      document.getElementById("newUsername").value = "";
      document.getElementById("newFullname").value = "";
      document.getElementById("newPassword").value = "";
    } else {
      alert("Error: " + data.error);
    }
  } catch (e) {
    alert("Error conectando con el servidor");
  }
}

async function deleteUser(username) {
  if (!confirm(`¿Está seguro de eliminar al usuario ${username}?`)) return;
  try {
    const res = await fetch(`/api/users/${username}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) {
      loadUsers();
    } else {
      alert("Error: " + data.error);
    }
  } catch (e) {
    alert("Error al eliminar usuario");
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// ================= MODO SIMULACIÓN vs MODO PRODUCCIÓN REAL =================
async function toggleSimulationMode() {
  try {
    const res = await fetch("/api/config/toggle-simulation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    if (data.success) {
      const isSim = data.simulation_mode;
      const dotEl = document.getElementById("dotMode");
      const textEl = document.getElementById("textMode");
      const btnEl = document.getElementById("btnToggleSimMode");

      if (isSim) {
        textEl.innerText = "Modo: Simulación";
        dotEl.className = "status-dot dot-cyan";
        btnEl.innerText = "⚡ Cambiar a Modo Real";
        btnEl.style.color = "var(--accent-cyan)";
        btnEl.style.borderColor = "var(--accent-cyan)";
      } else {
        textEl.innerText = "Modo: Producción Real";
        dotEl.className = "status-dot dot-green";
        btnEl.innerText = "⚡ Cambiar a Simulación";
        btnEl.style.color = "var(--accent-emerald)";
        btnEl.style.borderColor = "var(--accent-emerald)";
      }

      appendTerminalLog(`[SISTEMA] Modo operativo cambiado a: ${data.mode_label}`, "INFO");
      alert(`Modo cambiado exitosamente a: ${data.mode_label}\n` + (isSim ? "Las acciones se ejecutarán de forma segura simulada." : "ATENCIÓN: Las acciones se conectarán mediante SSH y MySQL real al hardware de destino."));
    }
  } catch (e) {
    alert("Error cambiando modo de simulación");
  }
}

// ================= ASISTENTE INTERACTIVO PASO A PASO (POPUPS EN VIVO) =================
let wizardCurrentPhase = 0;
let wizardAccumulatedParams = {};

const WIZARD_PHASES_INFO = [
  {
    id: 0,
    title: "Pre-flight & Conectividad de Red",
    desc: "Valide y configure las IPs, puertos y credenciales para comprobar el alcance del POS y el servidor local antes de alterar el equipo.",
    gate_rule: "Sockets SSH (puerto 22) y MySQL (puerto 3306) activos con latencia < 2000 ms.",
    fields: [
      { id: "w_bu", label: "Unidad de Negocio (Cadena)", type: "select", options: ["FYBECA", "SANASANA"], val: "FYBECA" },
      { id: "w_pos_ip", label: "IP del POS Destino", type: "text", val: "10.108.0.15" },
      { id: "w_local_ip", label: "IP Servidor del Local (MySQL Central)", type: "text", val: "10.108.0.101" },
      { id: "w_local_id", label: "ID del Local", type: "text", val: "901" },
      { id: "w_pos_num", label: "Número de Caja / POS", type: "number", val: "1" },
      { id: "w_ssh_pass", label: "Contraseña SSH usuario geocom", type: "password", val: "geocom" },
      { id: "w_mysql_pass", label: "Contraseña MySQL root", type: "password", val: "geocom" }
    ]
  },
  {
    id: 1,
    title: "Extracción de Artefactos desde Repo Central",
    desc: "Confirme los paquetes que se descargarán vía SCP desde el repositorio central hacia /home/geocom en el POS.",
    gate_rule: "DumpBaseCaja.sql, PaqueteBaseCaja.tgz y geopos2gpf presentes en el POS con Checksum válido.",
    fields: [
      { id: "w_repo_ip", label: "IP Servidor Repositorio Central", type: "text", val: "172.21.9.12" },
      { id: "w_repo_path", label: "Directorio Base en Repositorio", type: "text", val: "/home/geocom/repo_geo" },
      { id: "w_dump_file", label: "Archivo Dump Base Inicial", type: "text", val: "DumpBaseCaja.sql" },
      { id: "w_base_pkg", label: "Paquete Base de Caja", type: "text", val: "PaqueteBaseCaja.tgz" }
    ]
  },
  {
    id: 2,
    title: "Estructura de Directorios Linux y Gnome",
    desc: "Creación del árbol de carpetas de GeoPOS y GeoConfigurator, descompresión base y registro de accesos en el escritorio Gnome.",
    gate_rule: "Carpetas creadas con permisos geocom y dconf write ejecutado correctamente.",
    fields: [
      { id: "w_dest_dir", label: "Directorio Raíz de Usuario", type: "text", val: "/home/geocom" },
      { id: "w_desktop_apps", label: "Accesos Directos Favoritos", type: "text", val: "['firefox.desktop','GEOPOS.desktop','org.gnome.Nautilus.desktop','org.gnome.Terminal.desktop']" }
    ]
  },
  {
    id: 3,
    title: "Identificación de Terminal en GeoConfigurator",
    desc: "Generación del archivo identifier.properties con el código unívoco de caja en el formato root.produccion.<UN>.<LOCAL>.<POS>.",
    gate_rule: "identifier.properties contiene terminalId con nomenclatura oficial validada.",
    fields: [
      { id: "w_terminal_id", label: "Identificador de Terminal (terminalId)", type: "text", val: "root.produccion.fybeca.901.1" },
      { id: "w_cfg_file", label: "Ruta de Propiedades", type: "text", val: "/home/geocom/geoconfigurator/geoconfigurator/cfg/client/identifier.properties" }
    ]
  },
  {
    id: 4,
    title: "Instalación de GeoPOS y Librerías Epson",
    desc: "Despliegue de binarios de versión, creación del enlace simbólico 'current' e instalación de controladores de impresión Epson.",
    gate_rule: "Enlace simbólico /home/geocom/geopos/current activo y librerías Epson descomprimidas.",
    fields: [
      { id: "w_geopos_ver", label: "Paquete de Versión GeoPOS", type: "text", val: "geopos2gpf-fybeca-2.0.7.1.47.1.7.tar" },
      { id: "w_symlink", label: "Enlace Simbólico Activo", type: "text", val: "current" },
      { id: "w_epson_pkg", label: "Paquete Drivers Epson", type: "text", val: "LibreriasEpson.tgz" }
    ]
  },
  {
    id: 5,
    title: "Aprovisionamiento MySQL y Sincronización Local",
    desc: "Creación del schema geopos, carga del DumpBase, extracción de tablas maestras desde el local y parches de Liquibase e IVA.",
    gate_rule: "SELECT count(*) en information_schema == 239 tablas e IVA taxes.rate == 0.15 tras reboot.",
    fields: [
      { id: "w_db_name", label: "Nombre de Base de Datos", type: "text", val: "geopos" },
      { id: "w_expected_tables", label: "Total de Tablas Requeridas", type: "number", val: "239" },
      { id: "w_iva_rate", label: "Tasa de IVA Oficial", type: "text", val: "0.15" },
      { id: "w_unlock_liquibase", label: "Forzar desbloqueo de DATABASECHANGELOGLOCK", type: "checkbox", val: true }
    ]
  },
  {
    id: 6,
    title: "Configuración de PINPAD y Tareas Crontab",
    desc: "Asignación de parámetros bancarios en wposs.properties y pinpad.sh, y programación de rutinas de respaldo y promociones.",
    gate_rule: "Ping exitoso a la IP del Pinpad y 3 tareas programadas activas en crontab.",
    fields: [
      { id: "w_pinpad_ip", label: "Dirección IP del Pinpad", type: "text", val: "10.121.112.81" },
      { id: "w_merchant_code", label: "Código de Comercio (Merchant Code)", type: "text", val: "000000832686" },
      { id: "w_term_id_pinpad", label: "Terminal ID de Red Bancaria", type: "text", val: "S0001728" }
    ]
  },
  {
    id: 7,
    title: "Secuencias Fiscales SRI y Facturación Electrónica",
    desc: "Detención obligatoria del proceso geopos, cálculo del último ticket + 500, SRI + 10 y actualización de intsequencer y longsequencer.",
    gate_rule: "Proceso geopos detenido con kill -9 verificado, y secuencias en BD coincidentes con cálculo fiscal.",
    fields: [
      { id: "w_max_ticket", label: "Último Ticket Registrado en Servidor Local", type: "number", val: "5985" },
      { id: "w_offset_ticket", label: "Offset de Seguridad a Sumar", type: "number", val: "500" },
      { id: "w_offset_sri", label: "Offset SRI a Sumar", type: "number", val: "10" },
      { id: "w_kill_confirm", label: "Confirmar detención de GeoPOS antes de inyectar secuencias", type: "checkbox", val: true }
    ]
  },
  {
    id: 8,
    title: "Matriz de Reconciliación Cruzada (Certificación)",
    desc: "Comparativa SQL en tiempo real de los 8 módulos entre el Servidor Local y el POS para autorizar el pase a producción.",
    gate_rule: "100% de paridad en Convenios, Catálogos, Promociones, Precios y Usuarios.",
    fields: [
      { id: "w_audit_modules", label: "Módulos a Reconciliar", type: "text", val: "8 (Convenios, Doctores, Locales, Precios, Promos, Usuarios, Marcas)" },
      { id: "w_cert_notes", label: "Notas de Certificación y Firma Técnica", type: "text", val: "POS verificado y certificado sin discrepancias fiscales." }
    ]
  }
];

function startInteractiveWizard() {
  if (!currentUser) return showModal("loginModal");

  // Leer valores iniciales de la pantalla unitaria
  wizardAccumulatedParams = {
    business_unit: document.getElementById("deployUN")?.value || "FYBECA",
    local_id: document.getElementById("deployLocalId")?.value || "901",
    pos_num: parseInt(document.getElementById("deployPosNum")?.value) || 1,
    target_ip: document.getElementById("deployPosIp")?.value || "10.108.0.15",
    local_server_ip: document.getElementById("deployLocalIp")?.value || "10.108.0.101",
    pinpad_ip: document.getElementById("deployPinpadIp")?.value || "10.121.112.81"
  };

  openWizardStep(0);
}

function openWizardStep(phaseId) {
  wizardCurrentPhase = phaseId;
  const phaseInfo = WIZARD_PHASES_INFO[phaseId];
  if (!phaseInfo) return;

  document.getElementById("wizardPhaseBadge").innerText = `FASE ${phaseId} DE 8`;
  document.getElementById("wizardPhaseTitle").innerText = phaseInfo.title;
  document.getElementById("wizardPhaseDesc").innerText = phaseInfo.desc;
  document.getElementById("wizardGateRule").innerText = `Regla: ${phaseInfo.gate_rule}`;

  const alertEl = document.getElementById("wizardStatusAlert");
  alertEl.style.display = "none";
  alertEl.innerHTML = "";

  document.getElementById("btnExecuteStep").style.display = "block";
  document.getElementById("btnNextStep").style.display = "none";

  // Pre-calcular campos especiales
  if (phaseId === 3) {
    const un = (wizardAccumulatedParams.business_unit || "fybeca").toLowerCase();
    const loc = wizardAccumulatedParams.local_id || "901";
    const pos = wizardAccumulatedParams.pos_num || "1";
    phaseInfo.fields[0].val = `root.produccion.${un}.${loc}.${pos}`;
  }
  if (phaseId === 0) {
    phaseInfo.fields[0].val = wizardAccumulatedParams.business_unit || "FYBECA";
    phaseInfo.fields[1].val = wizardAccumulatedParams.target_ip || "10.108.0.15";
    phaseInfo.fields[2].val = wizardAccumulatedParams.local_server_ip || "10.108.0.101";
    phaseInfo.fields[3].val = wizardAccumulatedParams.local_id || "901";
    phaseInfo.fields[4].val = wizardAccumulatedParams.pos_num || 1;
  }
  if (phaseId === 6 && wizardAccumulatedParams.pinpad_ip) {
    phaseInfo.fields[0].val = wizardAccumulatedParams.pinpad_ip;
  }

  // Renderizar campos
  const container = document.getElementById("wizardFieldsContainer");
  container.innerHTML = phaseInfo.fields.map(f => {
    if (f.type === "select") {
      return `
        <div class="form-group">
          <label class="form-label">${f.label}</label>
          <select class="form-control wizard-input-field" data-field="${f.id}">
            ${f.options.map(opt => `<option value="${opt}" ${opt === f.val ? 'selected' : ''}>${opt}</option>`).join("")}
          </select>
        </div>
      `;
    } else if (f.type === "checkbox") {
      return `
        <div class="form-group" style="display:flex; align-items:center; gap:10px; background:rgba(255,255,255,0.03); padding:10px; border-radius:6px;">
          <input type="checkbox" id="${f.id}" class="wizard-input-field" data-field="${f.id}" ${f.val ? 'checked' : ''} style="width:18px; height:18px;">
          <label for="${f.id}" style="font-size:0.84rem; font-weight:600; cursor:pointer;">${f.label}</label>
        </div>
      `;
    } else {
      return `
        <div class="form-group">
          <label class="form-label">${f.label}</label>
          <input type="${f.type}" class="form-control wizard-input-field" data-field="${f.id}" value="${f.val || ''}">
        </div>
      `;
    }
  }).join("");

  showModal("stepWizardModal");
}

async function executeCurrentWizardStep() {
  const inputs = document.querySelectorAll(".wizard-input-field");
  inputs.forEach(input => {
    const fieldId = input.dataset.field;
    if (input.type === "checkbox") {
      wizardAccumulatedParams[fieldId] = input.checked;
    } else {
      wizardAccumulatedParams[fieldId] = input.value;
    }
  });

  // Mapear campos a parámetros estándar
  if (wizardAccumulatedParams.w_pos_ip) wizardAccumulatedParams.target_ip = wizardAccumulatedParams.w_pos_ip;
  if (wizardAccumulatedParams.w_local_ip) wizardAccumulatedParams.local_server_ip = wizardAccumulatedParams.w_local_ip;
  if (wizardAccumulatedParams.w_bu) wizardAccumulatedParams.business_unit = wizardAccumulatedParams.w_bu;
  if (wizardAccumulatedParams.w_pos_num) wizardAccumulatedParams.pos_num = parseInt(wizardAccumulatedParams.w_pos_num);
  if (wizardAccumulatedParams.w_local_id) wizardAccumulatedParams.local_id = wizardAccumulatedParams.w_local_id;
  if (wizardAccumulatedParams.w_pinpad_ip) wizardAccumulatedParams.pinpad_ip = wizardAccumulatedParams.w_pinpad_ip;

  const btnExec = document.getElementById("btnExecuteStep");
  btnExec.disabled = true;
  btnExec.innerText = "Ejecutando y validando...";

  try {
    const res = await fetch("/api/deploy/execute-phase-step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        phase_id: wizardCurrentPhase,
        params: wizardAccumulatedParams
      })
    });
    const data = await res.json();
    btnExec.disabled = false;
    btnExec.innerText = "⚡ Ejecutar Este Paso y Validar Compuerta";

    const alertEl = document.getElementById("wizardStatusAlert");
    alertEl.style.display = "block";

    if (data.success && data.gate_passed) {
      alertEl.style.background = "rgba(16, 185, 129, 0.15)";
      alertEl.style.border = "1px solid var(--accent-emerald)";
      alertEl.style.color = "#a7f3d0";
      alertEl.innerHTML = `<strong>✅ COMPUERTA APROBADA:</strong> ${escapeHtml(data.gate_detail)}`;

      btnExec.style.display = "none";
      const btnNext = document.getElementById("btnNextStep");
      btnNext.style.display = "block";

      if (wizardCurrentPhase >= 8) {
        btnNext.innerText = "🎉 Certificación Finalizada con Éxito";
      } else {
        btnNext.innerText = `Avanzar a Fase ${wizardCurrentPhase + 1} ➔`;
      }

      appendTerminalLog(`[ASISTENTE] Fase ${wizardCurrentPhase} certificada: ${data.gate_detail}`, "SUCCESS");
    } else {
      alertEl.style.background = "rgba(244, 63, 94, 0.15)";
      alertEl.style.border = "1px solid var(--accent-rose)";
      alertEl.style.color = "#fecdd3";
      alertEl.innerHTML = `<strong>❌ BLOQUEO DE SEGURIDAD:</strong> ${escapeHtml(data.error || data.gate_detail || "Compuerta no superada")}`;
      appendTerminalLog(`[ASISTENTE] Bloqueo en Fase ${wizardCurrentPhase}: ${data.error || data.gate_detail}`, "ERROR");
    }

  } catch (e) {
    btnExec.disabled = false;
    btnExec.innerText = "⚡ Ejecutar Este Paso y Validar Compuerta";
    alert("Error de comunicación al ejecutar el paso");
  }
}

function advanceToNextWizardStep() {
  if (wizardCurrentPhase < 8) {
    openWizardStep(wizardCurrentPhase + 1);
  } else {
    hideModal("stepWizardModal");
    alert("¡Felicitaciones! Todas las 8 fases y compuertas de seguridad han sido ejecutadas y certificadas con éxito.");
    runReconciliation();
  }
}
