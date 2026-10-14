(function() {
    const items = document.querySelectorAll('.pf-reveal');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || !('IntersectionObserver' in window)) { items.forEach(x => x.classList.add('is-visible')) } else { const io = new IntersectionObserver((entries, obs) => { entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('is-visible');
                    obs.unobserve(e.target) } }) }, { threshold: .13, rootMargin: '0px 0px -45px' });
        items.forEach(x => io.observe(x)) }
    const buttons = document.querySelectorAll('.pf-filter button');
    const cards = document.querySelectorAll('.pf-mini-card');
    buttons.forEach(button => button.addEventListener('click', () => { const filter = button.dataset.filter;
        buttons.forEach(x => x.classList.remove('is-active'));
        button.classList.add('is-active');
        cards.forEach(card => { const match = filter === 'all' || (card.dataset.category || '').split(' ').includes(filter);
            card.hidden = !match; if (match) { card.classList.remove('is-visible');
                requestAnimationFrame(() => card.classList.add('is-visible')) } }) }));
})();