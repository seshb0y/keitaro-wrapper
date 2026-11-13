// Редактор потоков кампании: черновик долей → Push в Keitaro или Cancel.
const root = document.getElementById("streams");
const campaignId = +root.dataset.campaign;
const names = {}; // offer_id → название (из Keitaro и из поиска)
const streams = {}; // stream_id → {view, saved, draft}

const fmtMoney = (v) => (+v || 0).toFixed(2);
const clone = (x) => JSON.parse(JSON.stringify(x));
const strip = (items) => items.map(({ offer_id, share, pinned, removed }) => ({ offer_id, share, pinned, removed }));
const isDirty = (s) => JSON.stringify(strip(s.draft)) !== JSON.stringify(strip(s.saved));

async function load() {
  root.innerHTML = '<p class="muted">Загрузка из Keitaro…</p>';
  try {
    const data = await api("GET", `/api/campaigns/${campaignId}`);
    const c = data.campaign;
    document.getElementById("c-name").textContent = c.name;
    document.getElementById("open-kt").href = c.keitaro_url;
    document.getElementById("c-meta").textContent =
      `ID ${c.id} · группа ${c.group_id ?? "—"} · домен ${c.domain_id ?? "—"} · источник ${c.traffic_source_id || "—"}`;
    root.innerHTML = "";
    for (const view of data.streams) {
      view.offers.forEach((o) => (names[o.offer_id] = o.name));
      streams[view.id] = { view, saved: clone(view.offers), draft: clone(view.offers) };
      const el = document.createElement("section");
      el.className = "card stream";
      el.id = `stream-${view.id}`;
      root.appendChild(el);
      render(view.id);
    }
    if (!data.streams.length) root.innerHTML = '<p class="muted">В кампании нет потоков</p>';
  } catch (e) {
    root.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function filtersText(filters) {
  return filters.map((f) => `${f.name} ${f.mode === "accept" ? "∈" : "∉"} ${(f.payload || []).join(", ")}`).join("; ");
}

function render(id) {
  const s = streams[id];
  const el = document.getElementById(`stream-${id}`);
  const v = s.view;
  const head = `
    <div class="stream-head">
      <div><b>Поток: ${esc(v.name)}</b> <span class="muted">#${v.position} · stream_id ${v.id}</span></div>
      ${v.filters.length ? `<div class="muted">Фильтры: ${esc(filtersText(v.filters))}</div>` : ""}
    </div>`;

  if (!v.is_offer_stream) {
    el.innerHTML = head + `<p>Редирект → <a href="${esc(v.action_payload)}" target="_blank" rel="noopener">${esc(v.action_payload)}</a></p>`;
    return;
  }

  const dirty = isDirty(s);
  const total = s.draft.filter((o) => !o.removed).reduce((a, o) => a + o.share, 0);
  el.classList.toggle("dirty", dirty);
  el.innerHTML = head + `
    ${dirty ? `<div class="draft-bar">
        <span>Изменения не отправлены. Сумма долей: <b class="${total === 100 ? "" : "error"}">${total}%</b></span>
        <button class="btn primary" data-act="push">⇪ Push to Keitaro</button>
        <button class="btn" data-act="cancel">✕ Cancel</button>
      </div>` : ""}
    <table class="table offers">
      <thead><tr><th>Оффер</th><th class="num">Доля</th><th class="num">Клики 7д</th><th class="num">Конв.</th><th class="num">Доход</th><th></th></tr></thead>
      <tbody>${s.draft.map((o) => row(o)).join("")}</tbody>
    </table>
    <div class="add-row">
      <div class="ac" data-ac><input placeholder="Добавить оффер: поиск по названию или ID"></div>
      <button class="btn" data-act="add">Добавить</button>
    </div>`;

  const ac = offerAutocomplete(el.querySelector("[data-ac]"), (o) => (names[o.id] = o.name));
  el.querySelector('[data-act="add"]').onclick = () => {
    const offerId = ac.value();
    if (!offerId) return toast("Выберите оффер из списка", "error");
    add(id, offerId);
  };
  el.onclick = (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn || btn.dataset.act === "add") return;
    e.preventDefault();
    const offerId = +btn.dataset.offer;
    ({ push, cancel, remove, back, pin, share })[btn.dataset.act]?.(id, offerId);
  };
}

function row(o) {
  const st = o.stats || { clicks: 0, conversions: 0, revenue: 0 };
  return `
    <tr class="${o.removed ? "removed" : ""}">
      <td>${esc(names[o.offer_id] || `Оффер ${o.offer_id}`)}${o.removed ? ' <span class="muted">(снят)</span>' : ""}</td>
      <td class="num nowrap">
        <a href="#" class="share" data-act="share" data-offer="${o.offer_id}" title="Задать долю вручную">${o.share}%</a>
        <button class="pin ${o.pinned ? "on" : ""}" data-act="pin" data-offer="${o.offer_id}" ${o.removed ? "disabled" : ""}
          title="${o.pinned ? "Открепить: доля снова делится поровну" : "Закрепить долю: при пересчёте не меняется"}">📌</button>
      </td>
      <td class="num">${st.clicks}</td>
      <td class="num">${st.conversions}</td>
      <td class="num">${fmtMoney(st.revenue)}</td>
      <td class="actions">${o.removed
        ? `<button class="btn small" data-act="back" data-offer="${o.offer_id}">↺ Bring back</button>`
        : `<button class="btn small danger" data-act="remove" data-offer="${o.offer_id}">🗑 Remove</button>`}</td>
    </tr>`;
}

// Пересчёт делает сервер (одна реализация правил, она же покрыта тестами).
async function rebalance(id, items) {
  const s = streams[id];
  try {
    const res = await api("POST", "/api/rebalance", { items: strip(items) });
    const stats = Object.fromEntries(s.draft.concat(s.saved).map((o) => [o.offer_id, o.stats]));
    s.draft = res.items.map((o) => ({ ...o, stats: stats[o.offer_id] }));
    render(id);
  } catch (e) {
    toast(e.message, "error");
  }
}

const find = (id, offerId) => streams[id].draft.find((o) => o.offer_id === offerId);

function add(id, offerId) {
  const existing = find(id, offerId);
  if (existing && !existing.removed) return toast("Этот оффер уже в потоке", "error");
  if (existing) return back(id, offerId);
  rebalance(id, [...streams[id].draft, { offer_id: offerId, share: 0, pinned: false, removed: false }]);
}

function remove(id, offerId) {
  const items = clone(streams[id].draft);
  items.find((o) => o.offer_id === offerId).removed = true;
  rebalance(id, items);
}

function back(id, offerId) {
  const items = clone(streams[id].draft);
  Object.assign(items.find((o) => o.offer_id === offerId), { removed: false, pinned: false, share: 0 });
  rebalance(id, items);
}

function pin(id, offerId) {
  const items = clone(streams[id].draft);
  const o = items.find((x) => x.offer_id === offerId);
  o.pinned = !o.pinned;
  rebalance(id, items);
}

// Клик по доле → поле ввода на месте. Enter/уход с поля — применить (доля закрепится), Esc — отмена.
function share(id, offerId) {
  const o = find(id, offerId);
  if (o.removed) return;
  const link = document.querySelector(`#stream-${id} .share[data-offer="${offerId}"]`);
  const input = document.createElement("input");
  input.type = "number";
  input.min = 0;
  input.max = 100;
  input.value = o.share;
  input.className = "share-input";
  input.title = "Доля закрепится, остальное поделится поровну";
  link.replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const finish = (apply) => {
    if (done) return;
    done = true;
    const n = Number(input.value);
    if (!apply || n === o.share) return render(id);
    if (!Number.isInteger(n) || n < 0 || n > 100) {
      toast("Нужно целое число от 0 до 100", "error");
      return render(id);
    }
    const items = clone(streams[id].draft);
    Object.assign(items.find((x) => x.offer_id === offerId), { share: n, pinned: true });
    rebalance(id, items);
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") finish(true);
    if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
}

function cancel(id) {
  streams[id].draft = clone(streams[id].saved);
  render(id);
}

async function push(id) {
  const s = streams[id];
  const btn = document.querySelector(`#stream-${id} [data-act="push"]`);
  btn.disabled = true;
  try {
    const view = await api("PUT", `/api/streams/${id}/offers`, { items: strip(s.draft) });
    view.offers.forEach((o) => (names[o.offer_id] = o.name));
    streams[id] = { view, saved: clone(view.offers), draft: clone(view.offers) };
    render(id);
    toast("Доли отправлены в Keitaro");
  } catch (e) {
    btn.disabled = false;
    toast(e.message, "error");
  }
}

document.getElementById("fetch").addEventListener("click", () => {
  const dirty = Object.values(streams).some(isDirty);
  if (dirty) return toast("Есть неотправленные изменения: сначала Push или Cancel", "error");
  load();
});
load();
