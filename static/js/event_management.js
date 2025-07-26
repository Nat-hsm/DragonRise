document.addEventListener('DOMContentLoaded', function() {
    console.log('Event management script loaded');
    
    // Function to properly hide modal and clean up backdrop
    function hideModal() {
        const modalElement = document.getElementById('activateEventModal');
        const modal = bootstrap.Modal.getInstance(modalElement);
        if (modal) {
            modal.hide();
        }
        
        // Force cleanup after animation
        setTimeout(() => {
            const backdrops = document.querySelectorAll('.modal-backdrop');
            backdrops.forEach(backdrop => backdrop.remove());
            document.body.classList.remove('modal-open');
            document.body.style.overflow = '';
            document.body.style.paddingRight = '';
        }, 300);
    }
    
    // Get all toggle event buttons
    const toggleEventButtons = document.querySelectorAll('.toggle-event-btn');
    console.log('Found ' + toggleEventButtons.length + ' event toggle buttons');
    
    // Add click event listeners to each button
    toggleEventButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            console.log('Event button clicked');
            e.preventDefault();  // Prevent any default form submission
            
            const form = this.closest('form');
            const eventId = form.querySelector('input[name="event_id"]').value;
            console.log('Event ID: ' + eventId);
            
            // Check if this is an activation button
            if (this.textContent.trim() === 'Activate') {
                console.log('Showing activation confirmation modal');
                // Set the event ID in the modal form
                document.getElementById('event_id_input').value = eventId;
                
                // Show the confirmation modal using Bootstrap's modal API
                const modalElement = document.getElementById('activateEventModal');
                const modal = new bootstrap.Modal(modalElement, {
                    backdrop: 'static',
                    keyboard: true
                });
                modal.show();
                
                // Add cleanup listener
                modalElement.addEventListener('hidden.bs.modal', function () {
                    hideModal();
                }, { once: true });
                
            } else {
                // For deactivation, just submit the form
                console.log('Deactivating event - submitting form directly');
                form.submit();
            }
        });
    });
    
    // Handle confirmation button in the modal
    const confirmButton = document.getElementById('confirm-activate-event');
    if (confirmButton) {
        confirmButton.addEventListener('click', function() {
            console.log('Activation confirmed - submitting form');
            hideModal();
            setTimeout(() => {
                document.getElementById('event-toggle-form').submit();
            }, 100);
        });
    } else {
        console.error('Could not find confirm-activate-event button');
    }
});