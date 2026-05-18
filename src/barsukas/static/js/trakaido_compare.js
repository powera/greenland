(function () {
    "use strict";

    function draw() {
        var container = document.getElementById("tk-compare");
        var svg = document.getElementById("tk-lines");
        if (!container || !svg) return;

        var rect = container.getBoundingClientRect();
        var width = rect.width;
        var height = rect.height;
        svg.setAttribute("width", width);
        svg.setAttribute("height", height);
        svg.setAttribute("viewBox", "0 0 " + width + " " + height);
        while (svg.firstChild) svg.removeChild(svg.firstChild);

        var ifaceRow = container.querySelector('[data-row="interface"]');
        var foreignRow = container.querySelector('[data-row="foreign"]');
        if (!ifaceRow || !foreignRow) return;

        var ifaceChips = ifaceRow.querySelectorAll(".tk-chip");
        var foreignChips = foreignRow.querySelectorAll(".tk-chip");

        var foreignByKey = {};
        foreignChips.forEach(function (chip) {
            var key = chip.getAttribute("data-pair-key");
            if (key) {
                if (!foreignByKey[key]) foreignByKey[key] = [];
                foreignByKey[key].push(chip);
            }
        });

        ifaceChips.forEach(function (chip) {
            var key = chip.getAttribute("data-pair-key");
            if (!key || !foreignByKey[key]) return;
            var partners = foreignByKey[key];
            var color = window.getComputedStyle(chip).color;
            partners.forEach(function (partner) {
                drawLine(svg, container, chip, partner, color);
            });
        });
    }

    function drawLine(svg, container, a, b, color) {
        var cRect = container.getBoundingClientRect();
        var aRect = a.getBoundingClientRect();
        var bRect = b.getBoundingClientRect();
        var x1 = aRect.left + aRect.width / 2 - cRect.left;
        var y1 = aRect.bottom - cRect.top;
        var x2 = bRect.left + bRect.width / 2 - cRect.left;
        var y2 = bRect.top - cRect.top;
        var midY = (y1 + y2) / 2;
        var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        var d = "M " + x1 + " " + y1 +
                " C " + x1 + " " + midY + ", " + x2 + " " + midY + ", " + x2 + " " + y2;
        path.setAttribute("d", d);
        path.setAttribute("stroke", color);
        path.setAttribute("stroke-width", "2");
        path.setAttribute("fill", "none");
        path.setAttribute("opacity", "0.6");
        svg.appendChild(path);
    }

    function setupHover() {
        var chips = document.querySelectorAll("#tk-compare .tk-chip[data-pair-key]");
        chips.forEach(function (chip) {
            chip.addEventListener("mouseenter", function () {
                var key = chip.getAttribute("data-pair-key");
                if (!key) return;
                document.querySelectorAll('#tk-compare .tk-chip[data-pair-key="' + key + '"]')
                    .forEach(function (c) { c.classList.add("tk-chip-active"); });
            });
            chip.addEventListener("mouseleave", function () {
                document.querySelectorAll("#tk-compare .tk-chip-active")
                    .forEach(function (c) { c.classList.remove("tk-chip-active"); });
            });
        });
    }

    function setupAudio() {
        var buttons = document.querySelectorAll(".trakaido-audio-button[data-audio-url]");
        if (!buttons.length) return;
        var audio = new Audio();
        var current = null;
        audio.addEventListener("ended", function () {
            if (current) current.classList.remove("is-playing");
            current = null;
        });
        buttons.forEach(function (btn) {
            btn.addEventListener("click", function () {
                var url = btn.getAttribute("data-audio-url");
                if (!url) return;
                if (current === btn && !audio.paused) {
                    audio.pause();
                    btn.classList.remove("is-playing");
                    current = null;
                    return;
                }
                if (current) current.classList.remove("is-playing");
                audio.src = url;
                audio.play().then(function () {
                    btn.classList.add("is-playing");
                    current = btn;
                }).catch(function () {
                    btn.classList.remove("is-playing");
                });
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            draw(); setupHover(); setupAudio();
        });
    } else {
        draw();
        setupHover();
        setupAudio();
    }
    window.addEventListener("resize", draw);
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(draw);
    }
})();
