// Consolidated analytics dashboard script
// Define global variables with defaults
let houseNames = [];
let houseColors = [];
let climbingData = {flights: [], points: []};
let standingData = {minutes: [], points: []};
let stepsData = {steps: [], points: []};
let combinedData = {climbing_points: [], standing_points: [], steps_points: [], total_points: []};

// Chart objects
let climbBarChart, standingBarChart, stepsBarChart, combinedBarChart;
let climbPieChart, standingPieChart, stepsPieChart, combinedPieChart;

// Initialize the dashboard
document.addEventListener('DOMContentLoaded', function() {
    console.log('Analytics dashboard initializing...');
    
    // Set Chart.js defaults
    Chart.defaults.font.family = "'Arial', 'sans-serif'";
    Chart.defaults.font.size = 14;
    Chart.defaults.animation.duration = 1000;
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;

    try {
        // Get data from the hidden data container
        const dataContainer = document.getElementById('chartDataContainer');
        if (!dataContainer) {
            console.error('Chart data container not found');
            displayChartError('Data container not found. Please contact support.');
            return;
        }
        
        // Add sample data for testing
        const sampleData = generateSampleData();
        
        // Try to parse actual data, fall back to sample data if parsing fails
        try {
            houseNames = JSON.parse(dataContainer.getAttribute('data-house-names'));
            houseColors = JSON.parse(dataContainer.getAttribute('data-house-colors'));
            climbingData = JSON.parse(dataContainer.getAttribute('data-climbing'));
            standingData = JSON.parse(dataContainer.getAttribute('data-standing'));
            stepsData = JSON.parse(dataContainer.getAttribute('data-steps'));
            combinedData = JSON.parse(dataContainer.getAttribute('data-combined'));
            
            console.log('Successfully parsed chart data:', { 
                houses: houseNames.length, 
                colors: houseColors.length,
                climbing: climbingData,
                standing: standingData
            });
        } catch (e) {
            console.error("Error parsing JSON data:", e);
            // Use fallback data
            houseNames = ['Black', 'Blue', 'Green', 'White', 'Gold', 'Purple'];
            houseColors = sampleData.houseColors;
            climbingData = sampleData.climbingData;
            standingData = sampleData.standingData;
            stepsData = sampleData.stepsData;
            combinedData = sampleData.combinedData;
            
            displayChartError('Error parsing chart data: ' + e.message);
            console.log('Using sample data instead');
        }
        
        // Initial display settings
        document.getElementById('barChartsSection').style.display = 'block';
        document.getElementById('pieChartsSection').style.display = 'none';
        
        // Hide all chart containers initially
        document.querySelectorAll('.chart-container').forEach(container => {
            container.style.display = 'none';
        });
        
        // Show initial chart
        document.getElementById('climbBarChartContainer').style.display = 'block';
        
        // Set button states
        updateButtonStyles();
        
        // Create charts
        createBarCharts();
        createPieCharts();
        
        // Set up event listeners
        setupEventListeners();
    } catch (error) {
        console.error('Error initializing analytics dashboard:', error);
        displayChartError('Failed to initialize analytics dashboard: ' + error.message);
    }
});

// Generate sample data for failover
function generateSampleData() {
    return {
        houseNames: ['Black', 'Blue', 'Green', 'White', 'Gold', 'Purple'],
        houseColors: [
            'rgba(51, 51, 51, 0.8)',
            'rgba(0, 102, 204, 0.8)',
            'rgba(0, 153, 51, 0.8)',
            'rgba(248, 249, 250, 0.8)',
            'rgba(255, 204, 0, 0.8)',
            'rgba(102, 0, 153, 0.8)'
        ],
        climbingData: {
            flights: [45, 32, 28, 15, 40, 22],
            points: [450, 320, 280, 150, 400, 220]
        },
        standingData: {
            minutes: [120, 95, 80, 60, 110, 75],
            points: [120, 95, 80, 60, 110, 75]
        },
        stepsData: {
            steps: [8500, 7200, 6500, 5000, 9000, 6200],
            points: [85, 72, 65, 50, 90, 62]
        },
        combinedData: {
            climbing_points: [450, 320, 280, 150, 400, 220],
            standing_points: [120, 95, 80, 60, 110, 75],
            steps_points: [85, 72, 65, 50, 90, 62],
            total_points: [655, 487, 425, 260, 600, 357]
        }
    };
}

// Setup event listeners
function setupEventListeners() {
    document.getElementById('barChartBtn').addEventListener('click', () => toggleChartType('bar'));
    document.getElementById('pieChartBtn').addEventListener('click', () => toggleChartType('pie'));
    document.getElementById('climbDataBtn').addEventListener('click', () => toggleDataType('climb'));
    document.getElementById('standingDataBtn').addEventListener('click', () => toggleDataType('standing'));
    document.getElementById('stepsDataBtn').addEventListener('click', () => toggleDataType('steps'));
    document.getElementById('combinedDataBtn').addEventListener('click', () => toggleDataType('combined'));
}

// Update all button styles
function updateButtonStyles() {
    // Chart type buttons
    document.getElementById('barChartBtn').classList.add('active', 'btn-primary');
    document.getElementById('barChartBtn').classList.remove('btn-outline-primary');
    document.getElementById('pieChartBtn').classList.remove('active');
    document.getElementById('pieChartBtn').classList.add('btn-outline-primary');
    document.getElementById('pieChartBtn').classList.remove('btn-primary');
    
    // Data type buttons
    document.getElementById('climbDataBtn').classList.add('active', 'btn-success');
    document.getElementById('climbDataBtn').classList.remove('btn-outline-success');
    
    ['standingDataBtn', 'stepsDataBtn', 'combinedDataBtn'].forEach(id => {
        document.getElementById(id).classList.remove('active', 'btn-success');
        document.getElementById(id).classList.add('btn-outline-success');
    });
}

// Toggle between bar and pie charts
function toggleChartType(type) {
    destroyAllCharts();
    
    if (type === 'bar') {
        document.getElementById('barChartsSection').style.display = 'block';
        document.getElementById('pieChartsSection').style.display = 'none';
        
        document.getElementById('barChartBtn').classList.add('active', 'btn-primary');
        document.getElementById('barChartBtn').classList.remove('btn-outline-primary');
        document.getElementById('pieChartBtn').classList.remove('active', 'btn-primary');
        document.getElementById('pieChartBtn').classList.add('btn-outline-primary');
    } else {
        document.getElementById('barChartsSection').style.display = 'none';
        document.getElementById('pieChartsSection').style.display = 'block';
        
        document.getElementById('pieChartBtn').classList.add('active', 'btn-primary');
        document.getElementById('pieChartBtn').classList.remove('btn-outline-primary');
        document.getElementById('barChartBtn').classList.remove('active', 'btn-primary');
        document.getElementById('barChartBtn').classList.add('btn-outline-primary');
    }
    
    // Get active data type
    const activeDataBtn = document.querySelector('.btn-group .btn-success.active');
    const dataType = activeDataBtn ? activeDataBtn.id.replace('DataBtn', '') : 'climb';
    
    // Show appropriate chart container
    const container = document.getElementById(`${dataType}${type.charAt(0).toUpperCase() + type.slice(1)}ChartContainer`);
    if (container) container.style.display = 'block';
    
    // Recreate charts
    createBarCharts();
    createPieCharts();
}

// Toggle data type (climb, standing, steps, combined)
function toggleDataType(type) {
    document.querySelectorAll('.chart-container').forEach(container => {
        container.style.display = 'none';
    });
    
    const isBarActive = document.getElementById('barChartBtn').classList.contains('active');
    const chartType = isBarActive ? 'Bar' : 'Pie';
    
    document.getElementById(`${type}${chartType}ChartContainer`).style.display = 'block';
    
    // Update button styles
    ['climbDataBtn', 'standingDataBtn', 'stepsDataBtn', 'combinedDataBtn'].forEach(id => {
        const btn = document.getElementById(id);
        if (id === `${type}DataBtn`) {
            btn.classList.add('active', 'btn-success');
            btn.classList.remove('btn-outline-success');
        } else {
            btn.classList.remove('active', 'btn-success');
            btn.classList.add('btn-outline-success');
        }
    });
}

// Create bar charts 
function createBarCharts() {
    try {
        // Climbing bar chart
        const climbCtx = document.getElementById('climbBarChart').getContext('2d');
        climbBarChart = new Chart(climbCtx, {
            type: 'bar',
            data: {
                labels: houseNames,
                datasets: [{
                    label: 'Points',
                    data: climbingData.points || [],
                    backgroundColor: houseColors,
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
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Climbing Points by House',
                        font: { size: 18 }
                    },
                    legend: { display: false }
                }
            }
        });
        
        // Standing bar chart
        const standingCtx = document.getElementById('standingBarChart').getContext('2d');
        standingBarChart = new Chart(standingCtx, {
            type: 'bar',
            data: {
                labels: houseNames,
                datasets: [{
                    label: 'Points',
                    data: standingData.points || [],
                    backgroundColor: houseColors,
                    borderWidth: 1
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
                    title: {
                        display: true,
                        text: 'Standing Points by House',
                        font: { size: 18 }
                    },
                    legend: { display: false }
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
                    data: stepsData.points || [],
                    backgroundColor: houseColors,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Steps Points by House',
                        font: { size: 18 }
                    }
                }
            }
        });
        
        // Combined bar chart
        const combinedCtx = document.getElementById('combinedBarChart').getContext('2d');
        combinedBarChart = new Chart(combinedCtx, {
            type: 'bar',
            data: {
                labels: houseNames,
                datasets: [
                    {
                        label: 'Climbing Points',
                        data: combinedData.climbing_points || [],
                        backgroundColor: 'rgba(255, 99, 132, 0.7)',
                        borderWidth: 1
                    },
                    {
                        label: 'Standing Points',
                        data: combinedData.standing_points || [],
                        backgroundColor: 'rgba(54, 162, 235, 0.7)',
                        borderWidth: 1
                    },
                    {
                        label: 'Steps Points',
                        data: combinedData.steps_points || [],
                        backgroundColor: 'rgba(255, 206, 86, 0.7)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        stacked: false
                    },
                    x: {
                        stacked: false
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Combined Points by House',
                        font: { size: 18 }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error creating bar charts:', error);
        displayChartError('Error creating charts: ' + error.message);
    }
}

// Create pie charts
function createPieCharts() {
    try {
        // Climbing pie chart
        const climbPieCtx = document.getElementById('climbPieChart').getContext('2d');
        climbPieChart = new Chart(climbPieCtx, {
            type: 'pie',
            data: {
                labels: houseNames,
                datasets: [{
                    data: climbingData.points || [],
                    backgroundColor: houseColors,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Climbing Points Distribution',
                        font: { size: 18 }
                    },
                    legend: { position: 'right' }
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
                    data: standingData.points || [],
                    backgroundColor: houseColors,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Standing Points Distribution',
                        font: { size: 18 }
                    },
                    legend: { position: 'right' }
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
                    data: stepsData.points || [],
                    backgroundColor: houseColors,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Steps Points Distribution',
                        font: { size: 18 }
                    },
                    legend: { position: 'right' }
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
                    data: combinedData.total_points || [],
                    backgroundColor: houseColors,
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: 'Total Points Distribution',
                        font: { size: 18 }
                    },
                    legend: { position: 'right' }
                }
            }
        });
    } catch (error) {
        console.error('Error creating pie charts:', error);
        displayChartError('Error creating charts: ' + error.message);
    }
}

// Destroy all charts before recreating
function destroyAllCharts() {
    [climbBarChart, standingBarChart, stepsBarChart, combinedBarChart, 
     climbPieChart, standingPieChart, stepsPieChart, combinedPieChart].forEach(chart => {
        if (chart) chart.destroy();
    });
}

// Display chart error
function displayChartError(message) {
    console.error('Chart error:', message);
    document.querySelectorAll('.chart-container').forEach(container => {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.textContent = message;
        const statsCard = container.querySelector('.stats-card');
        if (statsCard) {
            // Check if error message already exists
            const existingError = statsCard.querySelector('.alert-danger');
            if (existingError) {
                existingError.remove();
            }
            statsCard.appendChild(errorDiv);
        }
    });
}