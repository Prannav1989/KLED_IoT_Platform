document.addEventListener('DOMContentLoaded', function () {
    console.log('Initializing SuperAdmin Dashboard...');

    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    if (alerts.length > 0) {
        setTimeout(function () {
            alerts.forEach(alert => {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                bsAlert.close();
            });
        }, 5000);
    }

    // Make table rows clickable
    document.querySelectorAll('.clickable-row').forEach(row => {
        row.style.cursor = 'pointer';
        row.addEventListener('click', function () {
            const url = this.getAttribute('onclick').match(/'(.*?)'/)[1];
            window.location.href = url;
        });
    });

    // Initialize Charts with backend data
    initializeCharts();

    // Real-time stats update
    updateStats();
    setInterval(updateStats, 30000);
});

// Initialize Charts with backend data
function initializeCharts() {
    console.log('Initializing dashboard charts...');
    console.log('Chart data available:', window.chartData);

    // Users by Role Chart
    const roleChartCtx = document.getElementById('roleChart');
    if (roleChartCtx) {
        console.log('Initializing role chart with data:', window.chartData?.users_by_role);

        // Use backend data if available, otherwise use fallback
        let roleLabels, roleData, roleColors;

        if (window.chartData?.users_by_role?.labels && window.chartData?.users_by_role?.data) {
            // Use backend data
            roleLabels = window.chartData.users_by_role.labels;
            roleData = window.chartData.users_by_role.data;
            roleColors = window.chartData.users_by_role.colors || ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6'];
        } else {
            // Fallback data
            console.log('Using fallback data for role chart');
            const defaultRoleData = {
                'Super Admin': 1,
                'Admin': 2,
                'User': 10
            };

            roleLabels = Object.keys(defaultRoleData);
            roleData = Object.values(defaultRoleData);
            roleColors = ['#3498db', '#2ecc71', '#e74c3c', '#f39c12', '#9b59b6'];
        }

        const roleChart = new Chart(roleChartCtx, {
            type: 'doughnut',
            data: {
                labels: roleLabels,
                datasets: [{
                    data: roleData,
                    backgroundColor: roleColors,
                    borderWidth: 2,
                    borderColor: '#fff'
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
                            usePointStyle: true,
                            font: {
                                size: 11
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                const label = context.label || '';
                                const value = context.raw || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                },
                cutout: '70%'
            }
        });
    } else {
        console.error('Role chart canvas not found!');
    }

    // Device Status Chart
    const deviceStatusChartCtx = document.getElementById('deviceStatusChart');
    if (deviceStatusChartCtx) {
        console.log('Initializing device status chart with data:', window.chartData?.device_status);

        // Use backend data if available, otherwise use fallback
        let deviceLabels, deviceData, deviceColors;

        if (window.chartData?.device_status?.labels && window.chartData?.device_status?.data) {
            // Use backend data
            deviceLabels = window.chartData.device_status.labels;
            deviceData = window.chartData.device_status.data;
            deviceColors = window.chartData.device_status.colors || ['#27ae60', '#e74c3c'];
        } else {
            // Fallback: calculate from stats
            console.log('Using fallback data for device status chart');
            const activeDevices = window.chartData.stats.active_devices || 0;
            const totalDevices = window.chartData.stats.total_devices || 0;
            const inactiveDevices = Math.max(0, totalDevices - activeDevices);


            deviceLabels = ['Active', 'Inactive'];
            deviceData = [activeDevices, inactiveDevices];
            deviceColors = ['#27ae60', '#e74c3c'];
        }

        const deviceStatusChart = new Chart(deviceStatusChartCtx, {
            type: 'bar',
            data: {
                labels: deviceLabels,
                datasets: [{
                    label: 'Devices',
                    data: deviceData,
                    backgroundColor: deviceColors,
                    borderWidth: 0,
                    borderRadius: 8,
                    barPercentage: 0.6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function (context) {
                                return `Devices: ${context.raw}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            drawBorder: false
                        },
                        ticks: {
                            stepSize: 1,
                            precision: 0
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    } else {
        console.error('Device status chart canvas not found!');
    }
}

// Real-time stats update function
function updateStats() {
    console.log('Updating dashboard stats...');
    // You can implement actual API call here when ready
}

function updateStatElements(data) {
    const elements = {
        'total-users': data.total_users || 0,
        'total-devices': data.total_devices || 0,
        'today-data': data.total_sensor_data || 0
    };

    for (const [id, value] of Object.entries(elements)) {
        const element = document.getElementById(id);
        if (element) {
            // Add animation
            element.style.transform = 'scale(1.1)';
            setTimeout(() => {
                element.textContent = value.toLocaleString();
                element.style.transform = 'scale(1)';
            }, 150);
        }
    }
}