(function() {
    // The Services page now uses the exact homepage hero via js/hero.js.
    // This file is intentionally responsible only for Services-page reveals.
    const motionItems = document.querySelectorAll(
        [
            ".svc-section__head",
            ".svc-detail",
            ".svc-visual",
            ".svc-flow",
            ".svc-bottom-row",
            ".svc-architecture",
            ".svc-backend__list",
            ".svc-principles",
            ".svc-tech__marquee",
            ".svc-tech__groups",
            ".svc-engagement__grid",
            ".svc-media__layout",
            ".svc-marketing__grid",
            ".svc-growth",
            ".svc-growth__grid",
        ].join(",")
    );

    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || !('IntersectionObserver' in window)) {
        motionItems.forEach((item) => item.classList.add('is-visible'));
    } else {
        const revealObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add('is-visible');
                observer.unobserve(entry.target);
            });
        }, { threshold: 0.14, rootMargin: '0px 0px -55px' });
        motionItems.forEach((item) => revealObserver.observe(item));
    }
})();