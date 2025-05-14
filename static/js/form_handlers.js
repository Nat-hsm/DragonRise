document.addEventListener('DOMContentLoaded', function() {
    // Get all screenshot upload forms
    const screenshotForms = document.querySelectorAll('form[action*="upload"]');
    
    screenshotForms.forEach(form => {
        form.addEventListener('submit', function() {
            // Get the submit button and create loading spinner
            const submitBtn = this.querySelector('button[type="submit"]');
            const loadingSpinner = document.createElement('div');
            loadingSpinner.className = 'loading-spinner';
            loadingSpinner.innerHTML = `
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <span class="loading-text">Analyzing image...</span>
            `;
            
            // Insert loading spinner after the form
            this.parentNode.insertBefore(loadingSpinner, this.nextSibling);
            
            // Show loading spinner and disable button
            loadingSpinner.style.display = 'block';
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Processing...';
            
            // Form will submit normally
        });
    });
});