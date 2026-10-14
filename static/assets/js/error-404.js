(function () {
    "use strict";

    var eyes = Array.prototype.slice.call(document.querySelectorAll("[data-eye]"));
    if (!eyes.length) return;

    var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Back button
    var back = document.querySelector("[data-go-back]");
    if (back) {
        back.addEventListener("click", function () {
            if (window.history.length > 1 && document.referrer) window.history.back();
            else window.location.href = "/";
        });
    }

    var state = eyes.map(function (eye) {
        return { eye: eye, pupil: eye.querySelector("[data-pupil]"), x: 0, y: 0, tx: 0, ty: 0 };
    });

    var pointer = { x: window.innerWidth / 2, y: window.innerHeight / 2, active: false };
    var lastMove = 0;

    function aim(s, px, py) {
        var rect = s.eye.getBoundingClientRect();
        var cx = rect.left + rect.width / 2;
        var cy = rect.top + rect.height / 2;
        var dx = px - cx;
        var dy = py - cy;
        var dist = Math.hypot(dx, dy) || 1;

        // How far the pupil may travel inside the eye
        var maxTravel = (rect.width - s.pupil.offsetWidth) / 2 - rect.width * 0.03;
        // Reach the edge quickly, ease in near the centre
        var travel = Math.min(dist * 0.6, maxTravel);

        s.tx = (dx / dist) * travel;
        s.ty = (dy / dist) * travel;
    }

    function onMove(e) {
        var p = e.touches ? e.touches[0] : e;
        pointer.x = p.clientX;
        pointer.y = p.clientY;
        pointer.active = true;
        lastMove = performance.now();
    }

    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("touchmove", onMove, { passive: true });
    window.addEventListener("touchstart", onMove, { passive: true });

    // Idle wandering when no pointer (e.g. phones) - eyes glance around
    var wander = { x: 0, y: 0, next: 0 };
    function pickWander(now) {
        var a = Math.random() * Math.PI * 2;
        var r = 200 + Math.random() * 300;
        wander.x = window.innerWidth / 2 + Math.cos(a) * r;
        wander.y = window.innerHeight / 2 + Math.sin(a) * r;
        wander.next = now + 1200 + Math.random() * 1800;
    }

    function frame(now) {
        var idle = !pointer.active || now - lastMove > 3500;
        if (idle) {
            if (now > wander.next) pickWander(now);
            state.forEach(function (s) { aim(s, wander.x, wander.y); });
        } else {
            state.forEach(function (s) { aim(s, pointer.x, pointer.y); });
        }

        state.forEach(function (s) {
            s.x += (s.tx - s.x) * 0.16;
            s.y += (s.ty - s.y) * 0.16;
            s.pupil.style.setProperty("--px", s.x.toFixed(2) + "px");
            s.pupil.style.setProperty("--py", s.y.toFixed(2) + "px");
        });

        requestAnimationFrame(frame);
    }

    // Blinking
    function blink() {
        eyes.forEach(function (eye) { eye.classList.add("is-blinking"); });
        setTimeout(function () {
            eyes.forEach(function (eye) { eye.classList.remove("is-blinking"); });
        }, 140);
        setTimeout(blink, 2500 + Math.random() * 3500);
    }

    if (reduced) {
        // Static, centred pupils; still follow the cursor without smoothing/blinking
        window.addEventListener("pointermove", function (e) {
            state.forEach(function (s) {
                aim(s, e.clientX, e.clientY);
                s.pupil.style.setProperty("--px", s.tx.toFixed(2) + "px");
                s.pupil.style.setProperty("--py", s.ty.toFixed(2) + "px");
            });
        }, { passive: true });
    } else {
        requestAnimationFrame(frame);
        setTimeout(blink, 2000);
    }
})();
