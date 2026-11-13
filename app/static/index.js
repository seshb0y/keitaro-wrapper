// Страница создания кампании и список кампаний.
const form = document.getElementById("create-form");
const offerField = offerAutocomplete(document.getElementById("offer-ac"));

function fillSelect(select, options, selected, error) {
  const none = error ? "— нет доступа —" : options.length ? "— не задано —" : "— нет доступных —";
  select.innerHTML = `<option value="">${none}</option>` +
    options.map((o) => `<option value="${o.id}" ${o.id === selected ? "selected" : ""}>${esc(o.name)} (#${o.id})</option>`).join("");
}

async function loadMeta() {
  const meta = await api("GET", "/api/meta");
  document.getElementById("prefix").textContent = meta.prefix;
  document.querySelectorAll(".js-prefix").forEach((el) => (el.textContent = meta.prefix));
  fillSelect(form.group_id, meta.groups, meta.defaults.group_id, meta.errors.groups);
  fillSelect(form.domain_id, meta.domains, meta.defaults.domain_id, meta.errors.domains);
  fillSelect(form.traffic_source_id, meta.traffic_sources, meta.defaults.traffic_source_id, meta.errors.traffic_sources);
  for (const [key, err] of Object.entries(meta.errors)) {
    const note = form.querySelector(`[data-note="${key}"]`);
    const empty = !meta[key].length;
    note.textContent = err ? `Ключ API: ${err}` : empty ? "У ключа API нет ни одного" : "";
    note.className = err || empty ? "warn" : "";
  }
}

async function loadCampaigns() {
  const tbody = document.getElementById("campaigns");
  try {
    const mine = document.getElementById("mine").checked;
    const rows = await api("GET", `/api/campaigns?mine=${mine}`);
    tbody.innerHTML = rows.map((c) => `
      <tr>
        <td>${c.id}</td>
        <td>${esc(c.name)} ${c.created_here ? '<span class="tag">создана здесь</span>' : ""}</td>
        <td>${esc(c.geo || "")}</td>
        <td>${esc(c.group || "")}</td>
        <td><a class="btn small" href="/campaigns/${c.id}">Редактировать</a></td>
      </tr>`).join("") || '<tr><td colspan="5" class="muted">Кампаний нет</td></tr>';
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="error">${esc(e.message)}</td></tr>`;
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const offerId = offerField.value();
  if (!offerId) return toast("Выберите оффер из списка", "error");
  const num = (v) => (v ? +v : null);
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Создаю…";
  try {
    const res = await api("POST", "/api/campaigns", {
      name: form.elements.name.value,
      geo: form.geo.value,
      offer_id: offerId,
      group_id: num(form.group_id.value),
      domain_id: num(form.domain_id.value),
      traffic_source_id: num(form.traffic_source_id.value),
    });
    toast(`Кампания ${res.name} создана`);
    form.elements.name.value = "";
    form.geo.value = "";
    offerField.clear();
    await loadCampaigns();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Создать";
  }
});

document.getElementById("reload").addEventListener("click", loadCampaigns);
document.getElementById("mine").addEventListener("change", loadCampaigns);
loadMeta().catch((e) => toast(e.message, "error"));
loadCampaigns();
