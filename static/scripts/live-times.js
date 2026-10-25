function span(s) {
    const units = [
        [60, 1, "second"],
        [3600, 60, "minute"],
        [86400, 3600, "hour"],
        [604800, 86400, "day"],
        [2629800, 604800, "week"],
        [31557600, 2629800, "month"],
        [Infinity, 31557600, "year"]
    ];
    for (const [limit, size, unit] of units) {
        if (s < limit) {
            const n = Math.floor(s / size);
            return n + " " + unit + (n === 1 ? "" : "s");
        }
    }
}

function timeago(dt) {
    const s = Math.floor((Date.now() - dt) / 1000);
    return s < 0 ? "in " + span(-s) : span(s) + " ago";
}

function timeuntil(dt) {
    const s = Math.floor((dt - Date.now()) / 1000);
    return s <= 0 ? "due now" : "in " + span(s);
}

function updateLiveTimes() {
    document.querySelectorAll("time[data-live]").forEach(function (el) {
        const dt = new Date(el.getAttribute("datetime"));
        if (isNaN(dt)) return;
        el.textContent = el.dataset.live === "until" ? timeuntil(dt) : timeago(dt);
    });
}
updateLiveTimes();
setInterval(updateLiveTimes, 1000);
document.addEventListener("htmx:afterSettle", updateLiveTimes);
