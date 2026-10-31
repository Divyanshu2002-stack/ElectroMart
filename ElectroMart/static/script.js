document.addEventListener('DOMContentLoaded', function() {
    const btn = document.getElementById('cornerBtn');
    const dropdown = document.getElementById('cornerDropdown');
    if (btn && dropdown) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            dropdown.classList.toggle('show');
        });
        document.addEventListener('click', function() {
            dropdown.classList.remove('show');
        });
    }
});