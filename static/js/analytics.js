// Global variables
let currentDashboardId = null;
let currentTimeRange = '24h';
let currentChart = null;
let sensorsData = [];
let sensorData = [];
let filteredSensors = [];
let devicesData = [];
let currentView = 'table';
let currentPage = 1;
let itemsPerPage = 12;
let activeFilters = {
    parameterTypes: [],
    status: 'all'
};

// Colors for charts
const chartColors = [
    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40',
    '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40'
];

// Initialize when page loads
$(document).ready(function () {
    currentDashboardId = window.dashboardId || 0;
    initializeDashboard();
    setupEventListeners();
});

async function initializeDashboard() {
    showLoading();

    try {
        const response = await loadDashboardData();
        updateUI(response);
        setupFilters(response);
        showToast('Dashboard loaded successfully', 'success');
    } catch (error) {
        console.error('Initialization error:', error);
        showToast('Failed to load dashboard data', 'error');
    } finally {
        hideLoading();
    }
}

async function loadDashboardData() {
    try {
        const response = await $.ajax({
            url: `/superadmin/analytics/${currentDashboardId}/data?timeRange=${currentTimeRange}`,
            method: 'GET',
            timeout: 10000
        });

        return response;
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        throw error;
    }
}

function updateUI(response) {
    if (response.error) {
        showToast(response.error, 'error');
        return;
    }

    // Store data globally
    sensorsData = response.sensors || [];
    sensorData = response.sensor_data || [];
    devicesData = response.devices || [];

    // Update statistics
    updateStatistics(response.statistics);

    // Update chart
    updateMainChart(response.chart_data);

    // Update data views
    updateAllDataViews();

    // Update parameter filter dropdown
    updateParameterFilter(response.sensor_data);
}

function updateStatistics(stats) {
    if (!stats) return;

    $('#total-devices').text(devicesData.length || 0);
    $('#active-devices').text(stats.connected_devices || 0);
    $('#total-parameters').text(stats.active_sensors || 0);
    $('#data-rate').text(stats.data_points_24h || 0);

    if (stats.latest_reading) {
        $('#data-volume').text('Latest: ' + stats.latest_reading.value);
    }
}

function updateMainChart(chartData) {
    const ctx = document.getElementById('main-chart').getContext('2d');

    if (currentChart) {
        currentChart.destroy();
    }

    if (!chartData || !chartData.labels || !chartData.datasets) {
        // Show empty state
        ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
        ctx.font = '16px Arial';
        ctx.fillStyle = '#999';
        ctx.textAlign = 'center';
        ctx.fillText('No chart data available', ctx.canvas.width / 2, ctx.canvas.height / 2);
        return;
    }

    currentChart = new Chart(ctx, {
        type: 'line',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: {
                        color: 'rgba(0,0,0,0.05)'
                    },
                    title: {
                        display: true,
                        text: 'Values'
                    }
                },
                x: {
                    grid: {
                        color: 'rgba(0,0,0,0.05)'
                    },
                    title: {
                        display: true,
                        text: 'Time'
                    }
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 20
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function (context) {
                            let label = context.dataset.label || '';
                            const value = context.parsed.y;
                            return `${label}: ${value}`;
                        }
                    }
                }
            }
        }
    });
}

function updateAllDataViews() {
    // Apply current filters
    filteredSensors = filterSensorsData();

    // Update all views
    updateTableView();
    updateCardsView();
    updateGroupsView();
    updateSensorCount();
}

function filterSensorsData() {
    let filtered = sensorData;

    // Filter by parameter type
    if (activeFilters.parameterTypes.length > 0) {
        filtered = filtered.filter(item =>
            activeFilters.parameterTypes.includes(item.parameter_type)
        );
    }

    // Filter by status
    if (activeFilters.status !== 'all') {
        filtered = filtered.filter(item =>
            item.status === activeFilters.status
        );
    }

    return filtered;
}

function updateTableView() {
    const tbody = $('#sensor-table-body');
    tbody.empty();

    if (filteredSensors.length === 0) {
        tbody.html(`
            <tr>
                <td colspan="7" style="text-align:center; padding:40px;">
                    <i class="fas fa-search" style="font-size:48px; color:#ddd;"></i>
                    <h3 style="color:#999;">No sensors found</h3>
                </td>
            </tr>
        `);
        return;
    }

    // 🔹 Group sensors by device
    const groupedByDevice = {};
    filteredSensors.forEach(item => {
        if (!groupedByDevice[item.device_id]) {
            groupedByDevice[item.device_id] = [];
        }
        groupedByDevice[item.device_id].push(item);
    });

    const deviceEntries = Object.entries(groupedByDevice);
    const paginatedDevices = getPaginatedItems(deviceEntries);

    paginatedDevices.forEach(([deviceId, parameters]) => {
        const device = devicesData.find(d => d.id === parseInt(deviceId)) || {};
        const rowspan = parameters.length;
        const status = device.status || 'offline';

        parameters.forEach((param, index) => {
            let row = `<tr>`;

            // ✅ Device cell only once
            if (index === 0) {
                row += `
                    <td rowspan="${rowspan}">
                        <strong>${escapeHTML(device.name || 'Unknown Device')}</strong><br>
                        <small class="text-muted">${escapeHTML(device.device_id || '')}</small>
                    </td>
                `;
            }

            row += `
                <td>${escapeHTML(param.parameter_type || 'N/A')}</td>
                <td><strong>${param.value ?? 0}</strong></td>
                <td>${escapeHTML(param.unit || '')}</td>
                <td>${formatRelativeTime(param.timestamp)}</td>
            `;

            // ✅ Status + actions only once
            if (index === 0) {
                row += `
                    <td rowspan="${rowspan}">
                        <span class="status-indicator ${status}">●</span>
                        ${status}
                    </td>
                    <td rowspan="${rowspan}">
                        <div class="action-buttons">
                            <button class="btn-icon view-device" data-device-id="${device.id}">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn-icon chart-sensor" data-sensor-id="${device.id}">
                                <i class="fas fa-chart-line"></i>
                            </button>
                        </div>
                    </td>
                `;
            }

            row += `</tr>`;
            tbody.append(row);
        });
    });

    setupTablePagination(deviceEntries.length);
}


function createTableRow(item) {
    const device = devicesData.find(d => d.id === item.device_id) || {};
    const lastSeen = device.last_seen ? formatRelativeTime(device.last_seen) : 'Never';

    return `
        <tr data-sensor-id="${item.id}">
            <td>
                <div class="sensor-name-cell">
                    <strong>${escapeHTML(device.name || item.device_name)}</strong><br>
                    <small class="text-muted">${escapeHTML(device.device_id || 'N/A')}</small>
                </div>
            </td>
            <td>
                <span class="status-indicator ${device.status || item.status || 'offline'}">
                    ●
                </span>
                ${device.status || item.status || 'offline'}
            </td>
            <td>
                <div class="parameter-tags">
                    <span class="parameter-tag">${escapeHTML(item.parameter_type || 'Unknown')}</span>
                </div>
            </td>
            <td>
                <div class="latest-values">
                    <strong>${item.value || item.current_value || 0}</strong>
                    <small>${escapeHTML(item.unit || '')}</small>
                </div>
            </td>
            <td>
                ${lastSeen}<br>
                <small>${formatTimeAgo(item.timestamp)}</small>
            </td>
            <td>
                ${item.stats ? `
                    <div class="quick-stats">
                        <span class="quick-stat">Min: ${item.stats.min || 0}</span>
                        <span class="quick-stat">Avg: ${item.stats.avg || 0}</span>
                        <span class="quick-stat">Max: ${item.stats.max || 0}</span>
                    </div>
                ` : 'N/A'}
            </td>
            <td>
                <div class="action-buttons">
                    <button class="btn-icon view-sensor" data-sensor-id="${item.id}"
                            title="View details">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn-icon chart-sensor" data-sensor-id="${item.device_id}"
                            title="Show chart">
                        <i class="fas fa-chart-line"></i>
                    </button>
                    <button class="btn-icon export-sensor" data-sensor-id="${item.id}"
                            title="Export data">
                        <i class="fas fa-download"></i>
                    </button>
                </div>
            </td>
        </tr>
    `;
}

function updateCardsView() {
    const container = $('#sensor-cards-container');
    container.empty();

    if (filteredSensors.length === 0) {
        container.html(`
            <div class="empty-state">
                <i class="fas fa-search" style="font-size: 48px; color: #ddd; margin-bottom: 20px;"></i>
                <h3 style="color: #999;">No sensors found</h3>
                <p>Try adjusting your filters or search term</p>
            </div>
        `);
        return;
    }

    const paginatedData = getPaginatedItems(filteredSensors);

    // Group sensor data by device for card view
    const devicesWithData = {};
    paginatedData.forEach(item => {
        const deviceId = item.device_id;
        if (!devicesWithData[deviceId]) {
            devicesWithData[deviceId] = {
                device: devicesData.find(d => d.id === deviceId) || {},
                parameters: []
            };
        }
        devicesWithData[deviceId].parameters.push(item);
    });

    Object.values(devicesWithData).forEach(deviceData => {
        const card = createSensorCard(deviceData);
        container.append(card);
    });

    setupCardsPagination(filteredSensors.length);
}

function createSensorCard(deviceData) {
    const device = deviceData.device;
    const parameters = deviceData.parameters;

    // ✅ Compute device-level last seen
    let deviceLastSeen = null;
    parameters.forEach(p => {
        if (p.timestamp) {
            const ts = new Date(p.timestamp + 'Z');
            if (!deviceLastSeen || ts > deviceLastSeen) {
                deviceLastSeen = ts;
            }
        }
    });

    return `
        <div class="sensor-card" data-device-id="${device.id}">
            <!-- HEADER -->
            <div class="sensor-card-header">
                <div class="sensor-info">
                    <h4>${escapeHTML(device.name || 'Unknown Device')}</h4>
                    <small>${escapeHTML(device.device_id || '')}</small>
                </div>
                <span class="sensor-status ${device.status || 'offline'}">
                    ${device.status === 'online' ? '●' : '○'}
                </span>
            </div>

            <!-- LAST SEEN -->
            <div class="sensor-last-seen">
                Last seen:
                <strong>
                    ${deviceLastSeen ? formatRelativeTime(deviceLastSeen.toISOString().replace('Z', '')) : 'Never'}
                </strong>
            </div>

            <!-- PARAMETERS -->
            <div class="sensor-parameters">
                ${parameters.slice(0, 3).map(param => `
                    <div class="parameter-item">
                        <span class="parameter-name">
                            ${escapeHTML(param.parameter_type)}
                        </span>
                        <span class="parameter-value">
                            ${param.value ?? '--'} ${escapeHTML(param.unit || '')}
                        </span>
                    </div>
                `).join('')}
            </div>

            <!-- ACTIONS -->
<div class="sensor-actions">
    <button class="btn-sm btn-primary view-device" data-device-id="${device.id}">
        <i class="fas fa-eye"></i> Details
    </button>
    <button class="btn-sm btn-secondary compare-device" data-device-id="${device.id}">
        <i class="fas fa-balance-scale"></i> Compare
    </button>
</div>

        </div>
    `;
}

function updateGroupsView() {
    const container = $('#parameter-groups');
    container.empty();

    if (filteredSensors.length === 0) {
        container.html(`
            <div class="empty-state">
                <i class="fas fa-search" style="font-size: 48px; color: #ddd; margin-bottom: 20px;"></i>
                <h3 style="color: #999;">No sensors found</h3>
                <p>Try adjusting your filters or search term</p>
            </div>
        `);
        return;
    }

    const groupBy = $('#group-by').val();
    const groupedData = groupSensorsData(groupBy);

    Object.entries(groupedData).forEach(([groupName, items]) => {
        const groupElement = createGroupElement(groupName, items);
        container.append(groupElement);
    });
}

function groupSensorsData(groupBy) {
    const groups = {};

    filteredSensors.forEach(item => {
        let groupKey;

        switch (groupBy) {
            case 'parameter':
                groupKey = item.parameter_type || 'Unknown';
                break;
            case 'device':
                const device = devicesData.find(d => d.id === item.device_id);
                groupKey = device ? device.name : 'Unknown Device';
                break;
            case 'status':
                const deviceStatus = devicesData.find(d => d.id === item.device_id);
                groupKey = deviceStatus ? deviceStatus.status : 'offline';
                break;
            default:
                groupKey = 'Other';
        }

        if (!groups[groupKey]) groups[groupKey] = [];
        groups[groupKey].push(item);
    });

    return groups;
}

function createGroupElement(groupName, items) {
    return `
        <div class="parameter-group">
            <!-- GROUP HEADER -->
            <div class="parameter-group-header">
                <h3>${escapeHTML(groupName)}</h3>
                <span class="group-count">${items.length} devices</span>
            </div>

            <!-- GROUP TABLE -->
            <div class="parameter-group-table">
                ${items.map(item => {
        const device = devicesData.find(d => d.id === item.device_id);
        return `
                        <div class="parameter-group-row">
                            <div class="device-name">
                                ${escapeHTML(device?.name || 'Unknown')}
                            </div>
                            <div class="parameter-value">
                                ${item.value ?? '--'}
                            </div>
                            <div class="parameter-unit">
                                ${escapeHTML(item.unit || '')}
                            </div>
                        </div>
                    `;
    }).join('')}
            </div>
        </div>
    `;
}

function setupFilters(response) {
    // Get unique parameter types
    const paramTypes = [...new Set(sensorData.map(item => item.parameter_type).filter(Boolean))];

    // Populate parameter type filter
    const paramFilter = $('#parameter-type-filter');
    paramFilter.empty();
    paramTypes.forEach(type => {
        paramFilter.append(`<option value="${escapeHTML(type)}">${escapeHTML(type)}</option>`);
    });

    // Populate chart parameter select
    const chartSelect = $('#chart-parameter-select');
    chartSelect.empty();
    chartSelect.append('<option value="all">All Parameters</option>');
    paramTypes.forEach(type => {
        chartSelect.append(`<option value="${escapeHTML(type)}">${escapeHTML(type)}</option>`);
    });
}

function updateParameterFilter(sensorData) {
    const filter = $('#parameter-filter');
    const currentValue = filter.val();
    filter.empty();
    filter.append('<option value="all">All Parameters</option>');

    // Get unique parameter types from sensor data
    const paramTypes = new Set();
    sensorData?.forEach(sensor => {
        if (sensor.parameter_type) {
            paramTypes.add(sensor.parameter_type);
        }
    });

    paramTypes.forEach(param => {
        filter.append(`<option value="${escapeHTML(param)}">${escapeHTML(param)}</option>`);
    });

    // Restore previous selection if it exists
    if (paramTypes.has(currentValue)) {
        filter.val(currentValue);
    }
}

function setupEventListeners() {
    // Time range buttons
    $('.time-btn').click(function () {
        $('.time-btn').removeClass('active');
        $(this).addClass('active');
        currentTimeRange = $(this).data('range');

        if (currentTimeRange === 'custom') {
            $('#custom-range-panel').show();
        } else {
            $('#custom-range-panel').hide();
            reloadDashboardData();
        }
    });

    // Custom date range
    $('#apply-custom-range').click(function () {
        const startDate = $('#start-date').val();
        const endDate = $('#end-date').val();

        if (!startDate || !endDate) {
            showToast('Please select both start and end dates', 'warning');
            return;
        }

        const start = new Date(startDate);
        const end = new Date(endDate);

        if (start > end) {
            showToast('Start date must be before end date', 'warning');
            return;
        }

        currentTimeRange = `custom_${startDate}_${endDate}`;
        reloadDashboardData();
        $('#custom-range-panel').hide();
    });

    $('#cancel-custom-range').click(function () {
        $('#custom-range-panel').hide();
        $('.time-btn[data-range="24h"]').click();
    });

    // View toggle
    $('.view-toggle-btn').click(function () {
        $('.view-toggle-btn').removeClass('active');
        $(this).addClass('active');
        currentView = $(this).data('view');

        $('.data-section').hide();
        $(`#${currentView}-view`).show();


        // Update the current view
        switch (currentView) {
            case 'table':
                updateTableView();
                break;
            case 'cards':
                updateCardsView();
                break;
            case 'groups':
                updateGroupsView();
                break;
        }
    });

    // Filter actions
    $('#apply-filters').click(applyFilters);
    $('#clear-filters').click(clearFilters);

    // Search
    $('#sensor-search').on('input', debounce(filterBySearch, 300));

    // Chart parameter select
    $('#chart-parameter-select').change(filterChartByParameter);

    // Group by select
    $('#group-by').change(function () {
        if (currentView === 'groups') {
            updateGroupsView();
        }
    });

    // Cards per page
    $('#cards-per-page').change(function () {
        itemsPerPage = parseInt($(this).val());
        currentPage = 1;
        updateCardsView();
    });

    // Refresh
    $('#refresh-data').click(reloadDashboardData);

    // Export
    $('#export-data').click(exportAllData);
    $('#export-chart').click(exportChartImage);

    // Sensor actions (delegated events)
    $(document).on('click', '.view-sensor', function () {
        const sensorId = $(this).data('sensor-id');
        showSensorDetails(sensorId);
    });

    $(document).on('click', '.chart-sensor', function () {
        const deviceId = $(this).data('sensor-id');
        showDeviceChart(deviceId);
    });

    $(document).on('click', '.export-sensor', function () {
        const sensorId = $(this).data('sensor-id');
        exportSensorData(sensorId);
    });

    $(document).on('click', '.view-device', function () {
        const deviceId = $(this).data('device-id');
        showDeviceDetails(deviceId);
    });

    // Modal close
    $(document).on('click', '.close-modal', function () {
        $('#sensor-modal').hide();
    });

    $(document).on('click', '#sensor-modal', function (e) {
        if (e.target === this) {
            $(this).hide();
        }
    });
    $(document).on('click', '.compare-device', function () {
    const deviceId = $(this).data('device-id');
    showToast('Compare view coming soon', 'info');
    });


    // Keyboard shortcuts
    $(document).on('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            $('#sensor-search').focus();
        }

        if (e.key === 'Escape') {
            $('.modal').hide();
        }
    });
}

function reloadDashboardData() {
    showLoading();
    loadDashboardData()
        .then(updateUI)
        .catch(error => {
            console.error('Error reloading data:', error);
            showToast('Failed to reload data', 'error');
        })
        .finally(hideLoading);
}

function applyFilters() {
    activeFilters.parameterTypes = $('#parameter-type-filter').val() || [];
    activeFilters.status = $('#status-filter').val();

    currentPage = 1;
    updateAllDataViews();

    const appliedFilters = [];
    if (activeFilters.parameterTypes.length > 0) {
        appliedFilters.push(`${activeFilters.parameterTypes.length} parameter types`);
    }
    if (activeFilters.status !== 'all') {
        appliedFilters.push(`${activeFilters.status} devices`);
    }

    if (appliedFilters.length > 0) {
        showToast(`Filters applied: ${appliedFilters.join(', ')}`, 'info');
    }
}

function clearFilters() {
    activeFilters = {
        parameterTypes: [],
        status: 'all'
    };

    $('#parameter-type-filter').val([]);
    $('#status-filter').val('all');

    currentPage = 1;
    updateAllDataViews();

    showToast('All filters cleared', 'info');
}

function filterBySearch() {
    const searchTerm = $('#sensor-search').val().toLowerCase();

    if (!searchTerm) {
        filteredSensors = filterSensorsData();
    } else {
        filteredSensors = filterSensorsData().filter(item => {
            const device = devicesData.find(d => d.id === item.device_id);
            return (
                (device && device.name && device.name.toLowerCase().includes(searchTerm)) ||
                (device && device.device_id && device.device_id.toLowerCase().includes(searchTerm)) ||
                (item.parameter_type && item.parameter_type.toLowerCase().includes(searchTerm)) ||
                (item.unit && item.unit.toLowerCase().includes(searchTerm))
            );
        });
    }

    currentPage = 1;

    switch (currentView) {
        case 'table':
            updateTableView();
            break;
        case 'cards':
            updateCardsView();
            break;
        case 'groups':
            updateGroupsView();
            break;
    }

    updateSensorCount();
}

function filterChartByParameter() {
    const selectedParam = $(this).val();

    if (!currentChart || selectedParam === 'all') {
        if (currentChart && currentChart.data) {
            currentChart.data.datasets.forEach(dataset => {
                dataset.hidden = false;
            });
            currentChart.update();
        }
        return;
    }

    currentChart.data.datasets.forEach(dataset => {
        dataset.hidden = !dataset.label?.includes(selectedParam);
    });

    currentChart.update();
}

function getPaginatedItems(items) {
    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    return items.slice(start, end);
}

function setupTablePagination(totalItems) {
    const totalPages = Math.ceil(totalItems / itemsPerPage);
    setupPagination('table-pagination', totalPages);
}

function setupCardsPagination(totalItems) {
    const totalPages = Math.ceil(totalItems / itemsPerPage);
    setupPagination('cards-pagination', totalPages);
}

function setupPagination(containerId, totalPages) {
    const container = $(`#${containerId}`);
    container.empty();

    if (totalPages <= 1) return;

    // Previous button
    container.append(`
        <button class="page-btn ${currentPage === 1 ? 'disabled' : ''}" 
                data-page="${currentPage - 1}"
                ${currentPage === 1 ? 'disabled' : ''}>
            <i class="fas fa-chevron-left"></i>
        </button>
    `);

    // Page numbers
    const maxVisible = 5;
    let startPage = Math.max(1, currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(totalPages, startPage + maxVisible - 1);

    if (endPage - startPage + 1 < maxVisible) {
        startPage = Math.max(1, endPage - maxVisible + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
        container.append(`
            <button class="page-btn ${i === currentPage ? 'active' : ''}" 
                    data-page="${i}">
                ${i}
            </button>
        `);
    }

    // Next button
    container.append(`
        <button class="page-btn ${currentPage === totalPages ? 'disabled' : ''}" 
                data-page="${currentPage + 1}"
                ${currentPage === totalPages ? 'disabled' : ''}>
            <i class="fas fa-chevron-right"></i>
        </button>
    `);

    // Update page button event handlers
    container.find('.page-btn:not(.disabled)').off('click').click(function () {
        const page = parseInt($(this).data('page'));
        if (page && page !== currentPage) {
            currentPage = page;
            switch (currentView) {
                case 'table':
                    updateTableView();
                    break;
                case 'cards':
                    updateCardsView();
                    break;
                case 'groups':
                    updateGroupsView();
                    break;
            }
        }
    });
}

function updateSensorCount() {
    const uniqueDevices = new Set(filteredSensors.map(s => s.device_id));
    $('#visible-sensors').text(uniqueDevices.size);
    $('#total-sensors').text(new Set(sensorData.map(s => s.device_id)).size);
}


async function showSensorDetails(sensorId) {
    try {
        // Find the sensor data
        const sensor = sensorData.find(s => s.id === sensorId);
        if (!sensor) {
            showToast('Sensor not found', 'error');
            return;
        }

        const device = devicesData.find(d => d.id === sensor.device_id);

        const modalContent = `
            <h2>${escapeHTML(sensor.name || sensor.parameter_type)} Details</h2>
            <div class="sensor-info" style="margin: 20px 0;">
                <p><strong>Device:</strong> ${escapeHTML(device ? device.name : 'Unknown')}</p>
                <p><strong>Device ID:</strong> ${escapeHTML(device ? device.device_id : 'N/A')}</p>
                <p><strong>Parameter Type:</strong> ${escapeHTML(sensor.parameter_type || 'Unknown')}</p>
                <p><strong>Status:</strong> <span class="${sensor.status || 'offline'}">
                    ${sensor.status || 'offline'}
                </span></p>
                <p><strong>Latest Value:</strong> ${sensor.value} ${escapeHTML(sensor.unit || '')}</p>
                <p><strong>Last Updated:</strong> ${formatRelativeTime(sensor.timestamp)}</p>
            </div>
            
            ${sensor.stats ? `
                <div class="parameter-stats" style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <h4>Statistics (Last 24h)</h4>
                    <div style="display: flex; gap: 20px; margin-top: 10px;">
                        <div>
                            <strong>Min:</strong><br>
                            <span style="font-size: 24px; font-weight: bold;">${sensor.stats.min}</span>
                        </div>
                        <div>
                            <strong>Average:</strong><br>
                            <span style="font-size: 24px; font-weight: bold;">${sensor.stats.avg}</span>
                        </div>
                        <div>
                            <strong>Max:</strong><br>
                            <span style="font-size: 24px; font-weight: bold;">${sensor.stats.max}</span>
                        </div>
                    </div>
                </div>
            ` : ''}
        `;

        $('#modal-content').html(modalContent);
        $('#sensor-modal').show();

    } catch (error) {
        console.error('Error showing sensor details:', error);
        showToast('Failed to load sensor details', 'error');
    }
}


async function showDeviceDetails(deviceId) {
    try {
        const device = devicesData.find(d => d.id === deviceId);
        if (!device) {
            showToast('Device not found', 'error');
            return;
        }

        const deviceSensors = sensorData.filter(s => s.device_id === deviceId);
        const now = new Date();
        const ONLINE_LIMIT_MS = 10 * 60 * 1000; // 10 minutes

        // ✅ Compute device-level last seen (latest timestamp)
        let deviceLastSeen = null;
        let isDeviceOnline = false;

        deviceSensors.forEach(s => {
            if (s.timestamp) {
                const ts = new Date(s.timestamp + 'Z');
                if (!deviceLastSeen || ts > deviceLastSeen) {
                    deviceLastSeen = ts;
                }
                if (now - ts <= ONLINE_LIMIT_MS) {
                    isDeviceOnline = true; // any fresh data = device online
                }
            }
        });

        const modalContent = `
            <!-- HEADER -->
            <div class="modal-header">
                <div>
                    <h2>${escapeHTML(device.name)}</h2>
                    <small>ID: ${escapeHTML(device.device_id)}</small><br>
                    <small>
                        Last Seen:
                        <strong>
                            ${deviceLastSeen
                ? formatRelativeTime(deviceLastSeen.toISOString().replace('Z', ''))
                : 'Never'}
                        </strong>
                    </small>
                </div>
                <span class="device-status ${isDeviceOnline ? 'online' : 'offline'}">
                    ${isDeviceOnline ? 'ONLINE' : 'OFFLINE'}
                </span>
            </div>

            <!-- QUICK STATS -->
            <div class="device-stats">
                <div class="stat-box">
                    <strong>${deviceSensors.length}</strong>
                    <span>Parameters</span>
                </div>
                <div class="stat-box">
                    <strong>${isDeviceOnline ? 'ONLINE' : 'OFFLINE'}</strong>
                    <span>Device Status</span>
                </div>
                <div class="stat-box">
                    <strong>${deviceLastSeen ? 'ACTIVE' : 'INACTIVE'}</strong>
                    <span>Data State</span>
                </div>
            </div>

            <!-- PARAMETERS -->
            <div class="parameters-grid">
                ${deviceSensors.map(sensor => `
                    <div class="parameter-card">
                        <div class="parameter-header">
                            <span class="parameter-name">
                                ${escapeHTML(sensor.parameter_type)}
                            </span>
                        </div>

                        <div class="parameter-value">
                            ${sensor.value ?? 0}
                        </div>

                        <div class="parameter-unit">
                            ${escapeHTML(sensor.unit || '')}
                        </div>
                    </div>
                `).join('')}
            </div>

            <!-- FOOTER -->
            <div class="modal-footer">
                <button class="btn-secondary close-modal">Close</button>
                <button class="btn-primary" onclick="showDeviceChart(${device.id})">
                    <i class="fas fa-chart-line"></i> View Chart
                </button>
            </div>
        `;

        $('#modal-content').html(modalContent);
        $('#sensor-modal').show();

    } catch (error) {
        console.error(error);
        showToast('Failed to load device details', 'error');
    }
}



function showDeviceChart(deviceId) {
    // This would ideally load a detailed chart for the device
    showToast('Detailed chart view would open here', 'info');
}

function exportSensorData(sensorId) {
    const sensor = sensorData.find(s => s.id === sensorId);
    if (!sensor) {
        showToast('Sensor not found', 'error');
        return;
    }

    // Create CSV content
    let csv = 'Timestamp,Parameter Type,Value,Unit\n';
    csv += `"${new Date().toISOString()}","${sensor.parameter_type}","${sensor.value}","${sensor.unit}"\n`;

    downloadCSV(csv, `sensor_${sensorId}_export.csv`);
    showToast('Sensor data exported', 'success');
}

function exportAllData() {
    if (filteredSensors.length === 0) {
        showToast('No data to export', 'warning');
        return;
    }

    let csv = 'Device,Device ID,Parameter Type,Value,Unit,Status,Timestamp\n';

    filteredSensors.forEach(item => {
        const device = devicesData.find(d => d.id === item.device_id);
        csv += `"${escapeCSV(device ? device.name : 'Unknown')}","${escapeCSV(device ? device.device_id : 'N/A')}","${escapeCSV(item.parameter_type)}","${item.value}","${escapeCSV(item.unit)}","${item.status}","${item.timestamp}"\n`;
    });

    downloadCSV(csv, `dashboard_${currentDashboardId}_export.csv`);
    showToast(`Exported ${filteredSensors.length} records`, 'success');
}

function exportChartImage() {
    if (!currentChart) {
        showToast('No chart to export', 'warning');
        return;
    }

    const link = document.createElement('a');
    link.download = `chart_${new Date().toISOString().split('T')[0]}.png`;
    link.href = currentChart.toBase64Image();
    link.click();

    showToast('Chart exported as PNG', 'success');
}

function downloadCSV(csv, filename) {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
}

// Utility functions
function formatRelativeTime(timestamp) {
    if (!timestamp) return 'Never';

    const date = new Date(timestamp + 'Z'); // UTC → local
    const now = new Date();

    let diffMs = now - date;

    // ✅ Safety for future timestamps / clock mismatch
    if (diffMs < 0) diffMs = 0;

    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleString();
}



function formatTimeAgo(timestamp) {
    if (!timestamp) return '';
    return formatRelativeTime(timestamp);
}

function getGroupIcon(groupName) {
    const iconMap = {
        'temperature': 'fa-thermometer-half',
        'Temperature': 'fa-thermometer-half',
        'humidity': 'fa-tint',
        'Humidity': 'fa-tint',
        'pressure': 'fa-compress-arrows-alt',
        'Pressure': 'fa-compress-arrows-alt',
        'voltage': 'fa-bolt',
        'Voltage': 'fa-bolt',
        'power': 'fa-plug',
        'Power': 'fa-plug',
        'online': 'fa-wifi',
        'offline': 'fa-wifi-slash'
    };

    for (const [key, icon] of Object.entries(iconMap)) {
        if (groupName.toLowerCase().includes(key.toLowerCase())) {
            return icon;
        }
    }

    return 'fa-chart-line';
}

function getRandomColor() {
    const colors = [
        '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF', '#FF9F40',
        '#E7E9ED', '#8AC926', '#1982C4', '#6A4C93', '#F15BB5', '#00BBF9'
    ];
    return colors[Math.floor(Math.random() * colors.length)] + '40'; // 40 for opacity
}

function showLoading() {
    $('.stats-grid, .chart-container, .data-section').addClass('loading');
}

function hideLoading() {
    $('.stats-grid, .chart-container, .data-section').removeClass('loading');
}

function showToast(message, type = 'info') {
    // Remove existing toasts
    $('.toast').remove();

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const toast = $(`
        <div class="toast ${type}" role="alert">
            <i class="fas ${icons[type]}" style="color: var(--${type}-color); font-size: 1.5rem;"></i>
            <div>
                <strong>${escapeHTML(message)}</strong>
            </div>
        </div>
    `);

    $('body').append(toast);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        toast.fadeOut(300, () => toast.remove());
    }, 5000);
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

function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeCSV(str) {
    if (!str) return '';
    return str.toString().replace(/"/g, '""');
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (currentChart) {
        currentChart.destroy();
    }
});

