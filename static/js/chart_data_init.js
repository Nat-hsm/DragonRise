// Initialize chart data from HTML data attributes
document.addEventListener('DOMContentLoaded', function() {
    // Get data from the hidden data container
    const dataContainer = document.getElementById('chartDataContainer');
    
    if (!dataContainer) {
        console.error('Chart data container not found');
        return;
    }
    
    try {
        // Initialize global variables from data attributes
        window.houseNames = JSON.parse(dataContainer.getAttribute('data-house-names') || '[]');
        window.houseColors = JSON.parse(dataContainer.getAttribute('data-house-colors') || '[]');
        window.climbingData = JSON.parse(dataContainer.getAttribute('data-climbing') || '{}');
        window.standingData = JSON.parse(dataContainer.getAttribute('data-standing') || '{}');
        window.stepsData = JSON.parse(dataContainer.getAttribute('data-steps') || '{}');
        window.combinedData = JSON.parse(dataContainer.getAttribute('data-combined') || '{}');
        
        console.log('Chart data initialized successfully');
    } catch (error) {
        console.error('Error parsing chart data:', error);
    }
});