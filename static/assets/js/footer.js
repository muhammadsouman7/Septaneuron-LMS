(function() {
    const footer = document.getElementById('snFooter');
    if (!footer) return;

    // ---- Dynamic copyright year ----
    const yearEl = footer.querySelector('#snYear');
    if (yearEl) yearEl.textContent = new Date().getFullYear();

    // ---- Ambient drifting particles ----
    const particleField = footer.querySelector('.sn-footer__particles');
    if (particleField) {
        const COUNT = 18;
        for (let i = 0; i < COUNT; i++) {
            const dot = document.createElement('span');
            dot.style.left = `${Math.random() * 100}%`;
            dot.style.bottom = `${Math.random() * 60}%`;
            dot.style.animationDelay = `${Math.random() * 14}s`;
            dot.style.animationDuration = `${11 + Math.random() * 8}s`;
            particleField.appendChild(dot);
        }
    }

    // ---- Reveal wordmark + logo once footer scrolls into view ----
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    footer.classList.add('is-visible');
                    observer.disconnect();
                }
            });
        }, { threshold: 0.25 }
    );
    observer.observe(footer);

    // ---- Scale the SEPTANEURON wordmark to always fit on one line ----
    // Font-size clamps can't guarantee a long bold word never overflows at
    // every viewport width, so instead we measure the real rendered width
    // and apply a transform: scale() that makes it fit exactly, with a
    // small safety margin. This runs on load, resize, and after fonts load.
    const wordmark = footer.querySelector('.sn-footer__wordmark');
    const textEl = footer.querySelector('.sn-footer__text');
    const markEl = footer.querySelector('.sn-footer__mark');

    function fitWordmark() {
        if (!wordmark || !textEl) return;

        // Reset scale before measuring natural size
        textEl.style.transform = 'none';

        const wordmarkWidth = wordmark.clientWidth;
        const markWidth = markEl ? markEl.getBoundingClientRect().width : 0;
        const gap = parseFloat(getComputedStyle(wordmark).gap || '0') || 0;
        const available = Math.max(0, wordmarkWidth - markWidth - gap);

        const naturalWidth = textEl.scrollWidth;
        if (naturalWidth <= 0 || available <= 0) return;

        const SAFETY_MARGIN = 0.98; // tiny buffer so it never kisses the edge
        let scale = (available / naturalWidth) * SAFETY_MARGIN;
        scale = Math.min(scale, 1); // never scale up past its natural/designed size

        textEl.style.transform = `scale(${scale})`;
    }

    let resizeRaf = null;

    function scheduleFit() {
        if (resizeRaf !== null) return;
        resizeRaf = requestAnimationFrame(() => {
            resizeRaf = null;
            fitWordmark();
        });
    }

    window.addEventListener('resize', scheduleFit, { passive: true });
    window.addEventListener('load', fitWordmark);

    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(fitWordmark).catch(() => {});
    }

    // Run once immediately and once after layout settles
    fitWordmark();
    setTimeout(fitWordmark, 50);

})();