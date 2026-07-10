/* VEGEX — клиентский JS. Ванильный, без сборщиков. */

/* --- reveal-анимации при скролле (из концепта v3) --- */
const io = new IntersectionObserver(es => {
  es.forEach(e => {
    if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
  });
}, { threshold: .1 });
document.querySelectorAll('.rv').forEach(el => io.observe(el));

/* --- анимация калибр-баров при попадании секции spec в вид (из концепта v3) --- */
const spec = document.querySelector('.spec');
const io2 = new IntersectionObserver(es => {
  es.forEach(e => {
    if (e.isIntersecting) {
      document.querySelectorAll('.cal-bar i').forEach(b => b.style.width = b.dataset.w + '%');
      io2.disconnect();
    }
  });
}, { threshold: .25 });
if (spec) io2.observe(spec);

/* --- бургер-меню: показать/скрыть навигацию на мобильных --- */
const burger = document.querySelector('.burger');
const nav = document.querySelector('.nav ul');
if (burger && nav) {
  burger.addEventListener('click', () => {
    document.body.classList.toggle('nav-open');
  });
  nav.querySelectorAll('a').forEach(a =>
    a.addEventListener('click', () => document.body.classList.remove('nav-open'))
  );
}

/* --- форма заявки: прогрессивная отправка на Cloudflare Pages Function /contact --- */
const form = document.querySelector('[data-contact-form]');
if (form) {
  const status = form.querySelector('[data-form-status]');
  const btn = form.querySelector('button[type="submit"], .btn-o');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const setStatus = (msg, ok) => {
      if (!status) return;
      status.textContent = msg;
      status.dataset.state = ok ? 'ok' : 'err';
    };
    const payload = Object.fromEntries(new FormData(form).entries());
    const original = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = btn.dataset.sending || 'Отправляем…'; }
    try {
      const res = await fetch(form.getAttribute('action') || '/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error('bad status ' + res.status);
      form.reset();
      setStatus(form.dataset.msgOk || 'Заявка отправлена. Ответим в течение рабочего дня.', true);
    } catch (err) {
      setStatus(form.dataset.msgErr || 'Не удалось отправить. Напишите нам на info@vegex.kg.', false);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = original; }
    }
  });
}
