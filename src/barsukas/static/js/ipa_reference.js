document.addEventListener("DOMContentLoaded", () => {
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggerList.forEach((tooltipTriggerElement) => {
        // bootstrap is loaded globally in base.html
        // eslint-disable-next-line no-undef
        new bootstrap.Tooltip(tooltipTriggerElement);
    });
});
