document.addEventListener('DOMContentLoaded', function() {
    console.log('Event management script loaded');
    
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
                const modal = new bootstrap.Modal(document.getElementById('activateEventModal'));
                modal.show();
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
            document.getElementById('event-toggle-form').submit();
        });
    } else {
        console.error('Could not find confirm-activate-event button');
    }
});