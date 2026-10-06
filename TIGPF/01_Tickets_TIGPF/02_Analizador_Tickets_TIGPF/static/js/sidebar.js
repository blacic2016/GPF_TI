/* --------------------------------------------------------------------------
   SIDEBAR NAVIGATION SYSTEM - SIDEBAR.JS
   Corporación GPF | Dashboard Analítico de Tickets TI_GPF
   -------------------------------------------------------------------------- */

(function() {
  function initSidebar() {
    const btnToggle = document.getElementById('btn-toggle-menu');
    const btnClose = document.getElementById('btn-close-sidebar');
    const sidebar = document.getElementById('main-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const body = document.body;

    if (!sidebar) return;

    // Check saved state or default to open on desktop, collapsed on mobile
    const isMobile = window.innerWidth <= 1024;
    const savedState = localStorage.getItem('tigpf_sidebar_state');

    if (savedState === 'collapsed' || (isMobile && savedState !== 'open')) {
      body.classList.add('sidebar-collapsed');
    } else {
      body.classList.remove('sidebar-collapsed');
    }

    function toggleSidebar() {
      body.classList.toggle('sidebar-collapsed');
      const isCollapsed = body.classList.contains('sidebar-collapsed');
      localStorage.setItem('tigpf_sidebar_state', isCollapsed ? 'collapsed' : 'open');
      
      // Trigger window resize so Chart.js charts automatically resize smoothly to the new container width
      setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
      }, 310);
    }

    function closeSidebar() {
      body.classList.add('sidebar-collapsed');
      localStorage.setItem('tigpf_sidebar_state', 'collapsed');
      setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
      }, 310);
    }

    if (btnToggle) {
      btnToggle.addEventListener('click', (e) => {
        e.preventDefault();
        toggleSidebar();
      });
    }

    if (btnClose) {
      btnClose.addEventListener('click', (e) => {
        e.preventDefault();
        closeSidebar();
      });
    }

    if (overlay) {
      overlay.addEventListener('click', closeSidebar);
    }

    // Keyboard shortcut: Escape closes sidebar
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !body.classList.contains('sidebar-collapsed')) {
        closeSidebar();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSidebar);
  } else {
    initSidebar();
  }
})();
