(function() {
    "use strict";

    const loader = document.getElementById("snPageLoader");

    if (!loader) return;

    const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;

    let isNavigating = false;

    function showLoader() {
        loader.classList.add("is-visible");
        loader.setAttribute("aria-hidden", "false");
    }

    function hideLoader() {
        loader.classList.remove("is-visible");
        loader.setAttribute("aria-hidden", "true");
    }

    function isInternalPageLink(link) {
        if (!link) return false;

        const href = link.getAttribute("href");

        if (!href ||
            href.startsWith("#") ||
            href.startsWith("mailto:") ||
            href.startsWith("tel:") ||
            href.startsWith("javascript:")
        ) {
            return false;
        }

        if (
            link.target === "_blank" ||
            link.hasAttribute("download") ||
            link.hasAttribute("data-no-transition")
        ) {
            return false;
        }

        const destination = new URL(href, window.location.href);

        return destination.origin === window.location.origin;
    }

    document.addEventListener("click", function(event) {
        const link = event.target.closest("a");

        if (!isInternalPageLink(link)) return;

        const destination = new URL(
            link.getAttribute("href"),
            window.location.href
        );

        const currentUrl =
            window.location.pathname +
            window.location.search;

        const destinationUrl =
            destination.pathname +
            destination.search;

        // Do not show the loader for the current page.
        if (destinationUrl === currentUrl) return;

        event.preventDefault();

        if (isNavigating) return;

        isNavigating = true;

        // Keep the current page position unchanged.
        showLoader();

        const delay = reducedMotion ? 0 : 480;

        window.setTimeout(function() {
            window.location.assign(destination.href);
        }, delay);
    });

    // If the browser restores the page from its back/forward cache,
    // make sure the loader does not remain visible.
    window.addEventListener("pageshow", function() {
        isNavigating = false;
        hideLoader();
    });
})();