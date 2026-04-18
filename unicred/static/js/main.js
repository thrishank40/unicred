/**
 * UniCred — Campus Digital Economy Platform
 * main.js  ·  Frontend Interaction Layer
 * ES6 · Modular · Bootstrap 5 Compatible
 */

'use strict';

/* ─────────────────────────────────────────
   0. Utility Helpers
───────────────────────────────────────── */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

const debounce = (fn, delay = 300) => {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
};

const formatCredits = (n) => {
  n = Number(n);
  if (isNaN(n)) return '0';
  return n.toLocaleString('en-IN');
};

/* ─────────────────────────────────────────
   1. Initialise on DOM Ready
───────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initNavbar();
  initFlashMessages();
  initPasswordToggles();
  initButtonLoadingStates();
  initFormValidation();
  initSmoothScroll();
  initTooltips();
  initNotifications();
  initFilterChips();
  initStarRatings();
  initScannerUI();
  initCounterAnimation();
  initSearchDebounce();
  initCreditProgressBars();
  initScrollReveal();
  initTableRowLinks();
  initCopyToClipboard();
  createToastContainer();
});

/* ─────────────────────────────────────────
   2. Navbar: Scroll & Mobile Behaviour
───────────────────────────────────────── */
function initNavbar() {
  const nav = $('#mainNav');
  if (!nav) return;

  // Add scrolled class for shadow on scroll
  const onScroll = () => {
    nav.classList.toggle('scrolled', window.scrollY > 10);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll(); // run on init in case page loaded mid-scroll

  // Close mobile menu when a nav-link is clicked
  const toggler = nav.querySelector('.navbar-toggler');
  const collapse = nav.querySelector('.navbar-collapse');
  if (toggler && collapse) {
    $$('.nav-link', collapse).forEach(link => {
      link.addEventListener('click', () => {
        const bsCollapse = bootstrap.Collapse.getInstance(collapse);
        if (bsCollapse) bsCollapse.hide();
      });
    });
  }

  // Highlight current nav link based on href
  highlightActiveNavLink();
}

function highlightActiveNavLink() {
  const path = window.location.pathname;
  $$('#mainNav .nav-link').forEach(link => {
    const href = link.getAttribute('href');
    if (href && href !== '/' && path.startsWith(href)) {
      link.classList.add('active');
    }
  });
}

/* ─────────────────────────────────────────
   3. Flash / Alert Auto-Dismiss
───────────────────────────────────────── */
function initFlashMessages() {
  const container = $('.flash-container');
  if (!container) return;

  const alerts = $$('.alert', container);
  alerts.forEach((alert, i) => {
    // Stagger entrance animation
    alert.style.animationDelay = `${i * 80}ms`;

    // Auto-dismiss non-error alerts after 5 s
    if (!alert.classList.contains('alert-danger')) {
      setTimeout(() => dismissAlert(alert), 5000 + i * 200);
    }
  });
}

function dismissAlert(alertEl) {
  if (!alertEl || !alertEl.parentElement) return;
  alertEl.style.transition = 'opacity .35s ease, transform .35s ease, max-height .35s ease, padding .35s ease, margin .35s ease';
  alertEl.style.opacity = '0';
  alertEl.style.transform = 'translateY(-6px)';
  alertEl.style.maxHeight = '0';
  alertEl.style.paddingTop = '0';
  alertEl.style.paddingBottom = '0';
  alertEl.style.marginBottom = '0';
  setTimeout(() => alertEl.remove(), 380);
}

/* ─────────────────────────────────────────
   4. Password Visibility Toggle
───────────────────────────────────────── */
function initPasswordToggles() {
  $$('.btn-password-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.dataset.target || findPasswordInput(btn)?.id;
      if (!targetId) return;
      togglePassword(targetId);
    });
  });
}

function findPasswordInput(toggleBtn) {
  const wrapper = toggleBtn.closest('.form-floating, .input-group, .position-relative');
  return wrapper ? wrapper.querySelector('input[type="password"], input[type="text"]') : null;
}

// Global helper (also called from inline template scripts)
window.togglePassword = function (inputId) {
  const input = document.getElementById(inputId);
  const eye = document.getElementById(inputId + 'Eye');
  if (!input) return;
  const isHidden = input.type === 'password';
  input.type = isHidden ? 'text' : 'password';
  if (eye) eye.className = isHidden ? 'bi bi-eye-slash' : 'bi bi-eye';
};

/* ─────────────────────────────────────────
   5. Button Loading / Submit State
───────────────────────────────────────── */
function initButtonLoadingStates() {
  // Hook all forms that have a submit button with a .btn-text / spinner pattern
  $$('form[data-loading]').forEach(form => {
    form.addEventListener('submit', () => {
      const btn = form.querySelector('[type="submit"]');
      if (btn) setButtonLoading(btn, true);
    });
  });

  // Also handle any form with id="*Form" and a matching submit button
  $$('form[id$="Form"]').forEach(form => {
    form.addEventListener('submit', (e) => {
      if (form.checkValidity()) {
        const btn = form.querySelector('[type="submit"]');
        if (btn) setButtonLoading(btn, true);
      }
    });
  });
}

function setButtonLoading(btn, isLoading) {
  const textEl = btn.querySelector('.btn-text');
  const spinnerEl = btn.querySelector('.spinner-border');
  if (isLoading) {
    btn.disabled = true;
    if (textEl) textEl.classList.add('d-none');
    if (spinnerEl) spinnerEl.classList.remove('d-none');
  } else {
    btn.disabled = false;
    if (textEl) textEl.classList.remove('d-none');
    if (spinnerEl) spinnerEl.classList.add('d-none');
  }
}

/* ─────────────────────────────────────────
   6. Client-Side Form Validation Helpers
───────────────────────────────────────── */
function initFormValidation() {
  // Bootstrap's native validation UI
  $$('form.needs-validation').forEach(form => {
    form.addEventListener('submit', (e) => {
      if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
      }
      form.classList.add('was-validated');
    });
  });

  // Password confirmation matcher
  const confirmPw = $('#confirm_password, #confirmPassword');
  const pw = $('#password');
  if (confirmPw && pw) {
    const check = () => {
      if (confirmPw.value && pw.value !== confirmPw.value) {
        confirmPw.setCustomValidity('Passwords do not match');
        confirmPw.classList.add('is-invalid');
      } else {
        confirmPw.setCustomValidity('');
        confirmPw.classList.remove('is-invalid');
      }
    };
    confirmPw.addEventListener('input', check);
    pw.addEventListener('input', check);
  }

  // Email format hint: uni / college email
  const emailInput = $('input[type="email"]#email');
  if (emailInput) {
    emailInput.addEventListener('blur', () => {
      const val = emailInput.value.trim();
      const hasEduDomain = /\.(edu|ac\.[a-z]{2,}|edu\.[a-z]{2,})$/i.test(val);
      const hint = emailInput.nextElementSibling?.classList?.contains('email-hint')
        ? emailInput.nextElementSibling
        : null;
      // Only show hint on register page
      if (!hasEduDomain && val && $('#registerForm')) {
        if (!hint) {
          const p = document.createElement('p');
          p.className = 'email-hint text-warning small mt-1';
          p.innerHTML = '<i class="bi bi-info-circle me-1"></i>Use your institutional (.edu / .ac.in) email for campus access.';
          emailInput.insertAdjacentElement('afterend', p);
        }
      } else {
        if (hint) hint.remove();
      }
    });
  }

  // Credit amount: don't allow negative
  $$('input[name="credits"], input[name="credit_cost"]').forEach(inp => {
    inp.addEventListener('input', () => {
      if (parseInt(inp.value) < 0) inp.value = 0;
    });
  });
}

/* ─────────────────────────────────────────
   7. Smooth Scroll (anchor links)
───────────────────────────────────────── */
function initSmoothScroll() {
  $$('a[href^="#"]').forEach(a => {
    a.addEventListener('click', (e) => {
      const id = a.getAttribute('href').slice(1);
      if (!id) return;
      const target = document.getElementById(id);
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
}

/* ─────────────────────────────────────────
   8. Bootstrap Tooltips
───────────────────────────────────────── */
function initTooltips() {
  if (typeof bootstrap === 'undefined') return;
  $$('[data-bs-toggle="tooltip"]').forEach(el => {
    new bootstrap.Tooltip(el, { trigger: 'hover' });
  });
}

/* ─────────────────────────────────────────
   9. Notification System
───────────────────────────────────────── */
let _notifPollingId = null;

function initNotifications() {
  const notifCount = $('#notifCount');
  const notifList = $('#notifList');
  if (!notifCount || !notifList) return;

  fetchNotifications();

  // Poll every 30 s
  _notifPollingId = setInterval(fetchNotifications, 30000);

  // Mark all read
  const markAllBtn = $('#markAllRead');
  if (markAllBtn) {
    markAllBtn.addEventListener('click', (e) => {
      e.preventDefault();
      markAllNotificationsRead();
    });
  }
}

async function fetchNotifications() {
  try {
    const res = await fetch('/api/notifications', {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    if (!res.ok) return;
    const data = await res.json();
    renderNotifications(data);
  } catch (_) {
    // Silently fail — network issues shouldn't break the page
  }
}

function renderNotifications(data) {
  const notifCount = $('#notifCount');
  const notifList = $('#notifList');
  if (!notifCount || !notifList) return;

  const notifications = Array.isArray(data) ? data : (data.notifications || []);
  const unreadCount = notifications.filter(n => !n.is_read).length;

  // Badge
  if (unreadCount > 0) {
    notifCount.textContent = unreadCount > 99 ? '99+' : unreadCount;
    notifCount.style.display = 'flex';
  } else {
    notifCount.style.display = 'none';
  }

  // List
  if (notifications.length === 0) {
    notifList.innerHTML = `
      <div class="notif-empty">
        <i class="bi bi-bell-slash fs-2 d-block mb-2 text-muted"></i>
        No notifications yet
      </div>`;
    return;
  }

  notifList.innerHTML = notifications.map(n => `
    <div class="notif-item ${n.is_read ? '' : 'unread'}" data-id="${n.id}">
      <div class="notif-icon">
        <i class="bi ${getNotifIcon(n.type)}"></i>
      </div>
      <div class="flex-1">
        <div class="notif-text">${escapeHtml(n.message)}</div>
        <div class="notif-time">${formatRelativeTime(n.created_at)}</div>
      </div>
    </div>
  `).join('');

  // Click individual notification to mark read
  $$('.notif-item', notifList).forEach(item => {
    item.addEventListener('click', () => {
      const id = item.dataset.id;
      if (id && !item.classList.contains('read')) {
        markNotificationRead(id);
        item.classList.remove('unread');
        item.classList.add('read');
        updateBadgeCount(-1);
      }
    });
  });
}

function getNotifIcon(type) {
  const map = {
    borrow_request: 'bi-inbox',
    approved: 'bi-check-circle',
    returned: 'bi-arrow-counterclockwise',
    overdue: 'bi-exclamation-triangle',
    rating: 'bi-star',
    credit: 'bi-coin',
    system: 'bi-bell',
  };
  return map[type] || 'bi-bell';
}

async function markNotificationRead(id) {
  try {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    await fetch(`/api/notifications/${id}/read`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfToken }
    });
  } catch (_) { }
}

async function markAllNotificationsRead() {
  try {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    await fetch('/api/notifications/read-all', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfToken }
    });
    $$('.notif-item.unread').forEach(el => {
      el.classList.remove('unread');
    });
    const notifCount = $('#notifCount');
    if (notifCount) notifCount.style.display = 'none';
  } catch (_) { }
}

function updateBadgeCount(delta) {
  const notifCount = $('#notifCount');
  if (!notifCount) return;
  const current = parseInt(notifCount.textContent) || 0;
  const next = Math.max(0, current + delta);
  if (next === 0) {
    notifCount.style.display = 'none';
  } else {
    notifCount.textContent = next;
  }
}

/* ─────────────────────────────────────────
   10. Filter Chips (Resources / Search)
───────────────────────────────────────── */
function initFilterChips() {
  $$('.filter-chips').forEach(container => {
    const chips = $$('.filter-chip', container);
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        const exclusive = container.dataset.exclusive !== 'false';
        if (exclusive) chips.forEach(c => c.classList.remove('active'));
        chip.classList.toggle('active', exclusive ? true : !chip.classList.contains('active'));

        // Dispatch custom event for any page-specific handling
        container.dispatchEvent(new CustomEvent('filter-change', {
          detail: { active: $$('.filter-chip.active', container).map(c => c.dataset.value) }
        }));
      });
    });
  });
}

/* ─────────────────────────────────────────
   11. Star Rating Input
───────────────────────────────────────── */
function initStarRatings() {
  $$('.star-rating[data-interactive]').forEach(container => {
    const stars = $$('.star', container);
    const input = document.getElementById(container.dataset.input);
    let current = parseInt(container.dataset.value) || 0;

    function setStars(val) {
      stars.forEach((s, i) => s.classList.toggle('filled', i < val));
    }

    setStars(current);

    stars.forEach((star, i) => {
      star.addEventListener('mouseenter', () => setStars(i + 1));
      star.addEventListener('mouseleave', () => setStars(current));
      star.addEventListener('click', () => {
        current = i + 1;
        setStars(current);
        if (input) input.value = current;
        container.dataset.value = current;
      });
    });
  });
}

/* ─────────────────────────────────────────
   12. QR Scanner UI
───────────────────────────────────────── */
function initScannerUI() {
  const scanArea = $('.qr-scanner-area');
  if (!scanArea) return;

  // Inject scan line if not present
  if (!scanArea.querySelector('.qr-scanner-line')) {
    const line = document.createElement('div');
    line.className = 'qr-scanner-line';
    scanArea.appendChild(line);
  }

  // Handle scanner status messages
  const statusEl = $('#scanStatus');
  if (statusEl) {
    const states = {
      idle: { icon: 'bi-qr-code-scan', text: 'Point camera at a QR code', cls: 'text-muted' },
      scanning: { icon: 'bi-camera', text: 'Scanning…', cls: 'text-primary' },
      success: { icon: 'bi-check-circle', text: 'QR Verified!', cls: 'text-success' },
      error: { icon: 'bi-x-circle', text: 'Invalid QR code', cls: 'text-danger' },
    };

    window.setScanStatus = (state) => {
      const s = states[state] || states.idle;
      statusEl.innerHTML = `<i class="bi ${s.icon} me-2"></i>${s.text}`;
      statusEl.className = `scan-status mt-3 text-center fw-600 ${s.cls}`;
    };
  }
}

/* ─────────────────────────────────────────
   13. Counter Animation (Stats)
───────────────────────────────────────── */
function initCounterAnimation() {
  const counters = $$('[data-count]');
  if (!counters.length) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateCounter(entry.target);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  counters.forEach(el => observer.observe(el));
}

function animateCounter(el) {
  const target = parseInt(el.dataset.count) || 0;
  const suffix = el.dataset.suffix || '';
  const duration = 1200;
  const start = performance.now();

  const update = (now) => {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    el.textContent = formatCredits(Math.round(eased * target)) + suffix;
    if (progress < 1) requestAnimationFrame(update);
  };
  requestAnimationFrame(update);
}

/* Animate stat-num elements on index page */
function initStatNumbers() {
  $$('.stat-num').forEach(el => {
    const text = el.textContent.trim();
    const match = text.match(/^([\d,]+)(.*)/);
    if (!match) return;
    const num = parseInt(match[1].replace(/,/g, ''));
    const suffix = match[2] || '';
    el.dataset.count = num;
    el.dataset.suffix = suffix;
  });
  initCounterAnimation();
}

/* ─────────────────────────────────────────
   14. Debounced Search / Filter
───────────────────────────────────────── */
function initSearchDebounce() {
  const searchInput = $('#resourceSearch, #searchInput, input[name="q"]');
  if (!searchInput) return;

  const debouncedSearch = debounce((val) => {
    const rows = $$('[data-searchable]');
    const q = val.toLowerCase();
    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = (!q || text.includes(q)) ? '' : 'none';
    });
    updateEmptyState(rows);
  }, 250);

  searchInput.addEventListener('input', (e) => debouncedSearch(e.target.value));
}

function updateEmptyState(rows) {
  // If all rows are hidden, show an empty-state message
  const container = $('.search-empty-state');
  if (!container) return;
  const visibleCount = rows.filter(r => r.style.display !== 'none').length;
  container.style.display = visibleCount === 0 ? 'block' : 'none';
}

/* ─────────────────────────────────────────
   15. Credit Progress Bars
───────────────────────────────────────── */
function initCreditProgressBars() {
  $$('.credit-progress-bar[data-width]').forEach(bar => {
    const width = parseFloat(bar.dataset.width);
    // Animate on mount
    requestAnimationFrame(() => {
      bar.style.width = Math.min(100, Math.max(0, width)) + '%';
    });
  });
}

/* ─────────────────────────────────────────
   16. Scroll Reveal (Cards / Sections)
───────────────────────────────────────── */
function initScrollReveal() {
  const targets = $$('.feature-card, .stat-card, .resource-card, .knowledge-card, .leaderboard-row');
  if (!targets.length) return;

  targets.forEach((el, i) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = `opacity .45s ease ${(i % 4) * 60}ms, transform .45s ease ${(i % 4) * 60}ms`;
  });

  const revealObs = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
        revealObs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });

  targets.forEach(el => revealObs.observe(el));
}

/* ─────────────────────────────────────────
   17. Clickable Table Rows
───────────────────────────────────────── */
function initTableRowLinks() {
  $$('tr[data-href]').forEach(row => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', (e) => {
      // Don't navigate if clicking an actual link / button inside the row
      if (e.target.closest('a, button, .dropdown')) return;
      window.location.href = row.dataset.href;
    });
  });
}

/* ─────────────────────────────────────────
   18. Copy to Clipboard
───────────────────────────────────────── */
function initCopyToClipboard() {
  $$('[data-copy]').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.copy || btn.dataset.value;
      if (!text) return;
      navigator.clipboard.writeText(text).then(() => {
        const original = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check2 me-1"></i>Copied!';
        btn.classList.add('btn-success');
        setTimeout(() => {
          btn.innerHTML = original;
          btn.classList.remove('btn-success');
        }, 1800);
      }).catch(() => showToast('Could not copy to clipboard', 'error'));
    });
  });
}

/* ─────────────────────────────────────────
   19. Toast / Snackbar System
───────────────────────────────────────── */
let _toastContainer = null;

function createToastContainer() {
  if (_toastContainer) return;
  _toastContainer = document.createElement('div');
  _toastContainer.className = 'uc-toast-container';
  document.body.appendChild(_toastContainer);
}

const TOAST_ICONS = {
  success: 'bi-check-circle-fill text-success',
  error: 'bi-x-circle-fill text-danger',
  info: 'bi-info-circle-fill text-primary',
  warning: 'bi-exclamation-triangle-fill text-warning',
};

window.showToast = function (message, type = 'info', duration = 3500) {
  if (!_toastContainer) createToastContainer();

  const toast = document.createElement('div');
  toast.className = `uc-toast ${type}`;
  toast.innerHTML = `
    <i class="bi ${TOAST_ICONS[type] || TOAST_ICONS.info} uc-toast-icon"></i>
    <span>${escapeHtml(message)}</span>
  `;
  _toastContainer.appendChild(toast);

  // Auto-remove
  setTimeout(() => {
    toast.classList.add('exiting');
    setTimeout(() => toast.remove(), 320);
  }, duration);
};

/* ─────────────────────────────────────────
   20. Page-Specific Initialisers
───────────────────────────────────────── */

// Index / Landing page
(function indexPage() {
  if (!$('.hero-section')) return;
  initStatNumbers(); // Re-run counter for .stat-num elements

  // CTA button pulse on hover
  const cta = $('.hero-cta');
  if (cta) {
    cta.addEventListener('mouseenter', () => cta.style.boxShadow = '0 12px 35px rgba(59,130,246,.4)');
    cta.addEventListener('mouseleave', () => cta.style.boxShadow = '');
  }
})();

// Dashboard page
(function dashboardPage() {
  const creditDisplay = $('.credit-display');
  if (!creditDisplay) return;

  // Animate credit number
  const val = parseInt(creditDisplay.textContent.replace(/,/g, '')) || 0;
  creditDisplay.dataset.count = val;
  creditDisplay.dataset.suffix = '';

  // Charts: only initialise if Chart.js is loaded
  if (typeof Chart !== 'undefined') {
    initDashboardCharts();
  }
})();

function initDashboardCharts() {
  // Activity Chart (if canvas exists)
  const ctx = document.getElementById('activityChart');
  if (ctx) {
    new Chart(ctx, {
      type: 'line',
      data: {
        labels: ctx.dataset.labels ? JSON.parse(ctx.dataset.labels) : [],
        datasets: [{
          label: 'Credits',
          data: ctx.dataset.values ? JSON.parse(ctx.dataset.values) : [],
          borderColor: '#3B82F6',
          backgroundColor: 'rgba(59,130,246,.1)',
          fill: true,
          tension: .4,
          pointBackgroundColor: '#3B82F6',
          pointRadius: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, grid: { color: '#F1F5F9' } }
        }
      }
    });
  }

  // Category doughnut chart
  const ctxCat = document.getElementById('categoryChart');
  if (ctxCat) {
    const colors = ['#3B82F6', '#6366F1', '#22C55E', '#F59E0B', '#EF4444', '#8B5CF6'];
    new Chart(ctxCat, {
      type: 'doughnut',
      data: {
        labels: ctxCat.dataset.labels ? JSON.parse(ctxCat.dataset.labels) : [],
        datasets: [{
          data: ctxCat.dataset.values ? JSON.parse(ctxCat.dataset.values) : [],
          backgroundColor: colors,
          borderWidth: 2,
          borderColor: '#fff',
        }]
      },
      options: {
        cutout: '70%',
        plugins: { legend: { position: 'bottom', labels: { font: { size: 12 } } } }
      }
    });
  }
}

// Admin Dashboard
(function adminPage() {
  if (!$('.admin-sidebar') && !$('[data-admin]')) return;

  if (typeof Chart !== 'undefined') {
    // Line chart: credit flow
    const flowCtx = document.getElementById('creditFlowChart');
    if (flowCtx) {
      new Chart(flowCtx, {
        type: 'bar',
        data: {
          labels: flowCtx.dataset.labels ? JSON.parse(flowCtx.dataset.labels) : [],
          datasets: [
            {
              label: 'Credits Earned',
              data: flowCtx.dataset.earned ? JSON.parse(flowCtx.dataset.earned) : [],
              backgroundColor: 'rgba(59,130,246,.8)',
              borderRadius: 6,
            },
            {
              label: 'Credits Spent',
              data: flowCtx.dataset.spent ? JSON.parse(flowCtx.dataset.spent) : [],
              backgroundColor: 'rgba(239,68,68,.7)',
              borderRadius: 6,
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'top' } },
          scales: { y: { beginAtZero: true } }
        }
      });
    }
  }
})();

// Resource Listing: Category filter
(function resourcesPage() {
  const catSelect = $('#categoryFilter');
  if (!catSelect) return;

  catSelect.addEventListener('change', () => {
    const val = catSelect.value.toLowerCase();
    $$('[data-category]').forEach(card => {
      const match = !val || card.dataset.category.toLowerCase() === val;
      card.closest('.col, [class^="col-"]').style.display = match ? '' : 'none';
    });
  });
})();

/* ─────────────────────────────────────────
   21. Leaderboard Confetti (Top-3)
───────────────────────────────────────── */
(function leaderboardPage() {
  const topRow = $('.leaderboard-row.rank-1-row, .rank-1');
  if (!topRow) return;
  // Light confetti particles on the page if the current user is in top 3
  const currentUserTop = document.querySelector('.leaderboard-row.current-user .rank-badge.rank-1, .leaderboard-row.current-user .rank-badge.rank-2, .leaderboard-row.current-user .rank-badge.rank-3');
  if (currentUserTop) {
    spawnConfetti();
  }
})();

function spawnConfetti() {
  const colors = ['#3B82F6', '#6366F1', '#22C55E', '#F59E0B', '#8B5CF6', '#EF4444'];
  for (let i = 0; i < 48; i++) {
    const el = document.createElement('div');
    Object.assign(el.style, {
      position: 'fixed',
      width: '8px', height: '8px',
      borderRadius: Math.random() > .5 ? '50%' : '0',
      background: colors[Math.floor(Math.random() * colors.length)],
      left: Math.random() * 100 + 'vw',
      top: '-10px',
      opacity: '1',
      zIndex: '9999',
      transition: `top ${1.2 + Math.random()}s ease ${Math.random() * .4}s, opacity .4s ease ${1 + Math.random()}s`,
      transform: `rotate(${Math.random() * 360}deg)`,
    });
    document.body.appendChild(el);
    requestAnimationFrame(() => {
      el.style.top = (60 + Math.random() * 40) + 'vh';
      el.style.opacity = '0';
    });
    setTimeout(() => el.remove(), 2200);
  }
}

/* ─────────────────────────────────────────
   22. QR Code Page Actions
───────────────────────────────────────── */
(function qrPage() {
  const downloadBtn = $('#downloadQR');
  if (downloadBtn) {
    downloadBtn.addEventListener('click', () => {
      const img = $('#qrCodeImg');
      if (!img) return;
      const a = document.createElement('a');
      a.href = img.src;
      a.download = 'unicred-qr.png';
      a.click();
    });
  }
})();

/* ─────────────────────────────────────────
   23. Request / Transaction Actions
───────────────────────────────────────── */
(function transactionPage() {
  // Confirm before approve/reject/cancel
  $$('[data-confirm]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const msg = btn.dataset.confirm || 'Are you sure?';
      if (!confirm(msg)) e.preventDefault();
    });
  });
})();

/* ─────────────────────────────────────────
   24. Miscellaneous UI Helpers
───────────────────────────────────────── */

// Back button
$$('[data-back]').forEach(el => {
  el.addEventListener('click', () => history.back());
});

// Print button
$$('[data-print]').forEach(el => {
  el.addEventListener('click', () => window.print());
});

// Auto-expand textarea
$$('textarea[data-autoresize]').forEach(ta => {
  const resize = () => {
    ta.style.height = 'auto';
    ta.style.height = ta.scrollHeight + 'px';
  };
  ta.addEventListener('input', resize);
  resize();
});

// Input character count
$$('input[maxlength][data-counter], textarea[maxlength][data-counter]').forEach(inp => {
  const max = parseInt(inp.maxLength);
  const counterId = inp.dataset.counter;
  const counter = document.getElementById(counterId);
  if (!counter) return;
  counter.textContent = `0/${max}`;
  inp.addEventListener('input', () => {
    counter.textContent = `${inp.value.length}/${max}`;
    counter.style.color = inp.value.length >= max * .9 ? '#EF4444' : '';
  });
});

// Image preview before upload
$$('input[type="file"][data-preview]').forEach(inp => {
  inp.addEventListener('change', () => {
    const preview = document.getElementById(inp.dataset.preview);
    if (!preview) return;
    const file = inp.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => { preview.src = e.target.result; preview.style.display = 'block'; };
    reader.readAsDataURL(file);
  });
});

/* ─────────────────────────────────────────
   25. String / Date Utilities
───────────────────────────────────────── */
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatRelativeTime(dateStr) {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    const diffMs = Date.now() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d ago`;
    return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  } catch (_) {
    return dateStr;
  }
}

/* ─────────────────────────────────────────
   26. Keyboard Accessibility
───────────────────────────────────────── */
// Allow Enter to click elements with role="button" that aren't <button>
$$('[role="button"]:not(button)').forEach(el => {
  el.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      el.click();
    }
  });
});

// Focus ring: only show for keyboard navigation
document.addEventListener('mousedown', () => document.body.classList.add('using-mouse'));
document.addEventListener('keydown', (e) => {
  if (e.key === 'Tab') document.body.classList.remove('using-mouse');
});

/* ─────────────────────────────────────────
   27. Cleanup on beforeunload
───────────────────────────────────────── */
window.addEventListener('beforeunload', () => {
  if (_notifPollingId) clearInterval(_notifPollingId);
});

/* ─────────────────────────────────────────
   28. Expose Public API
───────────────────────────────────────── */
window.UniCred = {
  showToast,
  setButtonLoading,
  formatCredits,
  formatRelativeTime,
  escapeHtml,
  fetchNotifications,
  animateCounter,
};
