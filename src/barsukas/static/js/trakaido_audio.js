(function () {
    "use strict";

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
        document.addEventListener("DOMContentLoaded", setupAudio);
    } else {
        setupAudio();
    }
})();
