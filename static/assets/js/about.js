(function() {
    "use strict";

    const items = document.querySelectorAll(".ab-reveal");
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    items.forEach(function(item, index) {
        item.style.setProperty(
            "--ab-reveal-delay",
            `${Math.min(index % 5, 4) * 70}ms`
        );
    });

    if (
        reduced ||
        !("IntersectionObserver" in window)
    ) {
        items.forEach(function(item) {
            item.classList.add("is-visible");
        });
    } else {
        const observer = new IntersectionObserver(
            function(entries, obs) {
                entries.forEach(function(entry) {
                    if (!entry.isIntersecting) return;

                    entry.target.classList.add("is-visible");
                    obs.unobserve(entry.target);
                });
            }, {
                threshold: 0.13,
                rootMargin: "0px 0px -45px",
            }
        );

        items.forEach(function(item) {
            observer.observe(item);
        });
    }

    if (reduced) return;

    const interactiveCards = document.querySelectorAll(
        ".ab-capabilities article, .ab-difference article"
    );

    interactiveCards.forEach(function(card) {
        card.addEventListener("pointermove", function(event) {
            const rect = card.getBoundingClientRect();
            const x = ((event.clientX - rect.left) / rect.width) * 100;
            const y = ((event.clientY - rect.top) / rect.height) * 100;

            card.style.setProperty("--ab-pointer-x", `${x}%`);
            card.style.setProperty("--ab-pointer-y", `${y}%`);
        });

        card.addEventListener("pointerleave", function() {
            card.style.removeProperty("--ab-pointer-x");
            card.style.removeProperty("--ab-pointer-y");
        });
    });
})();


const bentoCards = document.querySelectorAll(
    ".ab-what-card, .ab-why-card"
);

bentoCards.forEach(function(card) {
    card.addEventListener("pointermove", function(event) {
        const rect = card.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 100;
        const y = ((event.clientY - rect.top) / rect.height) * 100;

        card.style.setProperty("--ab-bento-x", `${x}%`);
        card.style.setProperty("--ab-bento-y", `${y}%`);
    });

    card.addEventListener("pointerleave", function() {
        card.style.removeProperty("--ab-bento-x");
        card.style.removeProperty("--ab-bento-y");
    });

    card.addEventListener("focusin", function() {
        card.classList.add("is-focused");
    });

    card.addEventListener("focusout", function() {
        card.classList.remove("is-focused");
    });
});