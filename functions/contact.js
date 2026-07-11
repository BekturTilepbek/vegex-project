// Cloudflare Pages Function: POST /contact
// ЗАГЛУШКА. Форма принимает заявку и отвечает успехом, но данные пока
// никуда не отправляются (ни email, ни CRM, ни KV) — решение по каналу
// отправки для B2B-заявок покупателей (ЕС, GDPR) ещё не принято.
// Когда канал определится — здесь появится реальная отправка
// (fetch на email-провайдера / запись в KV / вызов CRM-вебхука).

export async function onRequestPost({ request }) {
  let data;
  try {
    data = await request.json();
  } catch {
    return json({ ok: false, error: "bad_request" }, 400);
  }

  const company = String(data.company || "").trim();
  const contact = String(data.contact || "").trim();
  const market = String(data.market || "").trim();
  const volume = String(data.volume || "").trim();

  // Минимальная валидация: должен быть хотя бы контакт для связи
  if (!contact) {
    return json({ ok: false, error: "contact_required" }, 400);
  }

  // TODO: заменить на реальную отправку, когда клиент определит канал
  console.log("[vegex:contact] новая заявка", { company, contact, market, volume });

  return json({ ok: true });
}

// GET и остальные методы — не поддерживаются
export async function onRequestGet() {
  return json({ ok: false, error: "method_not_allowed" }, 405);
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}