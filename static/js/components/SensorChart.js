// Reusable Sensor Chart Component
class SensorChart {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.chart = null;
        this.defaultOptions = {
            height: 300,
            timeRange: '24h',
            showLegend: true,
            showControls: true,
            autoRefresh: false,
            refreshInterval: 30000
        };
        this.options = { ...this.defaultOptions, ...options };
        this.sensors = [];
        this.selectedSensors = new Set();
        this.chartColors = [
            '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#6f42c1',
            '#858796', '#5a5c69', '#e83e8c', '#fd7e14', '#20c997', '#6610f2'
        ];
        this.autoRefreshInterval = null;
    }

    // Initialize the chart
    init() {
        this.renderContainer();
        this.setupEventListeners();
        
        if (this.options.autoRefresh) {
            this.startAutoRefresh();
        }
        
        return this;
    }

    // Render the chart container with controls
    renderContainer() {
        const container = document.getElementById(this.containerId);
        if (!container) {
            console.error(`Container with id '${this.containerId}' not found`);
            return;
        }

        let controlsHtml = '';
        if (this.options.showControls) {
            controlsHtml = `
                <div class="chart-controls mb-3">
                    <div class="d-flex flex-wrap gap-2 align-items-center">
                        <!-- Sensor Selection -->
                        <div class="dropdown">
                            <button class="btn btn-outline-primary btn-sm dropdown-toggle" type="button" 
                                    id="${this.containerId}-sensorSelect" data-toggle="dropdown" 
                                    aria-haspopup="true" aria-expanded="false">
                                <i class="fas fa-filter mr-1"></i>
                                Select Sensors
                                <span class="badge badge-primary ml-1" id="${this.containerId}-selectedCount">0</span>
                            </button>
                            <div class="dropdown-menu dropdown-menu-right p-3" style="min-width: 300px;" 
                                 id="${this.containerId}-sensorMenu">
                                <div class="d-flex justify-content-between align-items-center mb-2">
                                    <h6 class="m-0">Select Sensors</h6>
                                    <div class="small">
                                        <a href="#" class="text-primary mr-2" id="${this.containerId}-selectAll">All</a>
                                        <a href="#" class="text-secondary" id="${this.containerId}-clearAll">None</a>
                                    </div>
                                </div>
                                <div class="dropdown-divider"></div>
                                <div id="${this.containerId}-sensorCheckboxes" class="max-h-200 overflow-auto">
                                    <p class="text-muted text-center my-3">No sensors available</p>
                                </div>
                                <div class="dropdown-divider"></div>
                                <div class="d-flex justify-content-between mt-2">
                                    <button class="btn btn-sm btn-outline-secondary" id="${this.containerId}-cancelSelection">
                                        Cancel
                                    </button>
                                    <button class="btn btn-sm btn-primary" id="${this.containerId}-applySelection">
                                        Apply
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Time Range -->
                        <select class="form-control form-control-sm" id="${this.containerId}-timeRange" style="width: 150px;">
                            <option value="1h">Last 1 Hour</option>
                            <option value="6h">Last 6 Hours</option>
                            <option value="24h" selected>Last 24 Hours</option>
                            <option value="7d">Last 7 Days</option>
                            <option value="30d">Last 30 Days</option>
                        </select>
                        
                        <!-- Refresh Button -->
                        <button class="btn btn-outline-secondary btn-sm" id="${this.containerId}-refreshBtn" title="Refresh">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                    </div>
                </div>
            `;
        }

        container.innerHTML = `
            <div class="sensor-chart-component">
                ${controlsHtml}
                <div class="chart-container">
                    <div class="chart-area" style="height: ${this.options.height}px;">
                        <canvas id="${this.containerId}-chart"></canvas>
                    </div>
                    ${this.options.showLegend ? `
                    <div class="chart-legend mt-3" id="${this.containerId}-legend">
                        <!-- Legend will be rendered here -->
                    </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    // Load data into the chart
    loadData(sensors, chartData = null) {
        this.sensors = sensors || [];
        this.updateSensorSelectionMenu();
        this.renderChart(chartData);
    }

    // Load data from API
    loadDataFromApi(apiUrl) {
        this.showLoading();
        
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return response.json();
            })
            .then(data => {
                this.loadData(data.sensor_data, data.chart_data);
                this.hideLoading();
            })
            .catch(error => {
                console.error('Error loading chart data:', error);
                this.showError('Failed to load chart data');
                this.hideLoading();
            });
    }

    // Update sensor selection menu
    updateSensorSelectionMenu() {
        const container = document.getElementById(`${this.containerId}-sensorCheckboxes`);
        const selectedCount = document.getElementById(`${this.containerId}-selectedCount`);
        
        if (!container) return;

        if (!this.sensors || this.sensors.length === 0) {
            container.innerHTML = '<p class="text-muted text-center my-3">No sensors available</p>';
            if (selectedCount) selectedCount.textContent = '0';
            return;
        }

        let html = '';
        this.sensors.forEach((sensor, index) => {
            const sensorId = this.getSensorId(sensor);
            const sensorName = sensor.name || sensor.sensor_name || `Sensor ${index + 1}`;
            const deviceName = sensor.device_name || sensor.device?.name || 'Unknown Device';
            const isSelected = this.selectedSensors.has(sensorId);
            const color = this.chartColors[index % this.chartColors.length];

            html += `
                <div class="sensor-checkbox-item">
                    <label class="d-flex align-items-center mb-0">
                        <input type="checkbox" class="sensor-checkbox" 
                               value="${sensorId}" 
                               ${isSelected ? 'checked' : ''}
                               data-sensor-index="${index}">
                        <span class="sensor-color-indicator" style="background-color: ${color};"></span>
                        <div class="flex-grow-1">
                            <div class="small font-weight-bold">${sensorName}</div>
                            <div class="text-muted" style="font-size: 0.7rem;">${deviceName}</div>
                        </div>
                    </label>
                </div>
            `;
        });

        container.innerHTML = html;
        if (selectedCount) selectedCount.textContent = this.selectedSensors.size.toString();

        // Select all if none selected
        if (this.selectedSensors.size === 0 && this.sensors.length > 0) {
            this.selectAllSensors();
        }
    }

    // Get unique sensor ID
    getSensorId(sensor) {
        return `${sensor.device_id || 'unknown'}-${sensor.sensor_type || 'sensor'}-${sensor.id || Math.random().toString(36).substr(2, 9)}`;
    }

    // Select all sensors
    selectAllSensors() {
        this.sensors.forEach(sensor => {
            this.selectedSensors.add(this.getSensorId(sensor));
        });
        this.updateSensorSelectionMenu();
    }

    // Clear all sensors
    clearAllSensors() {
        this.selectedSensors.clear();
        this.updateSensorSelectionMenu();
    }

    // Apply sensor selection
    applySensorSelection() {
        const checkboxes = document.querySelectorAll(`#${this.containerId}-sensorCheckboxes .sensor-checkbox:checked`);
        this.selectedSensors.clear();
        
        checkboxes.forEach(checkbox => {
            this.selectedSensors.add(checkbox.value);
        });

        document.getElementById(`${this.containerId}-selectedCount`).textContent = this.selectedSensors.size.toString();
        
        // Close dropdown and refresh chart
        const dropdown = document.getElementById(`${this.containerId}-sensorSelect`);
        if (dropdown) {
            $(dropdown).dropdown('toggle');
        }

        this.renderChart();
    }

    // Render the main chart
    renderChart(chartData = null) {
        const ctx = document.getElementById(`${this.containerId}-chart`);
        if (!ctx) return;
        
        if (this.chart) {
            this.chart.destroy();
        }

        const datasets = this.prepareChartData();
        const labels = chartData?.labels || this.generateTimeLabels();

        if (datasets.length === 0) {
            this.showNoDataMessage();
            return;
        }

        this.chart = new Chart(ctx, {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { 
                        mode: 'index', 
                        intersect: false,
                        callbacks: {
                            label: (context) => {
                                let label = context.dataset.label || '';
                                if (label) label += ': ';
                                if (context.parsed.y !== null) {
                                    label += context.parsed.y.toFixed(2);
                                }
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: { 
                        title: { display: true, text: 'Time' },
                        grid: { display: true }
                    },
                    y: { 
                        beginAtZero: true, 
                        title: { display: true, text: 'Value' },
                        grid: { display: true }
                    }
                },
                interaction: { intersect: false, mode: 'nearest' },
                elements: {
                    point: {
                        radius: 2,
                        hoverRadius: 5
                    }
                }
            }
        });

        if (this.options.showLegend) {
            this.renderCustomLegend(datasets);
        }
    }

    // Prepare chart data from selected sensors
    prepareChartData() {
        if (!this.sensors || !Array.isArray(this.sensors)) return [];

        const datasets = [];
        let colorIndex = 0;

        this.sensors.forEach((sensor, index) => {
            const sensorId = this.getSensorId(sensor);
            
            if (!this.selectedSensors.has(sensorId)) return;

            const color = this.chartColors[colorIndex % this.chartColors.length];
            const sensorName = sensor.name || sensor.sensor_name || `Sensor ${index + 1}`;
            const readings = this.getSensorReadings(sensor);
            const unit = sensor.unit || '';
            
            datasets.push({
                label: `${sensorName}${unit ? ` (${unit})` : ''}`,
                data: readings,
                borderColor: color,
                backgroundColor: color + '20',
                tension: 0.4,
                fill: true,
                borderWidth: 2,
                pointBackgroundColor: color,
                pointBorderColor: '#fff',
                pointBorderWidth: 1
            });

            colorIndex++;
        });

        return datasets;
    }

    // Get sensor readings
    getSensorReadings(sensor) {
        if (sensor.history && Array.isArray(sensor.history)) {
            return sensor.history.map(item => 
                typeof item === 'number' ? item : item.value || 0
            ).filter(val => val !== null && val !== undefined);
        }
        
        if (sensor.readings && Array.isArray(sensor.readings)) {
            return sensor.readings.map(reading => reading.value || 0);
        }
        
        const currentVal = sensor.value || sensor.current_value || sensor.reading;
        return currentVal !== undefined ? [currentVal] : [];
    }

    // Generate time labels based on selected range
    generateTimeLabels() {
        const timeRange = document.getElementById(`${this.containerId}-timeRange`)?.value || this.options.timeRange;
        const labels = [];
        const now = new Date();
        let points = 24;
        
        switch (timeRange) {
            case '1h': points = 12; break;
            case '6h': points = 12; break;
            case '24h': points = 24; break;
            case '7d': points = 28; break;
            case '30d': points = 30; break;
        }
        
        for (let i = points - 1; i >= 0; i--) {
            const time = new Date(now.getTime() - (i * this.getTimeInterval(timeRange)));
            labels.push(this.formatTimeLabel(time, timeRange));
        }
        return labels;
    }

    getTimeInterval(timeRange) {
        switch (timeRange) {
            case '1h': return 5 * 60 * 1000;
            case '6h': return 30 * 60 * 1000;
            case '24h': return 60 * 60 * 1000;
            case '7d': return 6 * 60 * 60 * 1000;
            case '30d': return 24 * 60 * 60 * 1000;
            default: return 60 * 60 * 1000;
        }
    }

    formatTimeLabel(date, timeRange) {
        switch (timeRange) {
            case '1h':
            case '6h':
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            case '24h':
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            case '7d':
                return date.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit' });
            case '30d':
                return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
            default:
                return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
    }

    // Render custom legend
    renderCustomLegend(datasets) {
        const legendContainer = document.getElementById(`${this.containerId}-legend`);
        if (!legendContainer) return;

        if (!datasets || datasets.length === 0) {
            legendContainer.innerHTML = '<p class="text-muted text-center">No data to display</p>';
            return;
        }

        let html = '<div class="chart-legend">';
        
        datasets.forEach((dataset, index) => {
            const isVisible = this.chart?.isDatasetVisible?.(index) ?? true;
            html += `
                <div class="legend-item ${isVisible ? '' : 'hidden'}" 
                     data-dataset-index="${index}">
                    <span class="legend-color" style="background-color: ${dataset.borderColor};"></span>
                    <span class="legend-label">${dataset.label}</span>
                    <span class="legend-remove" title="Remove from chart">
                        <i class="fas fa-times"></i>
                    </span>
                </div>
            `;
        });

        html += '</div>';
        legendContainer.innerHTML = html;

        this.setupLegendEventListeners();
    }

    // Setup legend event listeners
    setupLegendEventListeners() {
        const legendItems = document.querySelectorAll(`#${this.containerId}-legend .legend-item`);
        
        legendItems.forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('legend-remove') || 
                    e.target.classList.contains('fa-times')) {
                    return;
                }
                
                const datasetIndex = parseInt(item.getAttribute('data-dataset-index'));
                if (this.chart) {
                    const meta = this.chart.getDatasetMeta(datasetIndex);
                    meta.hidden = meta.hidden === null ? !this.chart.data.datasets[datasetIndex].hidden : null;
                    this.chart.update();
                    item.classList.toggle('hidden', meta.hidden);
                }
            });

            const removeBtn = item.querySelector('.legend-remove');
            if (removeBtn) {
                removeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const datasetIndex = parseInt(item.getAttribute('data-dataset-index'));
                    const dataset = this.chart.data.datasets[datasetIndex];
                    
                    this.sensors.forEach(sensor => {
                        const sensorId = this.getSensorId(sensor);
                        const sensorName = sensor.name || sensor.sensor_name || '';
                        if (dataset.label.includes(sensorName)) {
                            this.selectedSensors.delete(sensorId);
                        }
                    });
                    
                    this.updateSensorSelectionMenu();
                    this.renderChart();
                });
            }
        });
    }

    // Setup event listeners
    setupEventListeners() {
        // Time range change
        const timeRangeSelect = document.getElementById(`${this.containerId}-timeRange`);
        if (timeRangeSelect) {
            timeRangeSelect.addEventListener('change', () => this.renderChart());
        }

        // Refresh button
        const refreshBtn = document.getElementById(`${this.containerId}-refreshBtn`);
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.renderChart());
        }

        // Sensor selection
        document.getElementById(`${this.containerId}-selectAll`)?.addEventListener('click', (e) => {
            e.preventDefault();
            this.selectAllSensors();
        });

        document.getElementById(`${this.containerId}-clearAll`)?.addEventListener('click', (e) => {
            e.preventDefault();
            this.clearAllSensors();
        });

        document.getElementById(`${this.containerId}-applySelection`)?.addEventListener('click', () => {
            this.applySensorSelection();
        });

        document.getElementById(`${this.containerId}-cancelSelection`)?.addEventListener('click', () => {
            const dropdown = document.getElementById(`${this.containerId}-sensorSelect`);
            if (dropdown) $(dropdown).dropdown('toggle');
        });
    }

    // Show loading state
    showLoading() {
        const container = document.getElementById(this.containerId);
        if (container) {
            container.classList.add('loading');
        }
    }

    // Hide loading state
    hideLoading() {
        const container = document.getElementById(this.containerId);
        if (container) {
            container.classList.remove('loading');
        }
    }

    // Show no data message
    showNoDataMessage() {
        const ctx = document.getElementById(`${this.containerId}-chart`);
        if (ctx) {
            ctx.innerHTML = `
                <div class="text-center text-muted py-5">
                    <i class="fas fa-chart-line fa-3x mb-3"></i>
                    <p>No sensor data available</p>
                    <small>Select sensors to display data</small>
                </div>
            `;
        }
    }

    // Show error message
    showError(message) {
        const container = document.getElementById(this.containerId);
        if (container) {
            const alert = document.createElement('div');
            alert.className = 'alert alert-danger alert-dismissible fade show';
            alert.innerHTML = `
                <strong>Error!</strong> ${message}
                <button type="button" class="close" data-dismiss="alert">
                    <span>&times;</span>
                </button>
            `;
            container.prepend(alert);
            setTimeout(() => alert.remove(), 5000);
        }
    }

    // Start auto refresh
    startAutoRefresh() {
        this.autoRefreshInterval = setInterval(() => {
            this.renderChart();
        }, this.options.refreshInterval);
    }

    // Stop auto refresh
    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }
    }

    // Update chart options
    updateOptions(newOptions) {
        this.options = { ...this.options, ...newOptions };
        this.renderContainer();
        this.setupEventListeners();
        this.renderChart();
    }

    // Destroy chart
    destroy() {
        this.stopAutoRefresh();
        if (this.chart) {
            this.chart.destroy();
        }
        const container = document.getElementById(this.containerId);
        if (container) {
            container.innerHTML = '';
        }
    }
}