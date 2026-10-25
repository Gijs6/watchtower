document.addEventListener("htmx:beforeRequest", function (event) {
    const el = event.detail.elt;
    if (el.matches("[data-pause-when-open]") && el.querySelector("details[open]")) {
        event.preventDefault();
    }
});
