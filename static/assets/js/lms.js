(function() {
    'use strict';
    // <form data-confirm="Are you sure?"> asks before submitting destructive actions.
    document.addEventListener('submit', function(e) {
        var msg = e.target.getAttribute && e.target.getAttribute('data-confirm');
        if (msg && !window.confirm(msg)) e.preventDefault();
    });
    // Disable submit buttons after the first click so slow requests (email, uploads) aren't sent twice.
    document.querySelectorAll('form[data-once]').forEach(function(form) {
        form.addEventListener('submit', function(e) {
            if (e.defaultPrevented) return;
            var btn = form.querySelector('button[type=submit]');
            if (btn) { btn.disabled = true;
                btn.textContent = btn.getAttribute('data-busy') || 'Working…'; }
        });
    });
})();


// Show/hide eye button on every password field (login + change password).
var EYE = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
var EYE_OFF = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18"/><path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.2"/><path d="M6.6 6.6C3.7 8.5 2 12 2 12s3.6 7 10 7c1.7 0 3.2-.4 4.5-1"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';
document.querySelectorAll('input[type=password]').forEach(function(input) {
    var wrap = document.createElement('span');
    wrap.className = 'lms-pw';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'lms-pw__btn';
    btn.setAttribute('aria-label', 'Show password');
    btn.setAttribute('aria-pressed', 'false');
    btn.innerHTML = EYE;
    btn.addEventListener('click', function() {
        var show = input.type === 'password';
        input.type = show ? 'text' : 'password';
        btn.innerHTML = show ? EYE_OFF : EYE;
        btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
        btn.setAttribute('aria-pressed', show ? 'true' : 'false');
        input.focus();
    });
    wrap.appendChild(btn);
});
// Never leave a password visible after back/forward navigation.
window.addEventListener('pageshow', function(e) {
    if (!e.persisted) return;
    document.querySelectorAll('.lms-pw input').forEach(function(i) { i.type = 'password'; });
    document.querySelectorAll('.lms-pw__btn').forEach(function(b) { b.innerHTML = EYE;
        b.setAttribute('aria-pressed', 'false'); });
});
// Friendly client-side zip check (the server re-checks everything).
document.querySelectorAll('input[data-zip-only]').forEach(function(input) {
    input.addEventListener('change', function() {
        var f = input.files && input.files[0];
        if (!f) return;
        if (!/\.zip$/i.test(f.name)) { window.alert('Only .zip files can be submitted.');
            input.value = ''; } else if (f.size > 4000000) { window.alert('The zip must be smaller than 4 MB.');
            input.value = ''; }
    });
});