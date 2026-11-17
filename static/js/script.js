/**
 * City Library Management System - Interactive Enhancements
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. Initialize Theme (Light / Dark Mode)
    initTheme();

    // 2. Auto-dismiss alerts after 5 seconds
    initAlerts();

    // 3. Quick Table Filters (if present)
    initTableFilters();

    // 4. Password Read / Visibility Toggle
    initPasswordToggles();
});

// Theme Management
function initTheme() {
    const savedTheme = localStorage.getItem('library_theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    const themeToggleBtn = document.getElementById('themeToggleBtn');
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', function () {
            const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('library_theme', newTheme);
            updateThemeIcon(newTheme);
        });
    }
}

function updateThemeIcon(theme) {
    const icon = document.getElementById('themeToggleIcon');
    if (!icon) return;
    if (theme === 'dark') {
        icon.className = 'fas fa-sun text-warning';
    } else {
        icon.className = 'fas fa-moon text-secondary';
    }
}

// Auto-dismiss Bootstrap Alerts
function initAlerts() {
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            if (window.bootstrap && bootstrap.Alert) {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } else {
                alert.style.opacity = '0';
                setTimeout(() => alert.remove(), 400);
            }
        }, 5000);
    });
}

// Table Search Filtering
function initTableFilters() {
    const filterInputs = document.querySelectorAll('[data-table-filter]');
    filterInputs.forEach(input => {
        const targetTableSelector = input.getAttribute('data-table-filter');
        const targetTable = document.querySelector(targetTableSelector);
        if (!targetTable) return;

        input.addEventListener('keyup', function () {
            const query = input.value.toLowerCase();
            const rows = targetTable.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const text = row.innerText.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });
    });
}

// Password Read / Visibility Toggle
function initPasswordToggles() {
    document.querySelectorAll('.toggle-password-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const targetSelector = this.getAttribute('data-target');
            const targetInput = document.querySelector(targetSelector);
            if (!targetInput) return;

            const icon = this.querySelector('i');
            if (targetInput.type === 'password') {
                targetInput.type = 'text';
                if (icon) {
                    icon.classList.remove('fa-eye');
                    icon.classList.add('fa-eye-slash');
                }
                this.setAttribute('title', 'Hide password');
            } else {
                targetInput.type = 'password';
                if (icon) {
                    icon.classList.remove('fa-eye-slash');
                    icon.classList.add('fa-eye');
                }
                this.setAttribute('title', 'Show password');
            }
        });
    });
}

// Tab Switcher for Metric Cards
function switchAdminTab(tabId, filterKeyword = '') {
    const tabButton = document.querySelector(`[data-bs-target="#${tabId}"]`);
    if (tabButton && window.bootstrap) {
        const tab = new bootstrap.Tab(tabButton);
        tab.show();
        
        if (filterKeyword) {
            const filterInput = document.querySelector(`#${tabId} [data-table-filter]`);
            if (filterInput) {
                filterInput.value = filterKeyword;
                filterInput.dispatchEvent(new Event('keyup'));
            }
        }
        
        tabButton.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// Toast notification helper
function showToast(message, type = 'info') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.style.position = 'fixed';
        container.style.bottom = '24px';
        container.style.right = '24px';
        container.style.zIndex = '9999';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '10px';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const bgClass = type === 'success' ? '#2e7d32' : (type === 'error' ? '#b71c1c' : '#650018');
    toast.style.background = bgClass;
    toast.style.color = '#E8CDB0';
    toast.style.border = '1px solid rgba(232, 205, 176, 0.4)';
    toast.style.padding = '12px 20px';
    toast.style.borderRadius = '10px';
    toast.style.boxShadow = '0 10px 25px rgba(0,0,0,0.2)';
    toast.style.fontWeight = '600';
    toast.style.fontSize = '0.9rem';
    toast.style.display = 'flex';
    toast.style.alignItems = 'center';
    toast.style.gap = '10px';
    toast.style.transition = 'all 0.3s ease';
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(15px)';

    const icon = type === 'success' ? 'fa-check-circle' : (type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle');
    toast.innerHTML = `<i class="fas ${icon}"></i> <span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0)';
    }, 10);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Copy link or Web Share
function shareBook(title, author) {
    if (navigator.share) {
        navigator.share({
            title: title,
            text: `Check out "${title}" by ${author} at City Library!`,
            url: window.location.href
        }).catch(() => {});
    } else {
        navigator.clipboard.writeText(window.location.href).then(() => {
            showToast('Book link copied to clipboard!', 'success');
        });
    }
}
