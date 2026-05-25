/**
 * Layout Shell for Admin Dashboard
 * Handles sidebar rendering, state, and toast notifications.
 */

// Toast System
function showToast(message, type = 'success') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  
  const icon = type === 'success' 
    ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 6L9 17l-5-5"/></svg>'
    : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
    
  toast.innerHTML = `${icon} <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('fade-out');
    toast.addEventListener('animationend', () => toast.remove());
  }, 3000);
}

// Sidebar System
function renderSidebar() {
  const isCollapsed = localStorage.getItem('sidebar_collapsed') === 'true';
  const currentPath = window.location.pathname;

  const sidebarHtml = `
    <aside class="sidebar ${isCollapsed ? 'collapsed' : ''}" id="sidebar">
      <div class="sidebar-brand">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
          <polyline points="2 17 12 22 22 17"></polyline>
          <polyline points="2 12 12 17 22 12"></polyline>
        </svg>
        <span>Job Agent</span>
      </div>
      
      <nav class="sidebar-nav">
        <a href="/admin" class="sidebar-item ${currentPath === '/admin' ? 'active' : ''}">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
          <span>Dashboard</span>
        </a>
        <a href="/admin/roles" class="sidebar-item ${currentPath.startsWith('/admin/role') && currentPath !== '/admin/add-role' ? 'active' : ''}">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
          <span>Pipeline</span>
        </a>
        <a href="/admin/add-role" class="sidebar-item ${currentPath === '/admin/add-role' ? 'active' : ''}">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
          <span>Add Role</span>
        </a>
      </nav>
      
      <div class="sidebar-bottom">
        <button class="toggle-sidebar" id="toggle-sidebar-btn">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"></polyline></svg>
          <span>Collapse</span>
        </button>
        <button class="toggle-sidebar mt-4" onclick="logout()" style="color: var(--status-error);">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
          <span>Logout</span>
        </button>
      </div>
    </aside>
  `;

  // Insert sidebar at start of body
  const shell = document.createElement('div');
  shell.className = 'admin-shell';
  
  // Wrap existing content in admin-main
  const main = document.createElement('main');
  main.className = 'admin-main';
  while (document.body.firstChild) {
    main.appendChild(document.body.firstChild);
  }
  
  shell.innerHTML = sidebarHtml;
  shell.appendChild(main);
  document.body.appendChild(shell);

  // Setup toggle listener
  const toggleBtn = document.getElementById('toggle-sidebar-btn');
  const sidebar = document.getElementById('sidebar');
  const toggleIcon = toggleBtn.querySelector('svg');

  function updateToggleIcon(collapsed) {
    toggleIcon.innerHTML = collapsed 
      ? '<polyline points="9 18 15 12 9 6"></polyline>'
      : '<polyline points="15 18 9 12 15 6"></polyline>';
  }
  
  updateToggleIcon(isCollapsed);

  toggleBtn.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    const isNowCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebar_collapsed', isNowCollapsed);
    updateToggleIcon(isNowCollapsed);
  });
}

// Make globally available
window.showToast = showToast;
window.renderSidebar = renderSidebar;
