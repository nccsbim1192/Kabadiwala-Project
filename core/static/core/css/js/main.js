// Online Kawadiwala - Complete Main JavaScript File
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 Online Kawadiwala System Initialized Successfully!');
    
    // Initialize all system components
    initializeAlerts();
    initializeForms();
    initializePriceCalculator();
    initializeConfirmDialogs();
    initializeTooltips();
    addLoadingStates();
    
    // Initialize dashboard features if on dashboard page
    if (window.location.pathname.includes('dashboard') || window.location.pathname.includes('customer')) {
        initializeDashboardFeatures();
    }
});

// ==================== ALERT MANAGEMENT ====================
function initializeAlerts() {
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        // Auto-hide alerts after 5 seconds
        setTimeout(() => {
            if (typeof bootstrap !== 'undefined') {
                try {
                    const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                    if (bsAlert) {
                        bsAlert.close();
                    }
                } catch (error) {
                    console.log('Alert auto-hide error:', error);
                }
            }
        }, 5000);
    });
}

// ==================== FORM ENHANCEMENTS ====================
function initializeForms() {
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        // Form submission handling
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
                showToast('Please fill in all required fields correctly.', 'error');
            } else {
                // Show loading state on submit buttons
                const submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    showLoading(submitBtn);
                }
            }
            form.classList.add('was-validated');
        });
        
        // Real-time validation feedback
        const inputs = form.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            input.addEventListener('blur', function() {
                if (this.checkValidity()) {
                    this.classList.remove('is-invalid');
                    this.classList.add('is-valid');
                } else {
                    this.classList.remove('is-valid');
                    this.classList.add('is-invalid');
                }
            });
        });
    });
}

// ==================== PRICE CALCULATOR ====================
function initializePriceCalculator() {
    const categorySelect = document.getElementById('id_waste_category');
    const weightInput = document.getElementById('id_estimated_weight_kg');

    if (categorySelect && weightInput) {
        function calculatePrice() {
            const selectedOption = categorySelect.options[categorySelect.selectedIndex];
            const weight = weightInput.value;
            
            // Get or create price display
            let display = document.getElementById('estimated-price');
            if (!display) {
                display = document.createElement('div');
                display.id = 'estimated-price';
                display.className = 'alert alert-info mt-2';
                display.style.display = 'none';
                weightInput.parentNode.appendChild(display);
            }

            if (selectedOption && weight && weight > 0) {
                // Try to get rate from data attribute first
                let rate = selectedOption.dataset.rate;
                
                // If not found, try to extract from option text
                if (!rate) {
                    const categoryText = selectedOption.textContent;
                    const rateMatch = categoryText.match(/Rs\.(\d+(?:\.\d+)?)/);
                    if (rateMatch) {
                        rate = parseFloat(rateMatch[1]);
                    }
                }

                if (rate) {
                    const total = (parseFloat(rate) * parseFloat(weight)).toFixed(2);
                    display.innerHTML = `
                        <div class="d-flex align-items-center">
                            <i class="fas fa-calculator me-2 text-success"></i>
                            <div>
                                <strong class="text-success">Estimated Earnings: Rs. ${total}</strong>
                                <small class="d-block text-muted">Rate: Rs. ${rate}/kg × ${weight}kg</small>
                            </div>
                        </div>
                    `;
                    display.style.display = 'block';
                    display.className = 'alert alert-success mt-2';
                } else {
                    display.style.display = 'none';
                }
            } else {
                display.style.display = 'none';
            }
        }

        // Event listeners
        categorySelect.addEventListener('change', calculatePrice);
        weightInput.addEventListener('input', calculatePrice);
        
        // Load waste category rates from API
        loadWasteCategoryRates();
    }
}

// Load waste category rates from Django API
function loadWasteCategoryRates() {
    fetch('/api/waste-categories/')
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            const categorySelect = document.getElementById('id_waste_category');
            if (categorySelect) {
                Array.from(categorySelect.options).forEach(option => {
                    if (option.value) {
                        const category = data.find(cat => cat.id == option.value);
                        if (category) {
                            option.dataset.rate = category.rate_per_kg;
                            option.textContent = `${category.name} - Rs. ${category.rate_per_kg}/kg`;
                        }
                    }
                });
            }
        })
        .catch(error => {
            console.log('Error loading waste categories:', error);
            // Fallback: try to extract rates from existing option text
        });
}

// ==================== UI ENHANCEMENTS ====================
function initializeConfirmDialogs() {
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    confirmButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.dataset.confirm || 'Are you sure?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}

function initializeTooltips() {
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
}

function addLoadingStates() {
    const navLinks = document.querySelectorAll('.navbar-nav .nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', function() {
            if (this.href && !this.href.includes('#') && !this.href.includes('logout')) {
                showPageLoading();
            }
        });
    });
}

// ==================== LOADING UTILITIES ====================
function showLoading(element) {
    const originalText = element.innerHTML;
    element.setAttribute('data-original-text', originalText);
    element.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Processing...';
    element.disabled = true;
}

function hideLoading(element) {
    const originalText = element.getAttribute('data-original-text');
    if (originalText) {
        element.innerHTML = originalText;
        element.disabled = false;
    }
}

function showPageLoading() {
    // Remove existing overlay if present
    const existingOverlay = document.getElementById('page-loading');
    if (existingOverlay) {
        existingOverlay.remove();
    }

    // Create and show page loading overlay
    const loadingOverlay = document.createElement('div');
    loadingOverlay.id = 'page-loading';
    loadingOverlay.innerHTML = `
        <div class="d-flex justify-content-center align-items-center h-100">
            <div class="text-center text-white">
                <div class="spinner-border mb-3" style="width: 3rem; height: 3rem;" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <h5>Loading...</h5>
            </div>
        </div>
    `;
    loadingOverlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(53, 173, 85, 0.9);
        z-index: 9999;
        display: flex;
    `;
    document.body.appendChild(loadingOverlay);
    
    // Remove loading overlay after page loads or timeout
    window.addEventListener('load', function() {
        setTimeout(() => {
            const overlay = document.getElementById('page-loading');
            if (overlay) {
                overlay.remove();
            }
        }, 500);
    });
    
    // Fallback timeout
    setTimeout(() => {
        const overlay = document.getElementById('page-loading');
        if (overlay) {
            overlay.remove();
        }
    }, 3000);
}

// ==================== TOAST NOTIFICATIONS ====================
function showToast(message, type = 'success') {
    const toastContainer = getOrCreateToastContainer();
    const toastId = 'toast-' + Date.now();
    
    const toastElement = document.createElement('div');
    toastElement.id = toastId;
    toastElement.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0`;
    toastElement.setAttribute('role', 'alert');
    toastElement.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'} me-2"></i>
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    toastContainer.appendChild(toastElement);
    
    // Initialize and show toast
    if (typeof bootstrap !== 'undefined') {
        const toast = new bootstrap.Toast(toastElement, {
            autohide: true,
            delay: 5000
        });
        toast.show();
        
        // Remove toast element after it's hidden
        toastElement.addEventListener('hidden.bs.toast', function() {
            this.remove();
        });
    } else {
        // Fallback for when Bootstrap is not loaded
        setTimeout(() => {
            toastElement.style.opacity = '0';
            setTimeout(() => toastElement.remove(), 300);
        }, 5000);
    }
}

function getOrCreateToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
    }
    return container;
}

// ==================== DASHBOARD FEATURES ====================
function initializeDashboardFeatures() {
    // Auto-refresh dashboard data every 30 seconds
    if (window.location.pathname.includes('dashboard') || window.location.pathname.includes('customer')) {
        startDashboardAutoRefresh();
    }
    
    // Initialize charts if Chart.js is available
    if (typeof Chart !== 'undefined') {
        initializeDashboardCharts();
    } else {
        // Try to load Chart.js dynamically if chart elements exist
        if (document.querySelector('[id$="-chart"]')) {
            loadChartJS();
        }
    }
}

function startDashboardAutoRefresh() {
    setInterval(() => {
        // Only refresh if user is still on dashboard and tab is active
        if (!document.hidden && 
            (window.location.pathname.includes('dashboard') || window.location.pathname.includes('customer'))) {
            refreshDashboardStats();
        }
    }, 30000); // Refresh every 30 seconds
}

function refreshDashboardStats() {
    fetch(window.location.href, {
        headers: {
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.text())
    .then(html => {
        // Update only stat cards without full page reload
        const parser = new DOMParser();
        const newDoc = parser.parseFromString(html, 'text/html');
        
        const statCards = document.querySelectorAll('.card.bg-primary, .card.bg-success, .card.bg-info, .card.bg-warning');
        const newStatCards = newDoc.querySelectorAll('.card.bg-primary, .card.bg-success, .card.bg-info, .card.bg-warning');
        
        statCards.forEach((card, index) => {
            if (newStatCards[index]) {
                card.innerHTML = newStatCards[index].innerHTML;
            }
        });
    })
    .catch(error => {
        console.log('Error refreshing dashboard:', error);
    });
}

function loadChartJS() {
    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/chart.js';
    script.onload = initializeDashboardCharts;
    document.head.appendChild(script);
}

function initializeDashboardCharts() {
    if (typeof Chart === 'undefined') return;
    
    // Environmental Impact Doughnut Chart
    const impactCanvas = document.getElementById('impact-chart');
    if (impactCanvas) {
        const ctx = impactCanvas.getContext('2d');
        const impactData = JSON.parse(impactCanvas.dataset.impact || '{}');
        
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Trees Saved', 'CO2 Reduced (kg)', 'Water Saved (L)'],
                datasets: [{
                    data: [
                        parseFloat(impactData.trees_saved) || 0,
                        parseFloat(impactData.co2_reduced) || 0,
                        parseFloat(impactData.water_saved) || 0
                    ],
                    backgroundColor: [
                        'rgba(40, 167, 69, 0.8)',
                        'rgba(23, 162, 184, 0.8)',
                        'rgba(255, 193, 7, 0.8)'
                    ],
                    borderColor: [
                        'rgba(40, 167, 69, 1)',
                        'rgba(23, 162, 184, 1)',
                        'rgba(255, 193, 7, 1)'
                    ],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            usePointStyle: true
                        }
                    }
                }
            }
        });
    }
    
    // Monthly Pickup Trend Chart
    const trendCanvas = document.getElementById('trend-chart');
    if (trendCanvas) {
        const ctx = trendCanvas.getContext('2d');
        const trendData = JSON.parse(trendCanvas.dataset.trend || '[]');
        
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: trendData.map(item => item.month),
                datasets: [{
                    label: 'Pickups',
                    data: trendData.map(item => item.count),
                    borderColor: 'rgba(40, 167, 69, 1)',
                    backgroundColor: 'rgba(40, 167, 69, 0.1)',
                    borderWidth: 3,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
}

// ==================== UTILITY FUNCTIONS ====================
function formatCurrency(amount) {
    return `Rs. ${parseFloat(amount).toFixed(2)}`;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ==================== GLOBAL API ====================
// Export functions for global use
window.KawadiwalaSystem = {
    showToast: showToast,
    showLoading: showLoading,
    hideLoading: hideLoading,
    initializeDashboardCharts: initializeDashboardCharts,
    startDashboardAutoRefresh: startDashboardAutoRefresh,
    formatCurrency: formatCurrency
};

// ==================== ERROR HANDLING ====================
window.addEventListener('error', function(e) {
    console.error('JavaScript Error:', e.error);
});

// Handle unhandled promise rejections
window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled Promise Rejection:', e.reason);
});

console.log('💻 Online Kawadiwala System JavaScript Loaded Successfully!');

// Online Kawadiwala - Main JavaScript File
document.addEventListener('DOMContentLoaded', function() {
    console.log('✅ Online Kawadiwala System Loaded Successfully!');
    
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            if (typeof bootstrap !== 'undefined') {
                try {
                    const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                    if (bsAlert) {
                        bsAlert.close();
                    }
                } catch (error) {
                    console.log('Alert auto-hide error:', error);
                }
            }
        }, 5000);
    });

    // Enhanced form validation and loading states
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && form.checkValidity()) {
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
                submitBtn.disabled = true;
            }
        });
    });

    // Price calculator for pickup requests
    initializePriceCalculator();
});

function initializePriceCalculator() {
    const categorySelect = document.getElementById('id_waste_category');
    const weightInput = document.getElementById('id_estimated_weight_kg');

    if (categorySelect && weightInput) {
        function calculatePrice() {
            const selectedOption = categorySelect.options[categorySelect.selectedIndex];
            const weight = weightInput.value;
            
            let display = document.getElementById('estimated-price');
            if (!display) {
                display = document.createElement('div');
                display.id = 'estimated-price';
                display.className = 'alert alert-info mt-2';
                display.style.display = 'none';
                weightInput.parentNode.appendChild(display);
            }

            if (selectedOption && weight && weight > 0) {
                let rate = selectedOption.dataset.rate;
                
                if (!rate) {
                    const categoryText = selectedOption.textContent;
                    const rateMatch = categoryText.match(/Rs\.(\d+(?:\.\d+)?)/);
                    if (rateMatch) {
                        rate = parseFloat(rateMatch[1]);
                    }
                }

                if (rate) {
                    const total = (parseFloat(rate) * parseFloat(weight)).toFixed(2);
                    display.innerHTML = `
                        <div class="d-flex align-items-center">
                            <i class="fas fa-calculator me-2 text-success"></i>
                            <div>
                                <strong class="text-success">Estimated Earnings: Rs. ${total}</strong>
                                <small class="d-block text-muted">Rate: Rs. ${rate}/kg × ${weight}kg</small>
                            </div>
                        </div>
                    `;
                    display.style.display = 'block';
                    display.className = 'alert alert-success mt-2';
                } else {
                    display.style.display = 'none';
                }
            } else {
                display.style.display = 'none';
            }
        }

        categorySelect.addEventListener('change', calculatePrice);
        weightInput.addEventListener('input', calculatePrice);
    }
}
