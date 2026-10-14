(function () {
    // Scroll-reveal for individual service pages (/services/<slug>).
    // Mirrors the reveal pattern in services.js so motion feels identical
    // across the hub page and each detail page.
    const motionItems = document.querySelectorAll(
        [
            ".svcd-hero__content",
            ".svc-section__head",
            ".svcd-intro",
            ".svcd-features",
            ".svcd-outcomes",
            ".svc-flow",
            ".svc-architecture",
            ".svc-backend__list",
            ".svc-process__steps",
            ".svc-faq__list",
            ".svcd-related__grid",
        ].join(",")
    );

    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (reduced || !("IntersectionObserver" in window)) {
        motionItems.forEach((item) => item.classList.add("is-visible"));
        return;
    }

    const revealObserver = new IntersectionObserver(
        (entries, observer) => {
            entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                entry.target.classList.add("is-visible");
                observer.unobserve(entry.target);
            });
        },
        { threshold: 0.14, rootMargin: "0px 0px -55px" }
    );

    motionItems.forEach((item) => revealObserver.observe(item));

    // FAQ analytics-free UX nicety: closing sibling <details> when one opens
    // keeps long FAQ lists tidy. Purely progressive - native <details> still
    // works with JS disabled.
    document.querySelectorAll(".svc-faq details").forEach((detail) => {
        detail.addEventListener("toggle", () => {
            if (!detail.open) return;
            detail.parentElement
                .querySelectorAll("details[open]")
                .forEach((other) => {
                    if (other !== detail) other.removeAttribute("open");
                });
        });
    });
})();
