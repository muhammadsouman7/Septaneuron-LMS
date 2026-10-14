// page-hero.js
document.querySelectorAll('.page-hero').forEach((hero) => {
    const blobs = hero.querySelectorAll('.page-hero__blob');
    hero.addEventListener('mousemove', (e) => {
        const r = hero.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        blobs.forEach((b, i) => {
            const strength = i === 0 ? 18 : -14;
            b.style.transform = `translate(${x * strength}px, ${y * strength}px)`;
        });
    });
    hero.addEventListener('mouseleave', () => {
        blobs.forEach((b) => { b.style.transform = ''; });
    });
});