import QRCode from "qrcode";

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function openPrint(title, bodyHtml, extraCss = "") {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
  <style>
    *{box-sizing:border-box} body{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;color:#0f172a;margin:24px}
    h1{font-size:20px;margin:0 0 2px} .sub{color:#64748b;font-size:12px;margin-bottom:16px}
    table{width:100%;border-collapse:collapse;font-size:12px} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e2e8f0}
    th{background:#f8fafc;text-transform:uppercase;font-size:10px;letter-spacing:.04em;color:#64748b}
    .right{text-align:right}
    @media print{ .noprint{display:none} body{margin:10mm} }
    ${extraCss}
  </style></head><body>${bodyHtml}
  <div class="noprint" style="margin-top:20px"><button onclick="window.print()" style="padding:8px 14px;border:0;border-radius:8px;background:#0f766e;color:#fff;font-weight:600;cursor:pointer">Print / Save as PDF</button></div>
  </body></html>`);
  w.document.close();
  setTimeout(() => { try { w.focus(); w.print(); } catch (e) { /* user can use the button */ } }, 600);
}

async function qrFor(item) {
  const payload = `${window.location.origin}/?item=${item.id}`;
  return QRCode.toDataURL(payload, { margin: 1, width: 220 });
}

// QR sticker labels (sheet of small labels).
export async function printLabels(items, { title = "Acopio — Labels" } = {}) {
  const cards = await Promise.all(
    items.map(async (it) => {
      const qr = await qrFor(it);
      return `<div class="label">
        <img src="${qr}" width="120" height="120"/>
        <div class="info">
          <div class="name">${esc(it.canonical_name)}</div>
          <div class="meta">${esc(it.center || "")}${it.unit ? " · " + esc(it.unit) : ""}</div>
          <div class="code">${esc(it.barcode || it.id)}</div>
        </div>
      </div>`;
    })
  );
  const css = `
    .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
    .label{display:flex;gap:10px;align-items:center;border:1px solid #cbd5e1;border-radius:10px;padding:10px;page-break-inside:avoid}
    .label img{flex:0 0 auto} .info{min-width:0}
    .name{font-weight:700;font-size:14px} .meta{color:#64748b;font-size:11px;margin-top:2px}
    .code{color:#94a3b8;font-size:10px;margin-top:4px;font-family:ui-monospace,monospace}`;
  openPrint(title, `<h1>📦 Acopio — Labels</h1><div class="sub">${items.length} items</div><div class="grid">${cards.join("")}</div>`, css);
}

// Logistics-Cluster-style bin/stock cards with a blank manual ledger grid.
export async function printBinCards(items, { title = "Acopio — Bin cards", t } = {}) {
  const L = (k, d) => (t ? t(k) : d);
  const rows = Array.from({ length: 12 })
    .map(() => `<tr><td>&nbsp;</td><td></td><td></td><td></td><td></td></tr>`)
    .join("");
  const cards = await Promise.all(
    items.map(async (it) => {
      const qr = await qrFor(it);
      return `<div class="card">
        <div class="head">
          <div>
            <div class="name">${esc(it.canonical_name)}</div>
            <div class="meta">${esc(it.center || "")} · ${L("inv.unit", "Unit")}: ${esc(it.unit)} · ${L("inv.minStock", "Min")}: ${esc(it.min_quantity ?? 0)}</div>
            <div class="code">${esc(it.barcode || it.id)}</div>
          </div>
          <img src="${qr}" width="96" height="96"/>
        </div>
        <table>
          <thead><tr><th>${L("up.col.current", "Date")}</th><th>${L("dash.received", "In")}</th><th>${L("dash.dispatched", "Out")}</th><th>${L("inv.balance", "Balance")}</th><th>${L("login.fullName", "By")}</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
    })
  );
  const css = `
    .card{border:1px solid #cbd5e1;border-radius:10px;padding:14px;margin-bottom:14px;page-break-inside:avoid}
    .head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px}
    .name{font-weight:800;font-size:18px} .meta{color:#64748b;font-size:12px;margin-top:2px}
    .code{color:#94a3b8;font-size:11px;margin-top:4px;font-family:ui-monospace,monospace}
    td{height:26px}`;
  openPrint(title, `<h1>📦 Acopio — Bin / Stock cards</h1><div class="sub">${items.length} items</div>${cards.join("")}`, css);
}

// Per-center summary report for donor updates (print → Save as PDF).
export function printReport({ summary, alerts, centerName, t, lang }) {
  const L = (k, d) => (t ? t(k) : d);
  const kn = (k) => (t ? t(`kind.${k || "other"}`) : k);
  const num = (n) => (Number(n) || 0).toLocaleString(lang === "es" ? "es" : "en");
  const dt = new Date().toLocaleString(lang === "es" ? "es" : "en", { dateStyle: "long", timeStyle: "short" });
  const T = summary.totals;

  const kpis = [
    [L("dash.kpi.items", "Items"), num(T.items)],
    [L("dash.kpi.stock", "Units in stock"), num(T.units)],
    [L("dash.kpi.received", "Total received"), num(T.units_in)],
    [L("dash.kpi.dispatched", "Total dispatched"), num(T.units_out)],
    [L("dash.kpi.low", "Low stock"), num(T.low_stock)],
    [L("dash.kpi.expiring", "Expiring <=30d"), num(T.expiring_soon || 0)],
    [L("dash.kpi.expired", "Expired units"), num(T.expired_units || 0)],
  ].map(([k, v]) => `<div class="kpi"><div class="v">${v}</div><div class="k">${esc(k)}</div></div>`).join("");

  const cats = (summary.by_category || []).filter((c) => c.units > 0)
    .map((c) => `<tr><td>${esc(kn(c.kind))}</td><td class="right">${num(c.items)}</td><td class="right">${num(c.units)}</td></tr>`).join("");

  const expiring = (alerts?.expiring || []).concat(alerts?.expired || []).slice(0, 25)
    .map((b) => `<tr><td>${esc(b.item_name)}</td><td>${esc(b.expiry_date)}</td><td class="right">${num(b.qty_remaining)} ${esc(b.unit || "")}</td></tr>`).join("");

  const recent = (summary.recent_movements || []).slice(0, 20)
    .map((m) => `<tr><td>${esc(m.item_name)}</td><td>${m.type === "in" ? "+" : "−"}${num(m.quantity)} ${esc(m.unit || "")}</td><td>${esc(m.party || "")}</td><td>${esc(m.user_name || "")}</td></tr>`).join("");

  const css = `
    .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0 18px}
    .kpi{border:1px solid #e2e8f0;border-radius:10px;padding:10px} .kpi .v{font-size:20px;font-weight:800} .kpi .k{font-size:11px;color:#64748b}
    h2{font-size:14px;margin:18px 0 6px} .two{display:grid;grid-template-columns:1fr 1fr;gap:18px}`;
  const body = `
    <h1>📦 Acopio — ${esc(centerName || L("scope.allCenters", "All centers"))}</h1>
    <div class="sub">${esc(dt)}</div>
    <div class="kpis">${kpis}</div>
    <div class="two">
      <div><h2>${esc(L("dash.byCategory", "Stock by category"))}</h2>
        <table><thead><tr><th>${esc(L("inv.col.category", "Category"))}</th><th class="right">${esc(L("dash.kpi.items", "Items"))}</th><th class="right">${esc(L("common.units", "Units"))}</th></tr></thead><tbody>${cats || '<tr><td colspan=3>—</td></tr>'}</tbody></table>
      </div>
      <div><h2>${esc(L("alerts.expiring", "Expiring / expired"))}</h2>
        <table><thead><tr><th>${esc(L("inv.col.item", "Item"))}</th><th>${esc(L("inv.col.expiry", "Expiry"))}</th><th class="right">${esc(L("inv.col.stock", "Qty"))}</th></tr></thead><tbody>${expiring || '<tr><td colspan=3>—</td></tr>'}</tbody></table>
      </div>
    </div>
    <h2>${esc(L("dash.recent", "Recent movements"))}</h2>
    <table><thead><tr><th>${esc(L("inv.col.item", "Item"))}</th><th>${esc(L("inv.col.change", "Change"))}</th><th>${esc(L("inv.supplier", "Party"))}</th><th>${esc(L("login.fullName", "By"))}</th></tr></thead><tbody>${recent || '<tr><td colspan=4>—</td></tr>'}</tbody></table>`;
  openPrint(`Acopio report — ${centerName || "all"}`, body, css);
}
