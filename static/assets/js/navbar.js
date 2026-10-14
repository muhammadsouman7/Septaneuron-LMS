(function() {
    'use strict';

    const nav = document.getElementById('snNav');
    if (!nav) return;

    const toggle = nav.querySelector('.sn-nav__toggle');
    const dock = nav.querySelector('.sn-dock');
    const cta = nav.querySelector('.sn-nav__cta');
    const items = dock ? Array.from(dock.querySelectorAll('.sn-dock__item')) : [];

    if (dock && !dock.id) {
        dock.id = 'snMainDock';
    }

    if (toggle && dock) {
        toggle.setAttribute('aria-controls', dock.id);
        toggle.setAttribute(
            'aria-expanded',
            nav.classList.contains('is-open') ? 'true' : 'false'
        );
    }

    const setMenuState = (isOpen, shouldFocusToggle = false) => {
        nav.classList.toggle('is-open', isOpen);
        if (isOpen) {
            nav.classList.remove("is-hidden");
        }

        if (toggle) {
            toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
            toggle.setAttribute('aria-label', isOpen ? 'Close menu' : 'Open menu');

            if (shouldFocusToggle) {
                toggle.focus();
            }
        }
    };

    /// Navbar behavior:
    // - Hide when scrolling down
    // - Show when scrolling up
    // - Always show near the top of the page
    let previousScrollY = window.scrollY;
    let ticking = false;

    const updateNavbarOnScroll = () => {
        const currentScrollY = window.scrollY;
        const scrollDifference = currentScrollY - previousScrollY;

        nav.classList.toggle("is-scrolled", currentScrollY > 12);

        // Always show the navbar at the top.
        if (currentScrollY <= 24) {
            nav.classList.remove("is-hidden");
            previousScrollY = currentScrollY;
            ticking = false;
            return;
        }

        // Do not react to tiny scroll movements.
        if (Math.abs(scrollDifference) < 6) {
            ticking = false;
            return;
        }

        // Do not hide the navbar while the mobile menu is open.
        if (nav.classList.contains("is-open")) {
            nav.classList.remove("is-hidden");
            previousScrollY = currentScrollY;
            ticking = false;
            return;
        }

        if (scrollDifference > 0) {
            // Scrolling down: move navbar out of view.
            nav.classList.add("is-hidden");
        } else {
            // Scrolling up: bring navbar back.
            nav.classList.remove("is-hidden");
        }

        previousScrollY = currentScrollY;
        ticking = false;
    };

    window.addEventListener(
        "scroll",
        () => {
            if (!ticking) {
                window.requestAnimationFrame(updateNavbarOnScroll);
                ticking = true;
            }
        }, { passive: true }
    );

    updateNavbarOnScroll();


    if (toggle) {
        toggle.addEventListener('click', () => {
            setMenuState(!nav.classList.contains('is-open'));
        });
    }

    const activateItem = (item) => {
        items.forEach((el) => {
            const isActive = el === item;

            el.classList.toggle("is-active", isActive);

            if (isActive) {
                el.setAttribute("aria-current", "page");
            } else {
                el.removeAttribute("aria-current");
            }
        });

        setMenuState(false);
    };


    items.forEach((item) => {
        item.addEventListener('click', () => activateItem(item));
    });

    // Close the mobile menu when the user clicks outside the navbar.
    document.addEventListener('click', (event) => {
        if (!nav.classList.contains('is-open') || nav.contains(event.target)) return;
        setMenuState(false);
    });

    // Escape closes the menu and returns focus to the menu button.
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && nav.classList.contains('is-open')) {
            setMenuState(false, true);
        }
    });

    // Keep the menu closed after switching to desktop layout.
    const desktopQuery = window.matchMedia('(min-width: 721px)');
    const closeOnDesktop = (event) => {
        if (event.matches) setMenuState(false);
    };

    if (desktopQuery.addEventListener) {
        desktopQuery.addEventListener('change', closeOnDesktop);
    } else {
        desktopQuery.addListener(closeOnDesktop);
    }

    // The brand returns to the top and resets the active state.
    const brand = nav.querySelector('.sn-nav__brand');
    if (brand) {
        brand.addEventListener('click', (event) => {
            const targetId = brand.getAttribute('href');
            if (targetId !== '#') return;

            event.preventDefault();
            setMenuState(false);
            window.scrollTo({
                top: 0,
                behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ?
                    'auto' : 'smooth'
            });

            const homeItem = items.find((item) => item.dataset.target === 'home');
            if (homeItem) activateItem(homeItem, false);
        });
    }

    // The navbar CTA follows the same contact target when one exists.
    if (cta) {
        cta.addEventListener('click', () => {
            const contactItem = items.find((item) => item.dataset.target === 'contact');
            if (contactItem) activateItem(contactItem);
        });
    }
})();