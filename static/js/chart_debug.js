// Add this file to help debug chart issues
document.addEventListener('DOMContentLoaded', function() {
    // Get data container
    const dataContainer = document.getElementById('chartDataContainer');
    
    if (!dataContainer) {
        console.error('Chart data container not found');
        return;
    }
    
    // Extract and log chart data
    console.log('House Names:', dataContainer.getAttribute('data-house-names'));
    console.log('House Colors:', dataContainer.getAttribute('data-house-colors'));
    console.log('Climbing Data:', dataContainer.getAttribute('data-climbing'));
    console.log('Standing Data:', dataContainer.getAttribute('data-standing'));
    console.log('Steps Data:', dataContainer.getAttribute('data-steps'));
    console.log('Combined Data:', dataContainer.getAttribute('data-combined'));
    
    // Check if canvases exist
    const canvases = document.querySelectorAll('canvas');
    console.log('Found', canvases.length, 'canvas elements');
    
    // Add a fallback for empty chart data
    const chartContainers = document.querySelectorAll('.chart-container');
    chartContainers.forEach(container => {
        const canvas = container.querySelector('canvas');
        if (canvas) {
            // Add a sample drawing to check if canvas works
            try {
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = 'rgba(200, 200, 200, 0.5)';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.font = '20px Arial';
                ctx.fillStyle = 'black';
                ctx.textAlign = 'center';
                ctx.fillText('Chart data loading...', canvas.width/2, canvas.height/2);
            } catch (error) {
                console.error('Error drawing on canvas:', error);
            }
        }
    });
});