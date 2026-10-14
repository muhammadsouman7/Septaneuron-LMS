(function() {
    const items = document.querySelectorAll('.ct-reveal');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduced || !('IntersectionObserver' in window)) { items.forEach(item => item.classList.add('is-visible')); return }
    const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add('is-visible');
            obs.unobserve(entry.target)
        })
    }, { threshold: .13, rootMargin: '0px 0px -45px' });
    items.forEach(item => observer.observe(item));
})();

(function() {
    const form = document.getElementById('ctForm');
    const modal = document.getElementById('ctModal');
    if (!form || !modal) return;

    const icon = document.getElementById('ctModalIcon');
    const title = document.getElementById('ctModalTitle');
    const text = document.getElementById('ctModalText');
    const submitBtn = form.querySelector('.ct-btn--submit');

    function openModal(success, message) {
        icon.textContent = success ? '✓' : '✕';
        icon.classList.toggle('ct-modal__icon--error', !success);
        title.textContent = success ? 'Message sent' : 'Something went wrong';
        text.textContent = message;
        modal.classList.add('is-open');
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeModal() {
        modal.classList.remove('is-open');
        modal.setAttribute('aria-hidden', 'true');
    }

    modal.querySelectorAll('[data-close]').forEach(el => el.addEventListener('click', closeModal));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

    form.addEventListener('submit', function(e) {
        e.preventDefault();
        e.stopPropagation();
        handleSubmit();
    });

    async function handleSubmit() {
        const originalLabel = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = 'Sending…';

        try {
            const formData = new FormData(form);
            const res = await fetch(form.action, {
                method: 'POST',
                headers: { 'Accept': 'application/json' },
                body: formData
            });
            const data = await res.json();

            if (res.ok && data.ok) {
                openModal(true, "Thanks for reaching out — we'll get back to you soon.");
                form.reset();
            } else {
                openModal(false, data.message || 'Please try again or email us directly.');
            }
        } catch (err) {
            openModal(false, 'Network error — please try again or email us directly.');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalLabel;
        }
    }
})();