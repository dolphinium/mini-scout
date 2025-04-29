// Constants and Configuration
const DEFAULT_SETTINGS = {
    lowRange: 70,  // mg/dL
    highRange: 180, // mg/dL
    refreshInterval: 60, // seconds
    chartHours: 12 // hours of data to display
};

// Store current settings
let settings = { ...DEFAULT_SETTINGS };

// Chart instance
let glucoseChart = null;

// Track if we've loaded data successfully
let dataLoaded = false;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    // Load saved settings from localStorage
    loadSettings();
    
    // Initialize UI
    initChart();
    setupEventListeners();
    
    // Load data for the first time
    fetchLatestReading();
    fetchGlucoseData(settings.chartHours);
    fetchStats(settings.chartHours);
    
    // Set up auto-refresh
    setInterval(() => {
        fetchLatestReading();
        fetchGlucoseData(settings.chartHours);
        fetchStats(settings.chartHours);
    }, settings.refreshInterval * 1000);
    
    // Update "time ago" every minute
    setInterval(updateTimeAgo, 60000);
});

// Initialize Chart.js
function initChart() {
    const ctx = document.getElementById('glucose-chart').getContext('2d');
    
    // Create gradient for chart
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, 'rgba(50, 115, 220, 0.3)');
    gradient.addColorStop(1, 'rgba(50, 115, 220, 0)');
    
    glucoseChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Glucose',
                data: [],
                borderColor: '#3273dc',
                backgroundColor: gradient,
                borderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                pointBackgroundColor: '#3273dc',
                tension: 0.3,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            return `Glucose: ${context.parsed.y} mg/dL`;
                        }
                    }
                },
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'HH:mm'
                        }
                    },
                    title: {
                        display: false
                    }
                },
                y: {
                    min: 40,
                    max: 300,
                    title: {
                        display: true,
                        text: 'mg/dL'
                    },
                    grid: {
                        color: function(context) {
                            if (context.tick.value === settings.lowRange || 
                                context.tick.value === settings.highRange) {
                                return 'rgba(255, 0, 0, 0.2)';
                            }
                            return 'rgba(0, 0, 0, 0.1)';
                        },
                        lineWidth: function(context) {
                            if (context.tick.value === settings.lowRange || 
                                context.tick.value === settings.highRange) {
                                return 2;
                            }
                            return 1;
                        }
                    }
                }
            }
        }
    });
}

// Set up event listeners
function setupEventListeners() {
    // Time range buttons
    document.querySelectorAll('.time-button').forEach(button => {
        button.addEventListener('click', function() {
            const hours = parseInt(this.dataset.hours);
            settings.chartHours = hours;
            
            // Update active button
            document.querySelectorAll('.time-button').forEach(btn => {
                btn.classList.remove('active');
            });
            this.classList.add('active');
            
            // Fetch new data for the selected time range
            fetchGlucoseData(hours);
            fetchStats(hours);
            
            // Save settings
            saveSettings();
        });
    });
    
    // Settings button
    document.getElementById('settings-button').addEventListener('click', function() {
        // Show settings modal
        document.getElementById('settings-modal').style.display = 'block';
        
        // Populate form with current settings
        document.getElementById('range-low').value = settings.lowRange;
        document.getElementById('range-high').value = settings.highRange;
        document.getElementById('refresh-interval').value = settings.refreshInterval;
    });
    
    // Close settings modal
    document.querySelector('.close-button').addEventListener('click', function() {
        document.getElementById('settings-modal').style.display = 'none';
    });
    
    // Save settings
    document.getElementById('save-settings').addEventListener('click', function() {
        // Get values from form
        const lowRange = parseInt(document.getElementById('range-low').value);
        const highRange = parseInt(document.getElementById('range-high').value);
        const refreshInterval = parseInt(document.getElementById('refresh-interval').value);
        
        // Validate
        if (lowRange >= highRange) {
            alert('Low range must be less than high range');
            return;
        }
        
        if (refreshInterval < 30) {
            alert('Refresh interval must be at least 30 seconds');
            return;
        }
        
        // Update settings
        settings.lowRange = lowRange;
        settings.highRange = highRange;
        settings.refreshInterval = refreshInterval;
        
        // Save settings
        saveSettings();
        
        // Update chart
        updateChartRanges();
        
        // Close modal
        document.getElementById('settings-modal').style.display = 'none';
    });
    
    // Close modal when clicking outside
    window.addEventListener('click', function(event) {
        const modal = document.getElementById('settings-modal');
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
}

// Load settings from localStorage
function loadSettings() {
    const savedSettings = localStorage.getItem('miniNightscoutSettings');
    if (savedSettings) {
        try {
            const parsed = JSON.parse(savedSettings);
            settings = { ...DEFAULT_SETTINGS, ...parsed };
            
            // Set active time range button
            document.querySelectorAll('.time-button').forEach(btn => {
                if (parseInt(btn.dataset.hours) === settings.chartHours) {
                    btn.classList.add('active');
                } else {
                    btn.classList.remove('active');
                }
            });
        } catch (e) {
            console.error('Error loading settings:', e);
            settings = { ...DEFAULT_SETTINGS };
        }
    }
}

// Save settings to localStorage
function saveSettings() {
    localStorage.setItem('miniNightscoutSettings', JSON.stringify(settings));
}

// Update chart range lines
function updateChartRanges() {
    if (glucoseChart) {
        glucoseChart.options.scales.y.grid.color = function(context) {
            if (context.tick.value === settings.lowRange || 
                context.tick.value === settings.highRange) {
                return 'rgba(255, 0, 0, 0.2)';
            }
            return 'rgba(0, 0, 0, 0.1)';
        };
        
        glucoseChart.update();
    }
}

// Fetch latest glucose reading
async function fetchLatestReading() {
    try {
        const response = await fetch('/api/entries/latest');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update UI with latest reading
        updateLatestReading(data);
        
        // Update status indicator
        updateStatusOnline();
        
    } catch (error) {
        console.error('Error fetching latest reading:', error);
        updateStatusOffline();
    }
}

// Fetch glucose data for the chart
async function fetchGlucoseData(hours) {
    try {
        const response = await fetch(`/api/entries?hours=${hours}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update chart with data
        updateGlucoseChart(data.readings);
        
        // Mark data as loaded
        dataLoaded = true;
        
    } catch (error) {
        console.error('Error fetching glucose data:', error);
    }
}

// Fetch statistics
async function fetchStats(hours) {
    try {
        const response = await fetch(`/api/entries/stats?hours=${hours}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update stats in UI
        updateStats(data);
        
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

// Update the latest reading in the UI
function updateLatestReading(data) {
    const valueElement = document.getElementById('latest-value');
    const trendElement = document.getElementById('trend-arrow');
    const timeAgoElement = document.getElementById('time-ago');
    const readingTimeElement = document.getElementById('reading-time');
    
    // Update value with color based on range
    valueElement.textContent = Math.round(data.value);
    updateGlucoseValueColor(valueElement, data.value);
    
    // Update trend arrow
    trendElement.textContent = getTrendArrow(data.trend);
    updateTrendArrowClass(trendElement, data.trend);
    
    // Update time information
    const readingTime = new Date(data.timestamp);
    
    // Format time
    const formattedTime = readingTime.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit'
    });
    readingTimeElement.textContent = formattedTime;
    
    // Time ago
    const minutesAgo = data.time_ago_minutes;
    if (minutesAgo !== null) {
        timeAgoElement.textContent = formatTimeAgo(minutesAgo);
    } else {
        timeAgoElement.textContent = 'Unknown';
    }
    
    // Store timestamp for time ago updates
    if (data.timestamp) {
        timeAgoElement.dataset.timestamp = data.timestamp;
    }
}

// Update the glucose chart
function updateGlucoseChart(readings) {
    if (!glucoseChart) return;
    
    // Prepare data for chart (newest to oldest)
    const chartData = readings.map(reading => ({
        x: new Date(reading.timestamp),
        y: reading.value
    })).reverse();  // Reverse to get chronological order
    
    // Update chart data
    glucoseChart.data.datasets[0].data = chartData;
    
    // Get min and max values with padding
    let minValue = Math.min(...chartData.map(d => d.y));
    let maxValue = Math.max(...chartData.map(d => d.y));
    
    // Add padding (10% of range)
    const padding = Math.max(10, (maxValue - minValue) * 0.1);
    minValue = Math.max(40, Math.floor(minValue - padding / 2));
    maxValue = Math.min(400, Math.ceil(maxValue + padding / 2));
    
    // Update scale
    glucoseChart.options.scales.y.min = minValue;
    glucoseChart.options.scales.y.max = maxValue;
    
    // Update chart
    glucoseChart.update();
}

// Update statistics in the UI
function updateStats(data) {
    document.getElementById('average-value').textContent = data.average;
    document.getElementById('time-in-range').textContent = `${data.time_in_range_percent}%`;
    document.getElementById('readings-count').textContent = data.count;
}

// Update the online/offline status indicator
function updateStatusOnline() {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const lastUpdate = document.getElementById('last-update');
    
    statusDot.classList.remove('offline');
    statusDot.classList.add('online');
    statusText.textContent = 'Online';
    
    const now = new Date();
    lastUpdate.textContent = `Last update: ${now.toLocaleTimeString()}`;
}

// Update the status to offline
function updateStatusOffline() {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    
    statusDot.classList.remove('online');
    statusDot.classList.add('offline');
    statusText.textContent = 'Offline';
}

// Update the time ago text for latest reading
function updateTimeAgo() {
    const timeAgoElement = document.getElementById('time-ago');
    const timestamp = timeAgoElement.dataset.timestamp;
    
    if (timestamp) {
        const readingTime = new Date(timestamp);
        const now = new Date();
        const minutesAgo = (now - readingTime) / (1000 * 60);
        
        timeAgoElement.textContent = formatTimeAgo(minutesAgo);
    }
}

// Format time ago text
function formatTimeAgo(minutesAgo) {
    if (minutesAgo < 1) {
        return 'Just now';
    } else if (minutesAgo < 60) {
        const minutes = Math.floor(minutesAgo);
        return `${minutes} ${minutes === 1 ? 'minute' : 'minutes'} ago`;
    } else {
        const hours = Math.floor(minutesAgo / 60);
        const minutes = Math.floor(minutesAgo % 60);
        return `${hours} ${hours === 1 ? 'hour' : 'hours'}${minutes ? `, ${minutes} min` : ''} ago`;
    }
}

// Get a trend arrow symbol based on trend direction
function getTrendArrow(trend) {
    if (!trend) return '';
    
    // Map LibreLink Up trend values to arrows
    switch (trend) {
        case 'Rising':
        case 'RisingQuickly':
            return '↑';
        case 'RisingSlightly':
            return '↗';
        case 'Stable':
            return '→';
        case 'FallingSlightly':
            return '↘';
        case 'Falling':
        case 'FallingQuickly':
            return '↓';
        default:
            return '';
    }
}

// Update trend arrow class for styling
function updateTrendArrowClass(element, trend) {
    element.classList.remove('trend-up', 'trend-down', 'trend-stable');
    
    if (!trend) return;
    
    if (trend.includes('Rising')) {
        element.classList.add('trend-up');
    } else if (trend.includes('Falling')) {
        element.classList.add('trend-down');
    } else if (trend === 'Stable') {
        element.classList.add('trend-stable');
    }
}

// Update glucose value color based on range
function updateGlucoseValueColor(element, value) {
    element.classList.remove('glucose-high', 'glucose-normal', 'glucose-low');
    
    if (value > settings.highRange) {
        element.classList.add('glucose-high');
    } else if (value < settings.lowRange) {
        element.classList.add('glucose-low');
    } else {
        element.classList.add('glucose-normal');
    }
}