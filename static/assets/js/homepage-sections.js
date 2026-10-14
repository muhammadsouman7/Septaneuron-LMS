(function () {
  const revealItems = document.querySelectorAll('.sn-reveal');
  if (!revealItems.length) return;

  const show = (item) => item.classList.add('is-visible');
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  if (prefersReducedMotion || !('IntersectionObserver' in window)) {
    revealItems.forEach(show);
  } else {
    const observer = new IntersectionObserver((entries, self) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          show(entry.target);
          self.unobserve(entry.target);
        }
      });
    }, { threshold: 0.14, rootMargin: '0px 0px -40px' });
    revealItems.forEach((item) => observer.observe(item));
  }

  // Keep existing hero CTAs useful without changing the hero markup.
  document.querySelectorAll('.hero .btn-primary, .sn-nav__cta').forEach((button) => {
    button.addEventListener('click', () => {
      const target = document.getElementById('contact');
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  document.querySelectorAll('.hero .btn-secondary').forEach((button) => {
    button.addEventListener('click', () => {
      const target = document.getElementById('work');
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
})();

