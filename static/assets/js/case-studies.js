(function() {
    "use strict";

    const revealItems = document.querySelectorAll(".cs-reveal");
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduceMotion || !("IntersectionObserver" in window)) {
        revealItems.forEach(function(item) {
            item.classList.add("is-visible");
        });
    } else {
        const observer = new IntersectionObserver(function(entries, obs) {
            entries.forEach(function(entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                obs.unobserve(entry.target);
            });
        }, { threshold: 0.14, rootMargin: "0px 0px -45px" });

        revealItems.forEach(function(item) {
            observer.observe(item);
        });
    }

    const metrics = document.querySelectorAll("[data-count]");

    function animateMetric(metric) {
        const target = Number(metric.dataset.count);
        if (!Number.isFinite(target) || reduceMotion) return;

        const duration = 900;
        const start = performance.now();

        function frame(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            metric.textContent = Math.round(target * eased);
            if (progress < 1) window.requestAnimationFrame(frame);
        }

        metric.textContent = "0";
        window.requestAnimationFrame(frame);
    }

    if (metrics.length && "IntersectionObserver" in window && !reduceMotion) {
        const metricObserver = new IntersectionObserver(function(entries, obs) {
            entries.forEach(function(entry) {
                if (!entry.isIntersecting) return;
                animateMetric(entry.target);
                obs.unobserve(entry.target);
            });
        }, { threshold: 0.5 });
        metrics.forEach(function(metric) { metricObserver.observe(metric); });
    }

    const orbit = document.querySelector(".cs-system-orbit");
    if (orbit && !reduceMotion) {
        orbit.addEventListener("pointermove", function(event) {
            const rect = orbit.getBoundingClientRect();
            const x = (event.clientX - rect.left) / rect.width - 0.5;
            const y = (event.clientY - rect.top) / rect.height - 0.5;
            orbit.style.transform = `rotate(${x * 12}deg) translate(${x * 8}px, ${y * 8}px)`;
        });
        orbit.addEventListener("pointerleave", function() {
            orbit.style.transform = "";
        });
    }

    /* ---------- Image lightbox: add class "cs-zoom" to any <img> ---------- */
    const zoomImages = document.querySelectorAll("img.cs-zoom");

    if (zoomImages.length) {
        const lightbox = document.createElement("div");
        lightbox.className = "cs-lightbox";
        lightbox.setAttribute("role", "dialog");
        lightbox.setAttribute("aria-modal", "true");
        lightbox.setAttribute("aria-hidden", "true");
        lightbox.innerHTML =
            '<div class="cs-lightbox__backdrop" data-close></div>' +
            '<button class="cs-lightbox__close" type="button" aria-label="Close image preview" data-close>&times;</button>' +
            '<img class="cs-lightbox__img" alt="">';
        document.body.appendChild(lightbox);

        const lightboxImg = lightbox.querySelector(".cs-lightbox__img");
        let lastFocused = null;

        function openLightbox(src, alt) {
            lastFocused = document.activeElement;
            lightboxImg.src = src;
            lightboxImg.alt = alt || "";
            lightbox.classList.add("is-open");
            lightbox.setAttribute("aria-hidden", "false");
            document.body.style.overflow = "hidden";
            lightbox.querySelector(".cs-lightbox__close").focus();
        }

        function closeLightbox() {
            lightbox.classList.remove("is-open");
            lightbox.setAttribute("aria-hidden", "true");
            document.body.style.overflow = "";
            if (lastFocused) lastFocused.focus();
        }

        zoomImages.forEach(function(img) {
            img.setAttribute("tabindex", "0");
            img.setAttribute("role", "button");
            img.addEventListener("click", function() {
                openLightbox(img.currentSrc || img.src, img.alt);
            });
            img.addEventListener("keydown", function(event) {
                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    openLightbox(img.currentSrc || img.src, img.alt);
                }
            });
        });

        lightbox.addEventListener("click", function(event) {
            if (event.target.hasAttribute("data-close")) closeLightbox();
        });

        document.addEventListener("keydown", function(event) {
            if (event.key === "Escape" && lightbox.classList.contains("is-open")) closeLightbox();
        });
    }
})();