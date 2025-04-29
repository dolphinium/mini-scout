// Mini Nightscout Frontend Script

// DOM Elements
const currentValueElement = document.getElementById('current-value');
const unitsElement = document.getElementById('units');
const trendArrowElement = document.getElementById('trend-arrow');
const timeAgoElement = document.getElementById('time-ago');
const refreshButton = document.getElementById('refresh-button');
const timeRangeSelect = document.getElementById('time-range');
const lastUpdateElement = document.getElementById('last-update');
const autoRefreshStatusElement = document.getElementById('auto-refresh-status');
const glucoseChartCanvas = document.getElementById('glucose-chart');

// Global variables
let glucoseChart = null;
let lastReadingTimestamp = null;
let autoRefreshInterval = null;
const AUTO_REFRESH_INTERVAL = 60000; // 60 seconds
let currentTimeRange = 24; // Default to 24 hours

// Initialize the application
function init() {
    // Set up event listeners
    refreshButton.addEventListener('click', manualRefresh);
    timeRangeSelect.addEventListener('change', handleTimeRangeChange);
    
    // Initial data load
    fetchLatestReading();
    fetchGlucoseData(currentTimeRange);
    
    // Set up auto-refresh
    startAutoRefresh();
}

// Start the auto-refresh interval
function startAutoRefresh() {
    // Clear any existing interval
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
    }
    
    // Set new interval
    autoRefreshInterval = setInterval(() => {
        fetchLatestReading();
        fetchGlucoseData(currentTimeRange);
    }, AUTO_REFRESH_INTERVAL);
    
    autoRefreshStatusElement.textContent = 'On';
}

// Stop the auto-refresh interval
function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
    
    autoRefreshStatusElement.textContent = 'Off';
}

// Handle manual refresh button click
function manualRefresh() {
    refreshButton.disabled = true;
    refreshButton.textContent = 'Refreshing...';
    
    // Trigger backend refresh
    fetch('/api/entries/refresh', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            console.log('Refresh triggered:', data);
            
            // Wait a moment for the backend to process
            setTimeout(() => {
                fetchLatestReading();
                fetchGlucoseData(currentTimeRange);
                refreshButton.disabled = false;
                refreshButton.textContent = 'Refresh Now';
            }, 2000);
        })
        .catch(error => {
            console.error('Error triggering refresh:', error);
            refreshButton.disabled = false;
            refreshButton.textContent = 'Refresh Now';
        });
}

// Handle time range change
function handleTimeRangeChange() {
    currentTimeRange = parseInt(timeRangeSelect.value);
    fetchGlucoseData(currentTimeRange);
}

// Fetch the latest glucose reading
function fetchLatestReading() {
    fetch('/api/entries/latest')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.reading) {
                updateLatestReading(data.reading, data.time_ago_seconds);
                updateLastUpdateTime();
            } else {
                console.warn('No readings available:', data.message);
                // Show empty state
                currentValueElement.textContent = '---';
                trendArrowElement.className = '';
                timeAgoElement.textContent = '--';
            }
        })
        .catch(error => {
            console.error('Error fetching latest reading:', error);
        });
}

// Fetch glucose data for the chart
function fetchGlucoseData(hours) {
    fetch(`/api/entries?hours=${hours}`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.entries && data.entries.length > 0) {
                updateChart(data.entries);
            } else {
                console.warn('No entries available for chart:', data.message);
                // Clear chart or show empty state
                if (glucoseChart) {
                    glucoseChart.data.labels = [];
                    glucoseChart.data.datasets[0].data = [];
                    glucoseChart.update();
                }
            }
        })
        .catch(error => {
            console.error('Error fetching glucose data:', error);
        });
}

// Update the latest reading display
function updateLatestReading(reading, timeAgoSeconds) {
    // Update value
    currentValueElement.textContent = reading.sgv;
    
    // Update color based on value
    if (reading.sgv < 70) {
        currentValueElement.className = 'low';
    } else if (reading.sgv >= 70 && reading.sgv <= 180) {
        currentValueElement.className = 'normal';
    } else if (reading.sgv > 180 && reading.sgv <= 250) {
        currentValueElement.className = 'high';
    } else {
        currentValueElement.className = 'very-high';
    }
    
    // Update trend arrow
    trendArrowElement.className = '';
    if (reading.direction) {
        const directionClass = mapDirectionToClass(reading.direction);
        trendArrowElement.className = directionClass;
    }
    
    // Update time ago
    const minutes = Math.floor(timeAgoSeconds / 60);
    timeAgoElement.textContent = minutes;
    
    // Save timestamp for reference
    lastReadingTimestamp = reading.timestamp;
}

// Update the chart with new data
function updateChart(entries) {
    // Process data for chart
    const labels = [];
    const dataPoints = [];
    
    // Sort entries by timestamp in ascending order
    entries.sort((a, b) => new Date(a.device_timestamp) - new Date(b.device_timestamp));
    
    // Extract data
    entries.forEach(entry => {
        const date = new Date(entry.device_timestamp);
        const timeLabel = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        labels.push(timeLabel);
        dataPoints.push(entry.sgv);
    });
    
    // Create or update chart
    if (glucoseChart) {
        // Update existing chart
        glucoseChart.data.labels = labels;
        glucoseChart.data.datasets[0].data = dataPoints;
        glucoseChart.update();
    } else {
        // Create new chart
        glucoseChart = new Chart(glucoseChartCanvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Glucose (mg/dL)',
                    data: dataPoints,
                    fill: false,
                    borderColor: '#3b7ddd',
                    tension: 0.1,
                    pointBackgroundColor: function(context) {
                        const value = context.dataset.data[context.dataIndex];
                        if (value < 70) return '#dc3545'; // Low
                        if (value > 180) return '#ffc107'; // High
                        return '#28a745'; // Normal
                    }
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: false,
                        suggestedMin: 40,
                        suggestedMax: 300,
                        grid: {
                            color: function(context) {
                                if (context.tick.value === 70) return '#dc3545'; // Low line
                                if (context.tick.value === 180) return '#ffc107'; // High line
                                return '#e9e9e9'; // Default grid color
                            },
                            lineWidth: function(context) {
                                if (context.tick.value === 70 || context.tick.value === 180) return 2;
                                return 1;
                            },
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            title: function(tooltipItems) {
                                const idx = tooltipItems[0].dataIndex;
                                const date = new Date(entries[idx].device_timestamp);
                                return date.toLocaleString();
                            }
                        }
                    }
                }
            }
        });
    }
}

// Update the "Last Update" time
function updateLastUpdateTime() {
    const now = new Date();
    lastUpdateElement.textContent = now.toLocaleTimeString();
}

// Map direction strings to CSS classes
function mapDirectionToClass(direction) {
    const directionMap = {
        'DoubleUp': 'trend-doubleup',
        'SingleUp': 'trend-singleup',
        'FortyFiveUp': 'trend-fortyfiveup',
        'Flat': 'trend-flat',
        'FortyFiveDown': 'trend-fortyfivedown',
        'SingleDown': 'trend-singledown',
        'DoubleDown': 'trend-doubledown',
        'NONE': ''
    };
    
    return directionMap[direction] || '';
}

// Start the application when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', init);