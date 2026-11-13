// Общие помощники: запросы к API, уведомления, автодополнение офферов.

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((d) => d.msg).join("; ")
      : data.detail || res.statusText;
    throw new Error(detail);
  }
  return data;
}

function toast(text, kind = "ok") {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.className = `toast ${kind}`;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), kind === "error" ? 6000 : 3000);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Поле с подсказками по офферам: onPick({id, name}) вызывается при выборе.
function offerAutocomplete(root, onPick) {
  const input = root.querySelector("input");
  const list = document.createElement("ul");
  list.className = "ac-list";
  list.hidden = true;
  root.appendChild(list);
  let timer;
  let active = -1;
  let items = [];

  const render = () => {
    list.innerHTML = items
      .map((o, i) => `<li data-i="${i}" class="${i === active ? "active" : ""}"><b>${o.id}</b> ${esc(o.name)}</li>`)
      .join("") || '<li class="muted">Ничего не найдено</li>';
    list.hidden = false;
  };
  const pick = (o) => {
    input.value = `${o.id} — ${o.name}`;
    input.dataset.offerId = o.id;
    list.hidden = true;
    onPick?.(o);
  };

  input.addEventListener("input", () => {
    delete input.dataset.offerId;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      items = await api("GET", `/api/offers?q=${encodeURIComponent(input.value)}`).catch(() => []);
      active = -1;
      render();
    }, 200);
  });
  input.addEventListener("focus", () => input.dispatchEvent(new Event("input")));
  input.addEventListener("keydown", (e) => {
    if (list.hidden) return;
    if (e.key === "ArrowDown") active = Math.min(active + 1, items.length - 1);
    else if (e.key === "ArrowUp") active = Math.max(active - 1, 0);
    else if (e.key === "Enter" && items[active]) { e.preventDefault(); pick(items[active]); return; }
    else if (e.key === "Escape") { list.hidden = true; return; }
    else return;
    e.preventDefault();
    render();
  });
  list.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[data-i]");
    if (li) pick(items[+li.dataset.i]);
  });
  input.addEventListener("blur", () => setTimeout(() => (list.hidden = true), 150));

  return {
    value: () => (input.dataset.offerId ? +input.dataset.offerId : null),
    clear: () => { input.value = ""; delete input.dataset.offerId; },
  };
}
