// Chart data will be injected via template variables
let houseNames, houseColors, climbingData, standingData, stepsData, combinedData;
let climbBarChart, standingBarChart, stepsBarChart, combinedBarChart;
let climbPieChart, standingPieChart, stepsPieChart, combinedPieChart;

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    // Set Chart.js defaults
    Chart.defaults.font.family = "'Arial', 'sans-serif'";
    Chart.defaults.font.size = 14;
    Chart.defaults.animation.duration = 1000;
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;
    
    try {
        // More robust pattern fallback
        window.pattern = window.pattern || {
            draw: function(type, color) {
                console.warn('Patternomaly library not loaded, using solid colors');
                return color; // Fallback to solid color if patterns not available
            }
        };
        
        // Set initial state with clear display settings
        document.getElementById('barChartsSection').style.display = 'block';
        document.getElementById('pieChartsSection').style.display = 'none';
        
        // Hide all chart containers first
        const chartContainers = document.querySelectorAll('.chart-container');
        chartContainers.forEach(container => {
            container.style.display = 'none';
        });
        
        // Then show only the initial ones
        document.getElementById('climbBarChartContainer').style.display = 'block';
        document.getElementById('climbPieChartContainer').style.display = 'block';
        
        // Initialize button states
        updateDataButtonStyles('climbDataBtn');
        document.getElementById('barChartBtn').classList.add('active');
        document.getElementById('barChartBtn').classList.add('btn-primary');
        document.getElementById('barChartBtn').classList.remove('btn-outline-primary');
        document.getElementById('pieChartBtn').classList.remove('active');
        
        // Create charts with error handling
        try {
            createBarCharts();
            createPieCharts();
        } catch (error) {
            console.error('Error creating charts:', error);
            console.log('Chart data:', { houseNames, houseColors, climbingData, standingData, stepsData, combinedData });
            displayChartError('There was an error creating the charts. Please try refreshing the page.');
        }
        
        // Event listeners for chart toggles
        document.getElementById('barChartBtn').addEventListener('click', function() {
            toggleChartType('bar');
        });
        
        document.getElementById('pieChartBtn').addEventListener('click', function() {
            toggleChartType('pie');
        });
        
        // Data type button event listeners
        document.getElementById('climbDataBtn').addEventListener('click', function() {
            toggleDataType('climb');
        });

        document.getElementById('standingDataBtn').addEventListener('click', function() {
            toggleDataType('standing');
        });

        document.getElementById('stepsDataBtn').addEventListener('click', function() {
            toggleDataType('steps');
        });

        document.getElementById('combinedDataBtn').addEventListener('click', function() {
            toggleDataType('combined');
        });
    } catch (error) {
        console.error('Error initializing analytics dashboard:', error);
        displayChartError('Failed to initialize analytics dashboard. Please try refreshing the page.');
    }
});

// Check if data exists
function hasData(dataArray) {
    if (!Array.isArray(dataArray)) return false;
    return dataArray.length > 0 && dataArray.some(val => val > 0);
}

// Validate chart data
function validateChartData() {
    let isValid = true;
    let debugInfo = "";
    
    try {
        // Check house names
        if (!Array.isArray(houseNames) || houseNames.length === 0) {
            debugInfo += "House names data is invalid or empty\n";
            houseNames = ['No Data'];
            isValid = false;
        } else {
            debugInfo += `Found ${houseNames.length} houses: ${houseNames.join(', ')}\n`;
        }
        
        // Check house colors
        if (!Array.isArray(houseColors) || houseColors.length === 0) {
            debugInfo += "House colors data is invalid or empty\n";
            houseColors = ['rgba(200, 200, 200, 0.7)'];
            isValid = false;
        } else {
            debugInfo += `Found ${houseColors.length} house colors\n`;
        }
        
        // Check climbing data
        if (!climbingData || typeof climbingData !== 'object') {
            debugInfo += "Missing climbing data\n";
            climbingData = {flights: [0], points: [0]};
            isValid = false;
        } else {
            debugInfo += `Climbing data - Flights: ${JSON.stringify(climbingData.flights)}\n`;
            debugInfo += `Climbing data - Points: ${JSON.stringify(climbingData.points)}\n`;
        }
        
        // Check standing data
        if (!standingData || typeof standingData !== 'object') {
            debugInfo += "Missing standing data\n";
            standingData = {minutes: [0], points: [0]};
            isValid = false;
        } else {
            debugInfo += `Standing data - Minutes: ${JSON.stringify(standingData.minutes)}\n`;
            debugInfo += `Standing data - Points: ${JSON.stringify(standingData.points)}\n`;
        }
        
        // Check steps data
        if (!stepsData || typeof stepsData !== 'object') {
            debugInfo += "Missing steps data\n";
            stepsData = {steps: [0], points: [0]};
            isValid = false;
        } else {
            debugInfo += `Steps data - Steps: ${JSON.stringify(stepsData.steps)}\n`;
            debugInfo += `Steps data - Points: ${JSON.stringify(stepsData.points)}\n`;
        }
        
        // Check combined data
        if (!combinedData || typeof combinedData !== 'object') {
            debugInfo += "Missing combined data\n";
            combinedData = {
                climbing_points: [0],
                standing_points: [0],
                steps_points: [0],
                total_points: [0]
            };
            isValid = false;
        } else {
            debugInfo += `Combined data - Total Points: ${JSON.stringify(combinedData.total_points)}\n`;
        }
        
        // Check that all arrays are the same length
        if (houseNames.length !== houseColors.length) {
            debugInfo += "Warning: House names and colors arrays have different lengths!\n";
        }
        
        // Set debug information if debug element exists
        const debugDataEl = document.getElementById('debugData');
        const debugMessageEl = document.getElementById('debugMessage');
        const debugInfoEl = document.getElementById('debugInfo');
        
        if (debugDataEl && debugMessageEl && debugInfoEl) {
            debugDataEl.textContent = debugInfo;
            
            if (!isValid) {
                debugMessageEl.textContent = "Chart data appears to be incomplete or invalid. See details below:";
                debugInfoEl.style.display = 'block';
            }
        }
        
        return isValid;
    } catch (error) {
        console.error('Error validating chart data:', error);
        if (document.getElementById('debugMessage') && document.getElementById('debugInfo')) {
            document.getElementById('debugMessage').textContent = `Error validating chart data: ${error.message}`;
            document.getElementById('debugInfo').style.display = 'block';
        }
        return false;
    }
}

// Create bar charts
function createBarCharts() {
    try {
        // Validate data before creating charts
        validateChartData();
        
        // More robust error handling for missing data
        if (!climbingData) {
            console.error('Missing climbing data');
            climbingData = {flights: [], points: []};
        }
        if (!standingData) {
            console.error('Missing standing data');
            standingData = {minutes: [], points: []};
        }
        if (!stepsData) {
            console.error('Missing steps data');
            stepsData = {steps: [], points: []};
        }
        if (!combinedData) {
            console.error('Missing combined data');
            combinedData = {
                climbing_points: [],
                standing_points: [],
                steps_points: [],
                total_points: []
            };
        }
        
        // Ensure all required data points exist
        if (!combinedData.steps_points) {
            combinedData.steps_points = stepsData.points || [];
        }
        
        // Climbing bar chart
        const climbCtx = document.getElementById('climbBarChart').getContext('2d');
        climbBarChart = new Chart(climbCtx, {
            type: 'bar',
            data: {
                labels: houseNames,
                datasets: [{
                    label: 'Points',
                    data: climbingData.points,
                    backgroundColor: houseColors,
                    borderColor: houseColors.map(color => color.replace('0.7', '1')),
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Points'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Houses'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Climbing Points by House',
                        font: {
                            size: 18
                        }
                    },
                    legend: {
                        display: false
                    }
                }
            }
        });

        if (!hasData(climbingData.points)) {
            // Add a "No Data" label to the chart
            const noDataLabel = document.createElement('div');
            noDataLabel.className = 'text-center text-muted py-5';
            noDataLabel.textContent = 'No climbing data available';
            document.getElementById('climbBarChartContainer').appendChild(noDataLabel);
        }
        
        // Standing bar chart
        const standingCtx = document.getElementById('standingBarChart').getContext('2d');
        standingBarChart = new Chart(standingCtx, {
            type: 'bar',
            data: {
                labels: houseNames,
                datasets: [{
                    label: 'Points',
                    data: standingData.points,
                    backgroundColor: houseColors,
                    borderColor: houseColors.map(color => color.replace('0.7', '1')),
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Points'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Houses'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Standing Points by House',
                        font: {
                            size: 18
                        }
                    },
                    legend: {
                        display: false
                    }
                }
            }
        });
        
        // Steps bar chart
        const stepsCtx = document.getElementById('stepsBarChart').getContext('2d');
        stepsBarChart = new Chart(stepsCtx, {
            type: 'bar',
            data: {
                labels: houseNames,
                datasets: [{
                    label: 'Points',
                    data: stepsData.points,
                    backgroundColor: houseColors,
                    borderColor: houseColors.map(color => color.replace('0.7', '1')),
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Points'
                        }
                    },
                    x: {
                        title: {
                            display: true,
                            text: 'Houses'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Steps Points by House',
                        font: {
                            size: 18
                        }
                    },
                    legend: {
                        display: false
                    }
                }
            }
        });
        
        // Combined bar chart
        const combinedCtx = document.getElementById('combinedBarChart').getContext('2d');
        
        // Create patterns for each house color
        const climbingPatterns = houseColors.map(color => pattern.draw('cross', color));
        const standingPatterns = houseColors.map(color => pattern.draw('line-vertical', color));
        const stepsPatterns = houseColors.map(color => pattern.draw('diagonal', color));
        
        combinedBarChart = new Chart(combinedCtx, {
            type: 'bar',
            data: {
                labels: houseNames,
                datasets: [{
                    label: 'Climbing Points (Cross)',
                    data: combinedData.climbing_points,
                    backgroundColor: climbingPatterns,
                    borderColor: houseColors,
                    borderWidth: 1
                }, {
                    label: 'Standing Points (Vertical)',
                    data: combinedData.standing_points,
                    backgroundColor: standingPatterns,
                    borderColor: houseColors,
                    borderWidth: 1
                }, {
                    label: 'Steps Points (Diagonal)',
                    data: combinedData.steps_points,
                    backgroundColor: stepsPatterns,
                    borderColor: houseColors,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        stacked: true,
                        title: {
                            display: true,
                            text: 'Points'
                        }
                    },
                    x: {
                        stacked: true,
                        title: {
                            display: true,
                            text: 'Houses'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Combined Points by House',
                        font: {
                            size: 18
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error creating bar charts:', error);
        // Add fallback display for errors
        document.querySelectorAll('[id$="BarChartContainer"]').forEach(container => {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'alert alert-danger';
            errorDiv.textContent = 'Error loading chart. Please try refreshing the page.';
            container.querySelector('.stats-card').appendChild(errorDiv);
        });
    }
}

// Create pie charts
function createPieCharts() {
    validateChartData();
    
    // Climbing pie chart
    const climbPieCtx = document.getElementById('climbPieChart').getContext('2d');
    climbPieChart = new Chart(climbPieCtx, {
        type: 'pie',
        data: {
            labels: houseNames,
            datasets: [{
                data: climbingData.points,
                backgroundColor: houseColors,
                borderColor: '#fff',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Climbing Points Distribution',
                    font: {
                        size: 18
                    }
                },
                legend: {
                    position: 'right'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: ${value} points (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });

    // Standing pie chart
    const standingPieCtx = document.getElementById('standingPieChart').getContext('2d');
    standingPieChart = new Chart(standingPieCtx, {
        type: 'pie',
        data: {
            labels: houseNames,
            datasets: [{
                data: standingData.points,
                backgroundColor: houseColors,
                borderColor: '#fff',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Standing Points Distribution',
                    font: {
                        size: 18
                    }
                },
                legend: {
                    position: 'right'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: ${value} points (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });

    // Steps pie chart
    const stepsPieCtx = document.getElementById('stepsPieChart').getContext('2d');
    stepsPieChart = new Chart(stepsPieCtx, {
        type: 'pie',
        data: {
            labels: houseNames,
            datasets: [{
                data: stepsData.points,
                backgroundColor: houseColors,
                borderColor: '#fff',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Steps Points Distribution',
                    font: {
                        size: 18
                    }
                },
                legend: {
                    position: 'right'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: ${value} points (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });

    // Combined pie chart
    const combinedPieCtx = document.getElementById('combinedPieChart').getContext('2d');
    combinedPieChart = new Chart(combinedPieCtx, {
        type: 'pie',
        data: {
            labels: houseNames,
            datasets: [{
                data: combinedData.total_points,
                backgroundColor: houseColors,
                borderColor: '#fff',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Total Points Distribution',
                    font: {
                        size: 18
                    }
                },
                legend: {
                    position: 'right'
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: ${value} points (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Toggle chart type (bar vs pie)
function toggleChartType(type) {
    // First destroy all charts
    destroyAllCharts();
    
    if (type === 'bar') {
        document.getElementById('barChartsSection').style.display = 'block';
        document.getElementById('pieChartsSection').style.display = 'none';
        
        // Update button styles
        document.getElementById('barChartBtn').classList.add('active');
        document.getElementById('barChartBtn').classList.remove('btn-outline-primary');
        document.getElementById('barChartBtn').classList.add('btn-primary');
        document.getElementById('pieChartBtn').classList.remove('active');
        document.getElementById('pieChartBtn').classList.add('btn-outline-primary');
        document.getElementById('pieChartBtn').classList.remove('btn-primary');
    } else {
        document.getElementById('barChartsSection').style.display = 'none';
        document.getElementById('pieChartsSection').style.display = 'block';
        
        // Update button styles
        document.getElementById('pieChartBtn').classList.add('active');
        document.getElementById('pieChartBtn').classList.remove('btn-outline-primary');
        document.getElementById('pieChartBtn').classList.add('btn-primary');
        document.getElementById('barChartBtn').classList.remove('active');
        document.getElementById('barChartBtn').classList.add('btn-outline-primary');
        document.getElementById('barChartBtn').classList.remove('btn-primary');
    }
    
    // Get active data type
    const activeDataBtn = document.querySelector('.btn-group .btn-success.active');
    const dataType = activeDataBtn ? activeDataBtn.id.replace('DataBtn', '') : 'climb';
    
    // Hide all chart containers
    document.querySelectorAll('.chart-container').forEach(container => {
        container.style.display = 'none';
    });
    
    // Show the appropriate container
    document.getElementById(`${dataType}${type.charAt(0).toUpperCase() + type.slice(1)}ChartContainer`).style.display = 'block';
    
    // Recreate charts
    createBarCharts();
    createPieCharts();
}

// Toggle data type (climbing, standing, steps, combined)
function toggleDataType(type) {
    // Hide all chart containers
    document.querySelectorAll('.chart-container').forEach(container => {
        container.style.display = 'none';
    });
    
    // Determine which chart type is active
    const isBarActive = document.getElementById('barChartBtn').classList.contains('active');
    const chartType = isBarActive ? 'Bar' : 'Pie';
    
    // Show the appropriate container
    document.getElementById(`${type}${chartType}ChartContainer`).style.display = 'block';
    
    // Update button styles
    updateDataButtonStyles(`${type}DataBtn`);
}

// Destroy all charts before recreating
function destroyAllCharts() {
    if (climbBarChart) climbBarChart.destroy();
    if (standingBarChart) standingBarChart.destroy();
    if (stepsBarChart) stepsBarChart.destroy();
    if (combinedBarChart) combinedBarChart.destroy();
    if (climbPieChart) climbPieChart.destroy();
    if (standingPieChart) standingPieChart.destroy();
    if (stepsPieChart) stepsPieChart.destroy();
    if (combinedPieChart) combinedPieChart.destroy();
}

// Update data button styles
function updateDataButtonStyles(activeId) {
    const buttons = ['climbDataBtn', 'standingDataBtn', 'stepsDataBtn', 'combinedDataBtn'];
    buttons.forEach(id => {
        const btn = document.getElementById(id);
        if (id === activeId) {
            btn.classList.add('active');
            btn.classList.remove('btn-outline-success');
            btn.classList.add('btn-success');
        } else {
            btn.classList.remove('active');
            btn.classList.add('btn-outline-success');
            btn.classList.remove('btn-success');
        }
    });
}

// Display chart error
function displayChartError(message) {
    document.querySelectorAll('.chart-container').forEach(container => {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.textContent = message;
        container.querySelector('.stats-card').appendChild(errorDiv);
    });
}