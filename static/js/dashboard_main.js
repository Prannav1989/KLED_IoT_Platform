// dashboard_main.js - Main dashboard functionality

// Sensor icon mapping function
// Sensor icon mapping function (Milesight Compatible)
function getSensorIcon(sensorType) {

    const iconMap = {
        // Environment
        'temperature': 'thermometer-half',
        'temp': 'thermometer-half',
        'humidity': 'tint',
        'rh': 'tint',
        'co2': 'wind',
        'tvoc': 'biohazard',
        'iaq': 'smog',
        'o3': 'cloud',
        'ozone': 'cloud',
        'pm2.5': 'smog',
        'pm10': 'smog',
        'pm25': 'smog',

        // Air Quality / Gas
        'hcho': 'vial',
        'voc': 'vial',
        'nh3': 'vial',
        'no2': 'vial',
        'so2': 'vial',
        'co': 'cloud',
        'ch4': 'fire',
        'gas': 'fire',

        // Motion / People Counting
        'pir': 'running',
        'motion': 'running',
        'people_count': 'users',
        'count': 'users',
        'sound': 'volume-up',
        'noise': 'volume-up',

        // Light / Lux
        'light': 'sun',
        'lux': 'sun',

        // Pressure / Weather
        'pressure': 'tachometer-alt',
        'barometric': 'tachometer-alt',

        // Water Leak / EM300 Series
        'leak': 'water',
        'water_leak': 'water',

        // Accelerometer / Vibration
        'vibration': 'wave-square',
        'acceleration': 'wave-square',
        'tilt': 'mobile-alt',

        // Electrical (WS Series)
        'voltage': 'bolt',
        'current': 'bolt',
        'power': 'bolt',
        'energy': 'bolt',

        // Battery / Signal
        'battery': 'battery-half',
        'rssi': 'signal',
        'snr': 'wave-square',
        'signal': 'signal',

        // Location
        'gps': 'map-marker-alt',
        'latitude': 'map-marker-alt',
        'longitude': 'map-marker-alt',

        // Default fallback
        'default': 'chart-line'
    };

    if (!sensorType) return iconMap.default;

    return iconMap[sensorType.toLowerCase()] || iconMap.default;
}

// Dashboard class to manage all functionality
class DashboardManager {
    constructor() {
        this.autoRefresh = true;
        this.refreshInterval = null;
        this.refreshRate = 30000; // 30 seconds
        this.dashboardData = null;
        
        this.init();
    }

    init() {
        try {
            this.loadDashboardData();
            this.setupEventListeners();
            this.initializeDashboard();
            
            if (this.dashboardData.device_count > 0) {
                this.setupAutoRefresh();
            }
        } catch (error) {
            console.error('Dashboard initialization failed:', error);
            this.showNotification('Dashboard initialization failed', 'danger');
        }
    }

    loadDashboardData() {
        const dashboardDataElement = document.getElementById('dashboardData');
        if (!dashboardDataElement) {
            throw new Error('Dashboard data element not found');
        }
        
        this.dashboardData = JSON.parse(dashboardDataElement.textContent);
    }

    setupEventListeners() {
        // Manual refresh button
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshDashboard());
        }

        // Download report button
        const downloadBtn = document.getElementById('downloadReportBtn');
        if (downloadBtn) {
            downloadBtn.addEventListener('click', () => this.downloadReport());
        }

        // Device card animations
        this.setupDeviceCardAnimations();
    }

    initializeDashboard() {
        this.updateLastUpdateTime();
        this.updateDashboardStats();
    }

    setupAutoRefresh() {
        this.refreshInterval = setInterval(() => {
            if (this.autoRefresh) {
                this.refreshDashboard();
            }
        }, this.refreshRate);
    }

    updateLastUpdateTime() {
        const lastUpdateElement = document.getElementById('lastUpdate');
        if (lastUpdateElement) {
            const now = new Date();
            lastUpdateElement.textContent = now.toLocaleTimeString();
        }
    }

    updateDashboardStats() {
        // Update any real-time stats here
        console.log('Updating dashboard stats...');
    }

    async refreshDashboard() {
        const refreshBtn = document.getElementById('refreshBtn');
        const originalContent = refreshBtn.innerHTML;

        try {
            // Disable button and show loading state
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing';

            // Make API call to refresh data
            const response = await fetch(window.location.href, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Cache-Control': 'no-cache'
                },
                cache: 'no-cache'
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const html = await response.text();
            
            // Parse the response and update the dashboard
            await this.updateDashboardContent(html);
            
            this.updateLastUpdateTime();
            this.showNotification('Dashboard updated successfully', 'success');

        } catch (error) {
            console.error('Refresh failed:', error);
            this.showNotification('Refresh failed: ' + error.message, 'danger');
        } finally {
            // Re-enable button and restore original content
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = originalContent;
        }
    }

    async updateDashboardContent(html) {
        // Create a temporary container to parse the HTML
        const tempContainer = document.createElement('div');
        tempContainer.innerHTML = html;

        // Update sensor grid
        const newSensorGrid = tempContainer.querySelector('#sensorGrid');
        if (newSensorGrid) {
            const currentSensorGrid = document.getElementById('sensorGrid');
            currentSensorGrid.innerHTML = newSensorGrid.innerHTML;
        }

        // Update stats cards
        const statsCards = tempContainer.querySelectorAll('.card.border-left-primary, .card.border-left-success, .card.border-left-info, .card.border-left-warning');
        statsCards.forEach(newCard => {
            const cardType = Array.from(newCard.classList).find(cls => cls.includes('border-left-'));
            const currentCard = document.querySelector(`.card.${cardType}`);
            if (currentCard) {
                currentCard.innerHTML = newCard.innerHTML;
            }
        });

        // Re-initialize device card animations
        this.setupDeviceCardAnimations();
    }

    setupDeviceCardAnimations() {
        const deviceCards = document.querySelectorAll('.device-card');
        deviceCards.forEach(card => {
            // Remove existing event listeners
            card.replaceWith(card.cloneNode(true));
            
            const newCard = document.querySelector(`[data-card-id="${card.dataset.cardId}"]`) || card;
            
            newCard.addEventListener('mouseenter', function () {
                this.style.transform = 'translateY(-5px)';
                this.style.transition = 'transform 0.2s ease-in-out';
                this.style.boxShadow = '0 4px 8px rgba(0,0,0,0.15)';
            });

            newCard.addEventListener('mouseleave', function () {
                this.style.transform = 'translateY(0)';
                this.style.boxShadow = '';
            });
        });
    }

    async downloadReport() {
        try {
            this.showNotification('Preparing download...', 'info');
            
            // Simulate API call for report generation
            const response = await fetch(`/api/dashboard/${this.dashboardData.dashboard_id}/report`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = `dashboard-report-${new Date().toISOString().split('T')[0]}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
                
                this.showNotification('Report downloaded successfully', 'success');
            } else {
                throw new Error('Failed to generate report');
            }
        } catch (error) {
            console.error('Download failed:', error);
            this.showNotification('Download failed: ' + error.message, 'danger');
        }
    }

    showNotification(message, type = 'info') {
        // Remove existing notifications
        const existingNotifications = document.querySelectorAll('.dashboard-notification');
        existingNotifications.forEach(notification => notification.remove());

        const alertClass = {
            'success': 'alert-success',
            'danger': 'alert-danger',
            'warning': 'alert-warning',
            'info': 'alert-info'
        }[type] || 'alert-info';

        const notification = document.createElement('div');
        notification.className = `alert ${alertClass} alert-dismissible fade show dashboard-notification position-fixed`;
        notification.style.cssText = 'top: 20px; right: 20px; z-index: 1050; min-width: 300px;';
        notification.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="fas fa-${this.getNotificationIcon(type)} me-2"></i>
                <span>${message}</span>
                <button type="button" class="btn-close ms-auto" data-bs-dismiss="alert"></button>
            </div>
        `;

        document.body.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 5000);
    }

    getNotificationIcon(type) {
        const icons = {
            'success': 'check-circle',
            'danger': 'exclamation-triangle',
            'warning': 'exclamation-circle',
            'info': 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    // Cleanup method to prevent memory leaks
    destroy() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        
        // Remove event listeners
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) {
            refreshBtn.replaceWith(refreshBtn.cloneNode(true));
        }
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function () {
    window.dashboardManager = new DashboardManager();
});

// Export for testing or other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { DashboardManager, getSensorIcon };
}