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
        
        // Add fixed opacity to chart sections at startup
        document.getElementById('barChartsSection').style.opacity = '1';
        document.getElementById('pieChartsSection').style.opacity = '0';
        
        // Create charts
        createBarCharts();
        createPieCharts();
        
        // Set up event listeners
        setupEventListeners();
        
        // Call our size function after initial setup
        setConsistentChartSizes();
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

// Update the setConsistentChartSizes function
function setConsistentChartSizes() {
    // Apply a strict height structure to all chart elements
    document.querySelectorAll('.chart-container').forEach(container => {
        container.style.height = '600px';
        container.style.minHeight = '600px';
        container.style.maxHeight = '600px';
        
        const statsCard = container.querySelector('.stats-card');
        if (statsCard) {
            statsCard.style.height = '560px';
            statsCard.style.minHeight = '560px';
            statsCard.style.maxHeight = '560px';
            statsCard.classList.add('fixed-height');
            
            const chartWrapper = statsCard.querySelector('.chart-wrapper');
            if (chartWrapper) {
                chartWrapper.style.height = '480px';
                chartWrapper.style.minHeight = '480px';
                chartWrapper.style.maxHeight = '480px';
            }
        }
    });
    
    ['barChartsSection', 'pieChartsSection'].forEach(id => {
        const section = document.getElementById(id);
        if (section) {
            section.style.height = '650px';
            section.style.minHeight = '650px';
            section.style.overflow = 'hidden';
        }
    });
}

// Modify the toggleChartType function to fix pie chart display
function toggleChartType(type) {
    // Destroy all charts first
    destroyAllCharts();
    
    // Store scroll position
    const scrollPos = window.scrollY;
    
    // Force consistent sizes
    setConsistentChartSizes();
    
    // Get sections
    const barSection = document.getElementById('barChartsSection');
    const pieSection = document.getElementById('pieChartsSection');
    
    if (type === 'bar') {
        // Update button styles immediately
        document.getElementById('barChartBtn').classList.add('active', 'btn-primary');
        document.getElementById('barChartBtn').classList.remove('btn-outline-primary');
        document.getElementById('pieChartBtn').classList.remove('active', 'btn-primary');
        document.getElementById('pieChartBtn').classList.add('btn-outline-primary');
        
        // Hide pie charts completely first
        pieSection.style.display = 'none';
        
        // Show bar section
        barSection.style.display = 'block';
        
        // Get active data type
        const activeDataBtn = document.querySelector('.btn-group .btn-success.active');
        const dataType = activeDataBtn ? activeDataBtn.id.replace('DataBtn', '') : 'climb';
        
        // Hide all bar chart containers
        document.querySelectorAll('#barChartsSection .chart-container').forEach(el => {
            el.style.display = 'none';
        });
        
        // Show only the active bar chart container
        const targetContainer = document.getElementById(`${dataType}BarChartContainer`);
        if (targetContainer) {
            targetContainer.style.display = 'block';
        }
        
        // Create bar charts with slight delay for DOM update
        setTimeout(() => {
            setConsistentChartSizes();
            createBarCharts();
            window.scrollTo(0, scrollPos);
        }, 50);
    } else {
        // Update button styles immediately
        document.getElementById('pieChartBtn').classList.add('active', 'btn-primary');
        document.getElementById('pieChartBtn').classList.remove('btn-outline-primary');
        document.getElementById('barChartBtn').classList.remove('active', 'btn-primary');
        document.getElementById('barChartBtn').classList.add('btn-outline-primary');
        
        // Hide bar charts completely first
        barSection.style.display = 'none';
        
        // Show pie section
        pieSection.style.display = 'block';
        pieSection.style.visibility = 'visible'; // Ensure visibility
        pieSection.style.opacity = '1';
        
        // Get active data type
        const activeDataBtn = document.querySelector('.btn-group .btn-success.active');
        const dataType = activeDataBtn ? activeDataBtn.id.replace('DataBtn', '') : 'climb';
        
        // Make all pie chart containers visible temporarily (for chart creation)
        document.querySelectorAll('#pieChartsSection .chart-container').forEach(el => {
            el.style.display = 'block';
            el.style.visibility = 'visible';
            el.style.opacity = '0.01'; // Nearly invisible but still rendered
        });
        
        // Create charts immediately while containers are visible
        createPieCharts();
        
        // Hide all pie chart containers except target
        document.querySelectorAll('#pieChartsSection .chart-container').forEach(el => {
            if (el.id !== `${dataType}PieChartContainer`) {
                el.style.display = 'none';
            } else {
                el.style.opacity = '1'; // Make target container fully visible
            }
        });
        
        // Scroll to previous position
        window.scrollTo(0, scrollPos);
    }
}

// Update the toggleDataType function
function toggleDataType(type) {
    // Store scroll position
    const scrollPos = window.scrollY;
    
    // Ensure all containers have the same height
    document.querySelectorAll('.chart-container').forEach(container => {
        container.style.height = '600px';
        container.style.minHeight = '600px';
    });
    
    // Determine which chart type is active
    const isBarActive = document.getElementById('barChartBtn').classList.contains('active');
    const chartType = isBarActive ? 'Bar' : 'Pie';
    
    // Hide all with opacity transition
    document.querySelectorAll('.chart-container').forEach(container => {
        container.style.opacity = '0';
        setTimeout(() => {
            container.style.display = 'none';
        }, 300);
    });
    
    // Show the target container
    const targetContainer = document.getElementById(`${type}${chartType}ChartContainer`);
    if (targetContainer) {
        setTimeout(() => {
            targetContainer.style.display = 'block';
            setTimeout(() => {
                targetContainer.style.opacity = '1';
                // Restore scroll position
                window.scrollTo(0, scrollPos);
            }, 50);
        }, 300);
    }
    
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
        // Add this line at the beginning of the function
        setConsistentChartSizes();
        
        // Common options for all charts with strict height control
        const commonChartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                title: {
                    font: { size: 18 }
                }
            },
            animation: {
                duration: 500
            },
            layout: {
                padding: {
                    top: 20,
                    right: 20,
                    bottom: 20,
                    left: 20
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        padding: 10
                    }
                },
                x: {
                    ticks: {
                        padding: 10
                    }
                }
            }
        };
        
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
                ...commonChartOptions,
                plugins: {
                    title: {
                        display: true,
                        text: 'Climbing Points by House'
                    }
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
                ...commonChartOptions,
                plugins: {
                    title: {
                        display: true,
                        text: 'Standing Points by House'
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
                    data: stepsData.points || [],
                    backgroundColor: houseColors,
                    borderWidth: 1
                }]
            },
            options: {
                ...commonChartOptions,
                plugins: {
                    title: {
                        display: true,
                        text: 'Steps Points by House'
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
                ...commonChartOptions,
                scales: {
                    y: {
                        stacked: false
                    },
                    x: {
                        stacked: false
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Combined Points by House'
                    }
                }
            }
        });
    } catch (error) {
        console.error('Error creating bar charts:', error);
        displayChartError('Error creating charts: ' + error.message);
    }
}

// Update the createPieCharts function to implement all four pie chart types
function createPieCharts() {
    try {
        // Ensure consistent sizes first
        setConsistentChartSizes();
        
        // Common options with guaranteed height
        const commonPieOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        boxWidth: 15,
                        padding: 10
                    }
                },
                title: {
                    display: true,
                    font: { size: 18 }
                }
            },
            animation: {
                duration: 500
            },
            layout: {
                padding: 20
            }
        };
        
        console.log('Creating pie charts with containers visible');
        
        // Climbing pie chart
        const climbPieCtx = document.getElementById('climbPieChart');
        if (climbPieCtx) {
            // Force canvas dimensions
            climbPieCtx.style.height = '480px';
            climbPieCtx.style.width = '100%';
            
            climbPieChart = new Chart(climbPieCtx.getContext('2d'), {
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
                    ...commonPieOptions,
                    plugins: {
                        ...commonPieOptions.plugins,
                        title: {
                            ...commonPieOptions.plugins.title,
                            text: 'Climbing Points Distribution'
                        }
                    }
                }
            });
        } else {
            console.error('Could not find climbing pie chart canvas');
        }
        
        // Standing pie chart
        const standingPieCtx = document.getElementById('standingPieChart');
        if (standingPieCtx) {
            // Force canvas dimensions
            standingPieCtx.style.height = '480px';
            standingPieCtx.style.width = '100%';
            
            standingPieChart = new Chart(standingPieCtx.getContext('2d'), {
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
                    ...commonPieOptions,
                    plugins: {
                        ...commonPieOptions.plugins,
                        title: {
                            ...commonPieOptions.plugins.title,
                            text: 'Standing Time Distribution'
                        }
                    }
                }
            });
        } else {
            console.error('Could not find standing pie chart canvas');
        }
        
        // Steps pie chart
        const stepsPieCtx = document.getElementById('stepsPieChart');
        if (stepsPieCtx) {
            // Force canvas dimensions
            stepsPieCtx.style.height = '480px';
            stepsPieCtx.style.width = '100%';
            
            stepsPieChart = new Chart(stepsPieCtx.getContext('2d'), {
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
                    ...commonPieOptions,
                    plugins: {
                        ...commonPieOptions.plugins,
                        title: {
                            ...commonPieOptions.plugins.title,
                            text: 'Steps Points Distribution'
                        }
                    }
                }
            });
        } else {
            console.error('Could not find steps pie chart canvas');
        }
        
        // Combined pie chart
        const combinedPieCtx = document.getElementById('combinedPieChart');
        if (combinedPieCtx) {
            // Force canvas dimensions
            combinedPieCtx.style.height = '480px';
            combinedPieCtx.style.width = '100%';
            
            combinedPieChart = new Chart(combinedPieCtx.getContext('2d'), {
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
                    ...commonPieOptions,
                    plugins: {
                        ...commonPieOptions.plugins,
                        title: {
                            ...commonPieOptions.plugins.title,
                            text: 'Total Points Distribution'
                        }
                    }
                }
            });
        } else {
            console.error('Could not find combined pie chart canvas');
        }
        
    } catch (error) {
        console.error('Error creating pie charts:', error);
        displayChartError('Error creating pie charts: ' + error.message);
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