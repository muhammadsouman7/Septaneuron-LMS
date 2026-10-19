(function() {
    'use strict';

    // ---- 1. One click only: every form locks its buttons the moment it is submitted -----------
    function lock(form, clicked) {
        form.setAttribute('data-locked', '1');
        form.querySelectorAll('button[type=submit], input[type=submit]').forEach(function(b) {
            if (!b.hasAttribute('data-label')) b.setAttribute('data-label', b.tagName === 'BUTTON' ? b.textContent : b.value);
            if (b === clicked || (!clicked && b === form.querySelector('button[type=submit], input[type=submit]'))) {
                var busy = b.getAttribute('data-busy') || 'Working…';
                if (b.tagName === 'BUTTON') b.textContent = busy;
                else b.value = busy;
            }
            b.disabled = true;
            b.setAttribute('aria-busy', 'true');
        });
    }

    function unlock(form) {
        form.removeAttribute('data-locked');
        form.querySelectorAll('button[type=submit], input[type=submit]').forEach(function(b) {
            if (b.hasAttribute('data-label')) {
                if (b.tagName === 'BUTTON') b.textContent = b.getAttribute('data-label');
                else b.value = b.getAttribute('data-label');
            }
            b.disabled = false;
            b.removeAttribute('aria-busy');
        });
    }
    document.addEventListener('submit', function(e) {
        var form = e.target;
        if (!form || form.tagName !== 'FORM') return;
        var msg = form.getAttribute('data-confirm');
        if (msg && !window.confirm(msg)) { e.preventDefault(); return; } // "Are you sure?" on destructive actions
        if (e.defaultPrevented) return; // handled elsewhere (e.g. zip upload)
        if (form.getAttribute('data-locked')) { e.preventDefault(); return; }
        var clicked = e.submitter || null;
        if (clicked && clicked.name) { // keep the clicked button's value in the request
            var h = document.createElement('input');
            h.type = 'hidden';
            h.name = clicked.name;
            h.value = clicked.value;
            form.appendChild(h);
        }
        lock(form, clicked);
    });
    // Coming back with the Back button must not leave a form stuck.
    window.addEventListener('pageshow', function(e) {
        if (!e.persisted) return;
        document.querySelectorAll('form[data-locked]').forEach(unlock);
        document.querySelectorAll('.lms-pw input').forEach(function(i) { i.type = 'password'; });
        document.querySelectorAll('[data-pw-new]').forEach(function(i) { i.dispatchEvent(new Event('input')); });
    });

    // ---- 2. Show/hide eye on every password field ---------------------------------------------
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

    // ---- 3. Live password rules (green tick / red cross) --------------------------------------
    document.querySelectorAll('form[data-pw-form]').forEach(function(form) {
        var pw = form.querySelector('[data-pw-new]');
        var cf = form.querySelector('[data-pw-confirm]');
        var go = form.querySelector('[data-pw-submit]');
        var items = {};
        form.querySelectorAll('[data-rule]').forEach(function(li) { items[li.getAttribute('data-rule')] = li; });

        function check() {
            var v = pw.value;
            var ok = {
                len: v.length >= 8,
                lower: /[a-z]/.test(v),
                upper: /[A-Z]/.test(v),
                number: /[0-9]/.test(v),
                special: /[^A-Za-z0-9]/.test(v),
                match: v.length > 0 && v === cf.value
            };
            var all = true;
            Object.keys(ok).forEach(function(k) {
                if (items[k]) items[k].classList.toggle('is-ok', ok[k]);
                if (!ok[k]) all = false;
            });
            if (!form.getAttribute('data-locked')) go.disabled = !all;
        }
        pw.addEventListener('input', check);
        cf.addEventListener('input', check);
        check();
    });

    // ---- 4. Zip submissions: upload straight to storage (no 4 MB server limit) ----------------
    document.querySelectorAll('form[data-direct-upload]').forEach(function(form) {
        var file = form.querySelector('input[type=file]');
        var path = form.querySelector('input[name=upload_path]');
        var max = parseInt(form.getAttribute('data-max-bytes'), 10) || 50000000;

        function problem(f) {
            if (!/\.zip$/i.test(f.name)) return 'Only .zip files can be submitted.';
            if (f.size > max) return 'The zip must be smaller than ' + Math.round(max / 1000000) + ' MB.';
            return '';
        }
        file.addEventListener('change', function() {
            path.value = '';
            var f = file.files && file.files[0];
            var msg = f ? problem(f) : '';
            if (msg) {
                window.alert(msg);
                file.value = '';
            }
        });
        form.addEventListener('submit', function(e) {
            var f = file.files && file.files[0];
            if (!f || path.value) return; // nothing to upload, or already uploaded
            e.preventDefault();
            if (form.getAttribute('data-locked')) return;
            var msg = problem(f);
            if (msg) { window.alert(msg); return; }
            var btn = form.querySelector('button[type=submit]');
            lock(form, btn);

            function say(t) { btn.textContent = t; }

            function fail(text) {
                unlock(form);
                window.alert(text);
            }
            var fd = new FormData();
            fd.append('_csrf', form.querySelector('input[name=_csrf]').value);
            fd.append('filename', f.name);
            fd.append('size', String(f.size));
            say('Preparing…');
            fetch(form.getAttribute('data-upload-url'), { method: 'POST', body: fd, credentials: 'same-origin' })
                .then(function(r) { return r.json().then(function(j) { return { ok: r.ok, j: j }; }); })
                .then(function(res) {
                    if (!res.ok) throw new Error(res.j.error || 'Could not start the upload.');
                    return new Promise(function(resolve, reject) {
                        var xhr = new XMLHttpRequest();
                        xhr.open('PUT', res.j.url);
                        if (res.j.apikey) xhr.setRequestHeader('apikey', res.j.apikey);
                        xhr.setRequestHeader('x-upsert', 'false');
                        xhr.upload.onprogress = function(ev) {
                            if (ev.lengthComputable) say('Uploading ' + Math.round(100 * ev.loaded / ev.total) + '%');
                        };
                        xhr.onload = function() {
                            if (xhr.status >= 200 && xhr.status < 300) resolve(res.j);
                            else reject(new Error('The upload failed (' + xhr.status + '). Please try again.'));
                        };
                        xhr.onerror = function() { reject(new Error('Network error during upload. Please try again.')); };
                        var body = new FormData();
                        body.append('cacheControl', '3600');
                        body.append('', f);
                        xhr.send(body);
                    });
                })
                .then(function(info) {
                    path.value = info.path;
                    say('Checking…');
                    form.submit();
                })
                .catch(function(err) { fail(err.message || 'Upload failed.'); });
        });
    });

    // ---- 5. Success messages appear as a toast that fades away --------------------------------
    document.querySelectorAll('.lms-main > .lms-flash--success').forEach(function(el) {
        el.classList.add('is-toast');
        el.addEventListener('click', function() { el.remove(); });
        setTimeout(function() {
            el.classList.add('is-leaving');
            setTimeout(function() { el.remove(); }, 500);
        }, 6000);
    });
})();