(function() {
    "use strict";

    const cards = document.querySelectorAll(".sn-beam-card");

    if (!cards.length) {
        return;
    }

    const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;

    if (reducedMotion) {
        return;
    }

    const beams = [];

    cards.forEach(function(card) {
        const beam = document.createElement("span");
        beam.className = "sn-border-beam";
        beam.setAttribute("aria-hidden", "true");

        const beamSize = Number(card.dataset.beamSize || 110);
        const beamColor = card.dataset.beamColor || "#07c0cd";
        const duration = Math.max(Number(card.dataset.beamDuration || 8), 1);
        const radius = getComputedStyle(card).borderRadius || "20px";

        card.style.setProperty("--beam-size", `${beamSize}px`);
        card.style.setProperty("--beam-color", beamColor);
        card.style.setProperty("--beam-duration", `${duration}s`);
        card.style.setProperty("--card-radius", radius);

        beam.style.width = `${beamSize}px`;
        // stagger start so beams don't all sync
        beam.style.animationDelay = `${-Math.random() * duration}s`;

        card.appendChild(beam);
    });

    function positionBeam(item, timestamp) {
        const card = item.card;
        const beam = item.beam;

        const width = card.clientWidth;
        const height = card.clientHeight;

        if (!width || !height) {
            return;
        }

        /*
         * Border perimeter.
         */
        const perimeter =
            width * 2 +
            height * 2;

        const elapsed =
            timestamp / 1000;

        const distance =
            (
                (elapsed / item.duration) +
                item.offset
            ) * perimeter;

        const position =
            distance % perimeter;

        let x;
        let y;
        let angle;

        /*
         * Top border: left to right
         */
        if (position < width) {
            x = position;
            y = 0;
            angle = 0;
        }

        /*
         * Right border: top to bottom
         */
        else if (position < width + height) {
            x = width;
            y = position - width;
            angle = 90;
        }

        /*
         * Bottom border: right to left
         */
        else if (position < width * 2 + height) {
            x = width - (position - width - height);
            y = height;
            angle = 180;
        }

        /*
         * Left border: bottom to top
         */
        else {
            x = 0;
            y = height - (position - width * 2 - height);
            angle = 270;
        }

        /*
         * The beam is centered exactly on the border point.
         * This is what makes it reach all four borders.
         */
        beam.style.left = `${x}px`;
        beam.style.top = `${y}px`;
        beam.style.transform =
            `translate(-50%, -50%) rotate(${angle}deg)`;
    }

    function animate(timestamp) {
        beams.forEach(function(item) {
            positionBeam(item, timestamp);
        });

        window.requestAnimationFrame(animate);
    }

    window.requestAnimationFrame(animate);

    /*
     * Recalculate the beam after cards resize.
     */
    const resizeObserver = new ResizeObserver(function() {
        beams.forEach(function(item) {
            positionBeam(item, performance.now());
        });
    });

    beams.forEach(function(item) {
        resizeObserver.observe(item.card);
    });
})();