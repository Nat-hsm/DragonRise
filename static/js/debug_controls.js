// Handle debug control buttons
document.addEventListener('DOMContentLoaded', function() {
    const debugCloseButtons = document.querySelectorAll('.debug-close-btn');
    
    debugCloseButtons.forEach(button => {
        button.addEventListener('click', function() {
            const debugInfo = document.getElementById('debugInfo');
            if (debugInfo) {
                debugInfo.style.display = 'none';
            }
        });
    });
});