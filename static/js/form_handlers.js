// Version 2.0.0 - Complete rewrite with no AJAX
document.addEventListener('DOMContentLoaded', function() {
    console.log('Form handlers script loaded');
    
    // Get all screenshot upload forms
    const screenshotForms = document.querySelectorAll('form[action*="upload"]');
    console.log(`Found ${screenshotForms.length} upload forms`);
    
    screenshotForms.forEach(form => {
        // Add novalidate to prevent browser validation
        form.setAttribute('novalidate', true);
        
        form.addEventListener('submit', function(event) {
            console.log(`Form submission intercepted: ${form.action}`);
            
            // Basic validation
            const fileInput = this.querySelector('input[type="file"]');
            if (!fileInput || !fileInput.files || !fileInput.files[0]) {
                event.preventDefault();
                alert('Please select a file to upload');
                return false;
            }
            
            // Log file info
            const file = fileInput.files[0];
            console.log(`File selected: ${file.name} Size: ${file.size}`);
            
            // File size validation (5MB limit)
            if (file.size > 5 * 1024 * 1024) {
                event.preventDefault();
                alert('File size exceeds the 5MB limit');
                return false;
            }
            
            // Display loading state
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = 'Processing...';
            }
            
            // Create loading spinner
            const existingSpinner = document.querySelector('.loading-spinner');
            if (existingSpinner) {
                existingSpinner.remove();
            }
            
            const loadingSpinner = document.createElement('div');
            loadingSpinner.className = 'loading-spinner';
            loadingSpinner.innerHTML = `
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <span class="loading-text">Analyzing image...</span>
            `;
            
            // Add spinner after form
            this.parentNode.insertBefore(loadingSpinner, this.nextSibling);
            
            // Allow the form to submit normally - no AJAX, no preventDefault
            return true;
        });
    });
});