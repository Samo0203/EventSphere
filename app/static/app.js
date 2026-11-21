/* EventSphere single-page frontend (vanilla JS + Bootstrap 5) */
const $ = (s, r = document) => r.querySelector(s);
const S = {
  user: JSON.parse(localStorage.getItem("es_user") || "null"),
  token: localStorage.getItem("es_token") || "",
  csrf: localStorage.getItem("es_csrf") || "",
  venues: [], authMode: "login", adminTab: "dash", ticketTab: "bookings", timers: [], unread: 0,
};
const ICON = { Concert: "🎵", Workshop: "🛠️", Seminar: "🎓", Conference: "🎤", Other: "✨" };
const CATS = ["Concert", "Workshop", "Seminar", "Conference", "Other"];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = d => new Date(d).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
const lkr = n => "LKR " + Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
const isStaff = () => S.user && (S.user.role === "staff" || S.user.role === "admin");
const isAdmin = () => S.user && S.user.role === "admin";
const toInput = d => { const x = new Date(d); x.setMinutes(x.getMinutes() - x.getTimezoneOffset()); return x.toISOString().slice(0, 16); };
const pillFor = s => ({ confirmed: "ok", valid: "ok", published: "ok", accepted: "ok", offered: "warn", escalated: "warn", alternatives_offered: "warn", waiting: "warn", draft: "", cancelled: "bad", rejected: "bad", expired: "bad", declined: "bad" }[s] ?? "");
const pill = s => `<span class="pill ${pillFor(s)}">${esc(String(s).replace(/_/g, " "))}</span>`;

/* ---------- API / helpers ---------- */
async function api(path, { method = "GET", body } = {}) {
  const h = {};
  if (S.token) h.Authorization = "Bearer " + S.token;
  if (method !== "GET") h["X-CSRF-Token"] = S.csrf;       // CSRF token returned at login
  const opts = { method, headers: h };
  if (body !== undefined) { h["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(path, opts);
  let d = {}; try { d = await r.json(); } catch { }
  if (r.status === 401 && S.token) { logout(true); throw new Error("Your session expired. Please sign in again."); }
  if (!r.ok) {
    const det = d.detail;
    throw new Error(typeof det === "string" ? det : Array.isArray(det) ? det.map(x => (x.msg || "").replace("Value error, ", "")).join("; ") : "Request failed");
  }
  return d;
}
function toast(msg, type = "dark") {
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${type} border-0`;
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(msg)}</div><button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button></div>`;
  $("#toasts").appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 4500 }); t.show();
  el.addEventListener("hidden.bs.toast", () => el.remove());
}
const authModal = new bootstrap.Modal($("#authModal"));
const modal = new bootstrap.Modal($("#modal"));
function openModal(title, html, size = "") {
  $("#modalTitle").textContent = title; $("#modalBody").innerHTML = html;
  $("#modalDialog").className = "modal-dialog modal-dialog-centered modal-dialog-scrollable " + size;
  modal.show();
}
const empty = (icon, text) => `<div class="empty"><div class="big">${icon}</div>${esc(text)}</div>`;
const skeletons = n => `<div class="row g-4">${Array.from({ length: n }, () => '<div class="col-12 col-md-6 col-lg-4"><div class="skeleton"></div></div>').join("")}</div>`;
const venueOptions = sel => S.venues.map(v => `<option value="${v.id}" ${String(sel) === String(v.id) ? "selected" : ""}>${esc(v.name)} (cap. ${v.capacity})</option>`).join("");
const clearTimers = () => { S.timers.forEach(clearInterval); S.timers = []; };

/* ---------- auth ---------- */
function saveAuth() {
  localStorage.setItem("es_token", S.token); localStorage.setItem("es_csrf", S.csrf);
  localStorage.setItem("es_user", JSON.stringify(S.user));
}
function logout(silent) {
  S.token = ""; S.csrf = ""; S.user = null; S.unread = 0;
  ["es_token", "es_csrf", "es_user"].forEach(k => localStorage.removeItem(k));
  renderNav(); if (!silent) toast("Signed out", "secondary"); location.hash = "#/"; route();
}
function showAuth(mode) {
  S.authMode = mode;
  $("#authTitle").textContent = mode === "login" ? "Welcome back" : "Create your account";
  $("#nameWrap").classList.toggle("d-none", mode !== "register");
  $("#fullName").required = mode === "register";
  $("#password").autocomplete = mode === "login" ? "current-password" : "new-password";
  $("#authSwitch").textContent = mode === "login" ? "New here? Create an account" : "Already registered? Sign in";
  $("#demoBox").classList.toggle("d-none", mode !== "login");
  $("#authError").textContent = "";
  authModal.show();
}
async function submitAuth(form) {
  const err = $("#authError"); err.textContent = "";
  const btn = $("#authSubmit"); btn.disabled = true;
  try {
    if (S.authMode === "register")
      await api("/auth/register", { method: "POST", body: { full_name: $("#fullName").value, email: $("#email").value, password: $("#password").value } });
    const r = await fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: $("#email").value, password: $("#password").value }) });
    const d = await r.json();
    if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Login failed");
    S.token = d.access_token; S.csrf = d.csrf_token; S.user = d.user; saveAuth();
    authModal.hide(); form.reset(); renderNav(); toast(`Welcome, ${S.user.full_name.split(" ")[0]}!`, "success");
    route();
  } catch (e) { err.textContent = e.message; } finally { btn.disabled = false; }
}

/* ---------- notifications (bell, top right) ---------- */
function bellHtml() {
  if (!S.user) return "";
  const n = S.unread;
  return `<button class="bell-btn" data-act="notifs" title="Notifications" aria-label="Notifications${n ? `, ${n} unread` : ""}">🔔${n ? `<span class="bell-count">${n > 9 ? "9+" : n}</span>` : ""}</button>`;
}
function setUnread(n) { S.unread = n; $("#navBell").innerHTML = bellHtml(); }
async function refreshBell() {
  if (!S.user) return;
  try { setUnread((await api("/notifications/mine")).filter(x => !x.is_read).length); } catch { }
}
async function openNotifs() {
  const rows = await api("/notifications/mine");
  const unread = rows.filter(n => !n.is_read).length;
  const extra = n => n.title === "Tickets available!" ? `<button class="btn btn-brand btn-sm mt-2" data-act="gotoWaitlist">Claim now</button>`
    : n.title === "Venue hire needs review" ? `<button class="btn btn-soft btn-sm mt-2" data-act="gotoHires">Review request</button>` : "";
  openModal("Notifications", rows.length ? rows.map(n => `<div class="list-row notif ${n.is_read ? "" : "unread"}"><div><b>${esc(n.title)}</b>${n.is_read ? "" : ' <span class="pill">new</span>'}
    <div class="small text-secondary">${esc(n.message)}</div>${extra(n)}</div><div class="meta">${fmt(n.created_at)}</div></div>`).join("") : empty("🔔", "No notifications yet."));
  if (unread) { await api("/notifications/read-all", { method: "POST" }); setUnread(0); }
}

/* ---------- navigation ---------- */
async function renderNav() {
  const cur = (location.hash.replace(/^#\/?/, "") || "").split("/")[0];
  const link = (h, t) => `<a class="nav-link ${cur === h ? "active" : ""}" href="#/${h}" data-nav>${t}</a>`;
  let html = link("", "Explore");
  if (S.user) html += link("tickets", "My tickets");
  html += link("hire", "Venue hire");
  if (isStaff()) html += link("scan", "Scanner");
  if (isAdmin()) html += link("admin", "Admin");
  $("#navLinks").innerHTML = html;
  $("#navAuth").innerHTML = S.user
    ? `<span class="text-white-50 small d-none d-xl-inline">${esc(S.user.full_name)} · ${esc(S.user.role)}</span><button class="btn btn-outline-light btn-sm" data-act="logout">Sign out</button>`
    : `<button class="btn btn-outline-light btn-sm" data-act="login">Sign in</button><button class="btn btn-brand btn-sm" data-act="register">Create account</button>`;
  $("#navBell").innerHTML = bellHtml();
  refreshBell();
}
function route() {
  clearTimers(); stopCam();
  const page = (location.hash.replace(/^#\/?/, "") || "").split("/")[0];
  renderNav();
  const needsLogin = () => { $("#view").innerHTML = `<div class="container section">${empty("🔒", "Please sign in to continue.")}<div class="text-center"><button class="btn btn-brand" data-act="login">Sign in</button></div></div>`; };
  if (page === "tickets") return S.user ? viewTickets() : needsLogin();
  if (page === "hire") return viewHire();
  if (page === "scan") return isStaff() ? viewScan() : needsLogin();
  if (page === "admin") return isAdmin() ? viewAdmin() : needsLogin();
  viewHome();
}
window.addEventListener("hashchange", route);
document.addEventListener("click", e => { if (e.target.closest("[data-nav]")) bootstrap.Collapse.getInstance($("#nav"))?.hide(); });

/* ---------- HOME ---------- */
async function viewHome() {
  $("#view").innerHTML = `
  <header class="hero"><div class="orb"></div><div class="container hero-inner">
    <div class="eyebrow">Your campus. Your moments.</div>
    <h1>Make room for<br><span>something memorable.</span></h1>
    <p>Discover campus events, book your place from your phone and walk in with a secure QR ticket.</p>
    <a class="btn btn-brand btn-lg" href="#events" data-act="scrollEvents">Explore events →</a>
    <div class="hero-stats"><div><b>One platform</b><small>Events &amp; venues</small></div><div><b>Instant tickets</b><small>Unique QR entry</small></div><div><b>Smart agents</b><small>Fair, fast decisions</small></div></div>
  </div></header>
  <div class="container" id="events">
    <div class="filter-bar"><div class="row g-2">
      <div class="col-12 col-md-5"><input id="fSearch" class="form-control" placeholder="🔍  Search events…" aria-label="Search events"></div>
      <div class="col-6 col-md-3"><select id="fCat" class="form-select" aria-label="Category"><option value="">All categories</option>${CATS.map(c => `<option>${c}</option>`).join("")}</select></div>
      <div class="col-6 col-md-2"><button class="btn btn-soft w-100 h-100" data-act="toggleMore">More filters</button></div>
      <div class="col-12 col-md-2"><button class="btn btn-brand w-100" data-act="search">Search</button></div>
    </div>
    <div class="row g-2 mt-1 d-none" id="moreFilters">
      <div class="col-12 col-md-3"><label class="form-label mt-2" for="fVenue">Venue</label><select id="fVenue" class="form-select"><option value="">Any venue</option>${venueOptions()}</select></div>
      <div class="col-6 col-md-3"><label class="form-label mt-2" for="fFrom">From date</label><input id="fFrom" type="date" class="form-control"></div>
      <div class="col-6 col-md-3"><label class="form-label mt-2" for="fTo">To date</label><input id="fTo" type="date" class="form-control"></div>
      <div class="col-12 col-md-3"><label class="form-label mt-2" for="fMax">Max ticket price (LKR)</label><input id="fMax" type="number" min="0" class="form-control" placeholder="Any"></div>
    </div></div>
    <section class="section"><div class="eyebrow">What's happening</div><h2 class="mb-4">Find your next experience</h2><div id="eventGrid">${skeletons(3)}</div></section>
  </div>`;
  $("#fSearch").addEventListener("keydown", e => { if (e.key === "Enter") loadEvents(); });
  $("#fCat").addEventListener("change", loadEvents);
  ["#fVenue", "#fFrom", "#fTo", "#fMax"].forEach(id => $(id).addEventListener("change", loadEvents));
  $("#fMax").addEventListener("keydown", e => { if (e.key === "Enter") loadEvents(); });
  loadEvents();
  if (!S.venues.length) { try { S.venues = await api("/venues/"); const fv = $("#fVenue"); if (fv) fv.innerHTML = '<option value="">Any venue</option>' + venueOptions(); } catch { } }
}
async function loadEvents() {
  const p = new URLSearchParams();
  [["q", "#fSearch"], ["category", "#fCat"], ["venue_id", "#fVenue"], ["date_from", "#fFrom"], ["date_to", "#fTo"], ["max_price", "#fMax"]]
    .forEach(([k, id]) => { const v = $(id)?.value?.trim(); if (v) p.set(k, v); });
  const grid = $("#eventGrid"); if (!grid) return;
  try {
    const rows = await api("/events/?" + p);
    grid.innerHTML = rows.length ? `<div class="row g-4">${rows.map((e, i) => eventCard(e, i)).join("")}</div>` : empty("🔎", "No published events match your search. Try different filters.");
  } catch (e) { grid.innerHTML = empty("⚠️", e.message); }
}
function eventCard(e, i) {
  const left = e.tickets_left, now = new Date();
  const ended = new Date(e.end_time) <= now, live = !ended && new Date(e.start_time) <= now;
  const badge = ended ? '<span class="pill dark left">Ended</span>' : live ? '<span class="pill warn left">Started</span>'
    : left === 0 ? '<span class="pill bad left">Sold out</span>' : left <= 10 ? `<span class="pill warn left">Only ${left} left</span>` : `<span class="pill glass left">${left} left</span>`;
  const btn = ended || live ? "View details" : left === 0 ? "Join waitlist" : "View tickets";
  const cover = e.image_url ? `style="background-image:url('${esc(e.image_url)}')"` : "";
  return `<div class="col-12 col-md-6 col-lg-4"><article class="event-card">
    <div class="event-cover cover-c${i % 4}" ${cover}>${e.image_url ? "" : ICON[e.category] || "✨"}<span class="pill dark tag">${esc(e.category)}</span>${badge}</div>
    <div class="event-body"><h5>${esc(e.title)}</h5>
      <div class="meta">📍 ${esc(e.venue_name)}</div><div class="meta mb-2">🕒 ${fmt(e.start_time)}</div>
      <p class="text-secondary small mb-0">${esc((e.description || "Join us for this campus experience.").slice(0, 110))}</p>
      <div class="event-foot"><div><div class="meta">from</div><div class="price">${Number(e.min_price) ? lkr(e.min_price) : "Free"}</div></div>
      <button class="btn btn-brand" data-act="openEvent" data-id="${e.id}">${btn}</button></div></div>
  </article></div>`;
}
async function openEvent(id) {
  const e = await api("/events/" + id);
  const closed = e.status !== "published" || new Date(e.start_time) <= new Date();
  const rows = e.categories.map(c => {
    const left = c.available_quantity, maxq = left > 0 ? Math.min(6, left) : 6;
    const qty = `<select id="qty${c.id}" class="form-select" style="width:76px" aria-label="Quantity for ${esc(c.name)}">${Array.from({ length: maxq }, (_, i) => `<option>${i + 1}</option>`).join("")}</select>`;
    const action = closed ? "" : left > 0
      ? `<button class="btn btn-brand" data-act="book" data-event="${e.id}" data-cat="${c.id}" data-name="${esc(c.name)}" data-price="${esc(c.price)}">Book</button>`
      : `<button class="btn btn-soft" data-act="waitlist" data-event="${e.id}" data-cat="${c.id}">Join waitlist</button>`;
    return `<div class="list-row"><div><b>${esc(c.name)}</b><div class="meta">${Number(c.price) ? lkr(c.price) : "Free"} · ${left ? `<span class="text-success">${left} left</span>` : '<span class="text-danger">Sold out</span>'}</div></div>
      <div class="d-flex gap-2 align-items-center">${closed ? "" : qty}${action}</div></div>`;
  }).join("");
  openModal(e.title, `<div class="mb-2">${pill(e.category)} ${e.status !== "published" ? pill(e.status) : ""}</div>
    <p class="text-secondary">${esc(e.description || "")}</p>
    <div class="meta">📍 ${esc(e.venue_name)} — ${esc(e.venue_location)}</div><div class="meta mb-3">🕒 ${fmt(e.start_time)} → ${fmt(e.end_time)}</div>
    ${rows || empty("🎟️", "No ticket categories published yet.")}
    ${closed ? '<div class="alert alert-secondary py-2 mt-3 mb-0">Booking is closed for this event.</div>' : ""}
    <div class="meta mt-3">Max 6 tickets per booking · Simulated payment — no real card needed. Refunds: 100% if cancelled 48h+ before the event.</div>`);
}
const needLogin = () => { modal.hide(); showAuth("login"); };
async function doBook(d, el) {
  if (!S.user) return needLogin();
  const quantity = Number($("#qty" + d.cat).value);
  const total = Number(d.price) * quantity;
  if (!confirm(`Book ${quantity} × ${d.name} for ${total ? lkr(total) : "free"}? (simulated payment)`)) return;
  const r = await api("/bookings/", { method: "POST", body: { event_id: Number(d.event), ticket_category_id: Number(d.cat), quantity } });
  openModal("Booking confirmed 🎉", `<div class="scan-result ok mb-3">${esc(r.event)}</div>
    <p class="mb-1">${r.quantity} ticket(s) · <b>${lkr(r.amount)}</b></p><p class="meta">Simulated payment reference: <b>${esc(r.payment_reference)}</b></p>
    <a class="btn btn-brand w-100" href="#/tickets" data-act="gotoTickets">View my QR tickets</a>`);
  loadEvents(); renderNav();
}
async function doWaitlist(d) {
  if (!S.user) return needLogin();
  const quantity = Number($("#qty" + d.cat).value);
  const r = await api("/waitlist/", { method: "POST", body: { event_id: Number(d.event), ticket_category_id: Number(d.cat), quantity } });
  modal.hide(); toast(`You're on the waitlist (position ${r.position}). We'll notify you when seats free up.`, "success");
}

/* ---------- MY TICKETS ---------- */
async function viewTickets() {
  if (S.ticketTab !== "waitlist") S.ticketTab = "bookings";
  const tabs = [["bookings", "🎟️ Bookings"], ["waitlist", "⏳ Waitlist"]];
  $("#view").innerHTML = `<div class="container section"><div class="eyebrow">Your account</div><h2 class="mb-3">My tickets</h2>
    <div class="tabs">${tabs.map(([k, t]) => `<button class="tab ${S.ticketTab === k ? "active" : ""}" data-act="ticketTab" data-t="${k}">${t}</button>`).join("")}</div><div id="tabBody">${skeletons(1)}</div></div>`;
  const body = $("#tabBody");
  try {
    if (S.ticketTab === "bookings") {
      const rows = await api("/bookings/mine");
      body.innerHTML = rows.length ? rows.map(bookingCard).join("") : empty("🎫", "No bookings yet. Find an event and grab your tickets!");
    } else {
      const rows = await api("/waitlist/mine");
      body.innerHTML = rows.length ? `<div class="panel">${rows.map(w => `<div class="list-row"><div><b>${esc(w.event)}</b><div class="meta">${w.quantity} × ${esc(w.category)}</div>
        ${w.status === "offered" ? `<div class="small text-warning-emphasis fw-bold">Held for you — <span data-expires="${w.expires_at}"></span> left to claim</div>` : ""}</div>
        <div class="d-flex gap-2 align-items-center">${pill(w.status)}
        ${w.status === "offered" ? `<button class="btn btn-brand btn-sm" data-act="claim" data-id="${w.id}">Claim tickets</button>` : ""}
        ${["offered", "waiting"].includes(w.status) ? `<button class="btn btn-outline-secondary btn-sm" data-act="leaveWait" data-id="${w.id}">${w.status === "offered" ? "Decline" : "Leave"}</button>` : ""}</div></div>`).join("")}</div>` : empty("⏳", "You're not on any waitlist.");
      tickCountdown(); S.timers.push(setInterval(tickCountdown, 1000));
    }
  } catch (e) { body.innerHTML = empty("⚠️", e.message); }
}
function tickCountdown() {
  document.querySelectorAll("[data-expires]").forEach(el => {
    const s = Math.max(0, Math.floor((new Date(el.dataset.expires) - Date.now()) / 1000));
    el.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  });
}
function bookingCard(b) {
  const upcoming = new Date(b.event_start) > new Date();
  return `<div class="booking"><div class="d-flex justify-content-between flex-wrap gap-2"><div><h5 class="mb-1">${esc(b.event)}</h5>
    <div class="meta">📍 ${esc(b.venue)} · 🕒 ${fmt(b.event_start)}</div><div class="meta">${b.quantity} × ${esc(b.category)} · ${lkr(b.amount)}${b.status === "cancelled" ? ` · refunded ${lkr(b.refund_amount)}` : ""}</div></div>${pill(b.status)}</div>
    <div class="stubs">${b.tickets.map((t, i) => `<div class="stub ${t.checked_in ? "used" : ""} ${t.status === "cancelled" ? "void" : ""}">
      ${t.qr_image ? `<img class="zoomable" src="${t.qr_image}" alt="QR code ticket ${i + 1}" title="Tap to enlarge" data-act="zoomQr" data-id="${t.id}">` : '<div class="py-4">🚫</div>'}
      <div class="small fw-bold mt-1">Ticket #${t.id}</div><div class="small">${t.status === "cancelled" ? "Cancelled" : t.checked_in ? "✅ Checked in" : "Valid · tap QR to enlarge"}</div><code>${esc(t.qr_code.slice(0, 14))}…</code></div>`).join("")}</div>
    ${b.status === "confirmed" && upcoming ? `<button class="btn btn-sm btn-outline-danger mt-3" data-act="cancelBooking" data-id="${b.id}">Cancel booking</button><span class="meta ms-2">Full refund if 48h+ before the event</span>` : ""}</div>`;
}

/* ---------- VENUE HIRE ---------- */
async function viewHire() {
  $("#view").innerHTML = `<div class="container section"><div class="eyebrow">Private occasions</div><h2 class="mb-1">Hire a venue</h2><p class="text-secondary mb-4">Farewells, receptions, club meetings — our VenueAgent decides instantly and offers alternatives if your slot is taken.</p>
    <div id="hireVenues">${skeletons(3)}</div>
    <div class="row g-4 mt-1"><div class="col-12 col-lg-5"><div class="panel" id="hireFormBox"><h5>Request a venue</h5>
      <form data-form="hire" class="mt-3"><div class="mb-3"><label class="form-label" for="hVenue">Venue</label><select id="hVenue" class="form-select" required></select></div>
      <div class="row g-2"><div class="col-12 col-sm-6 mb-3"><label class="form-label" for="hStart">Starts</label><input id="hStart" type="datetime-local" class="form-control" required></div><div class="col-12 col-sm-6 mb-3"><label class="form-label" for="hEnd">Ends</label><input id="hEnd" type="datetime-local" class="form-control" required></div></div>
      <div class="mb-3"><label class="form-label" for="hGuests">Guests</label><input id="hGuests" type="number" min="1" class="form-control" required></div>
      <div class="mb-3"><label class="form-label" for="hPurpose">Purpose</label><input id="hPurpose" class="form-control" placeholder="e.g. Batch farewell party" required></div>
      <button class="btn btn-brand w-100" id="hSubmit">${S.user ? "Request venue" : "Sign in to request"}</button></form><div id="hireResult" class="mt-3" aria-live="polite"></div></div></div>
    <div class="col-12 col-lg-7"><div class="panel"><h5>My hire requests</h5><div id="myHires" class="mt-2">${S.user ? "Loading…" : '<div class="meta">Sign in to see your requests.</div>'}</div></div></div></div></div>`;
  const minNow = toInput(new Date());
  $("#hStart").min = minNow; $("#hEnd").min = minNow;
  $("#hStart").addEventListener("change", () => {
    const s = $("#hStart").value; if (!s) return;
    $("#hEnd").min = s;
    if (!$("#hEnd").value || $("#hEnd").value <= s) { const d = new Date(s); d.setHours(d.getHours() + 2); $("#hEnd").value = toInput(d); }
  });
  try {
    S.venues = await api("/venues/"); const v = S.venues.filter(x => x.is_available && x.open_for_hire);
    $("#hVenue").innerHTML = v.map(x => `<option value="${x.id}">${esc(x.name)} — cap. ${x.capacity} — ${lkr(x.price_per_hour)}/h</option>`).join("");
    $("#hireVenues").innerHTML = v.length ? `<div class="row g-4">${v.map((x, i) => `<div class="col-12 col-md-6 col-lg-4"><article class="event-card"><div class="event-cover cover-c${i % 4}" ${x.image_url ? `style="background-image:url('${esc(x.image_url)}')"` : ""}>${x.image_url ? "" : "🏛️"}<span class="pill glass left">${lkr(x.price_per_hour)}/hour</span></div>
      <div class="event-body"><h5>${esc(x.name)}</h5><div class="meta">📍 ${esc(x.location)} · 👥 up to ${x.capacity}</div><p class="text-secondary small mb-0 mt-2">${esc(x.description || "")}</p>
      <div class="event-foot"><span></span><button class="btn btn-soft" data-act="pickVenue" data-id="${x.id}">Choose</button></div></div></article></div>`).join("")}</div>` : empty("🏛️", "No venues are open for private hire right now.");
  } catch (e) { $("#hireVenues").innerHTML = empty("⚠️", e.message); }
  if (S.user) loadMyHires();
}
async function loadMyHires() {
  try { const rows = await api("/venue-hire/mine"); $("#myHires").innerHTML = rows.length ? rows.map(hireRow).join("") : '<div class="meta">No requests yet.</div>'; } catch (e) { $("#myHires").textContent = e.message; }
}
const hireRow = h => `<div class="list-row"><div><b>${esc(h.venue_name)}</b> <span class="meta">· ${h.guest_count} guests</span><div class="meta">${fmt(h.start_time)} → ${fmt(h.end_time)}</div><div class="small text-secondary">${esc(h.decision_reason || "")}</div></div><div class="text-end">${pill(h.status)}${Number(h.quoted_price) ? `<div class="price mt-1">${lkr(h.quoted_price)}</div>` : ""}</div></div>`;
async function submitHire(alt) {
  if (!S.user) return showAuth("login");
  const body = { venue_id: Number($("#hVenue").value), start_time: $("#hStart").value, end_time: $("#hEnd").value, guest_count: Number($("#hGuests").value), purpose: $("#hPurpose").value };
  const btn = $("#hSubmit"); btn.disabled = true;
  try {
    const r = await api("/venue-hire/", { method: "POST", body });
    const d = r.decision, cls = r.performative === "AGREE" ? "ok" : r.performative === "PROPOSE" || d.decision === "ESCALATE" ? "warn" : "bad";
    const title = { confirmed: "Confirmed ✅", escalated: "Sent to administrator for approval", alternatives_offered: "Slot unavailable — here are alternatives", rejected: "Request refused" }[r.hire.status];
    $("#hireResult").innerHTML = `<div class="scan-result ${cls === "ok" ? "ok" : cls === "bad" ? "bad" : ""}" style="${cls === "warn" ? "background:#fff1d6;color:#9a6200" : ""}">${title}</div>
      <p class="small mt-2 mb-1">${esc(d.reason)}</p>${d.price ? `<p class="fw-bold">Quoted price: ${lkr(d.price)}</p>` : ""}
      ${(d.alternatives || []).map(a => `<div class="alt"><b>${esc(a.venue)}</b> <span class="pill">${a.type === "venue" ? "other venue" : "other time"}</span><div class="meta">${fmt(a.start)} → ${fmt(a.end)} · ${lkr(a.price)}</div>
        <button class="btn btn-sm btn-brand mt-2" data-act="useAlt" data-v="${a.venue_id}" data-s="${a.start}" data-e="${a.end}">Request this instead</button></div>`).join("")}`;
    loadMyHires(); renderNav();
  } catch (e) { $("#hireResult").innerHTML = `<div class="scan-result bad">${esc(e.message)}</div>`; } finally { btn.disabled = false; }
}

/* ---------- SCANNER (staff / admin) ---------- */
let stream = null, scanning = false, lastScan = 0;
async function viewScan() {
  $("#view").innerHTML = `<div class="container section"><div class="eyebrow">Gate staff</div><h2 class="mb-3">Ticket scanner</h2>
  <div class="row g-4"><div class="col-12 col-lg-6"><div class="panel">
    <label class="form-label" for="scEvent">Event at the gate</label><select id="scEvent" class="form-select mb-3"></select>
    <div class="d-flex gap-2 mb-3"><button class="btn btn-brand flex-fill" data-act="startCam">📷 Start camera</button><button class="btn btn-outline-secondary" data-act="stopCam">Stop</button></div>
    <div class="cam-wrap mb-3" id="camWrap"><video id="cam" playsinline muted></video></div><canvas id="camCanvas" class="d-none"></canvas>
    <label class="form-label" for="scCode">Or type / paste the ticket code</label>
    <div class="input-group"><input id="scCode" class="form-control" placeholder="Ticket code"><button class="btn btn-brand" data-act="manualScan">Validate</button></div>
    <div class="meta mt-2">The camera needs HTTPS and permission. Manual entry always works.</div></div></div>
  <div class="col-12 col-lg-6"><div id="scResult" class="scan-result bad d-none" aria-live="assertive"></div><div class="panel mt-3"><h6>Recent scans</h6><div id="scLog" class="meta">Nothing scanned yet.</div></div></div></div></div>`;
  try { const ev = await api("/events/"); $("#scEvent").innerHTML = ev.map(e => `<option value="${e.id}">${esc(e.title)} — ${fmt(e.start_time)}</option>`).join("") || "<option value=''>No published events</option>"; } catch (e) { toast(e.message, "danger"); }
}
async function startCam() {
  if (!navigator.mediaDevices?.getUserMedia) return toast("Camera unavailable here (needs HTTPS). Use manual entry.", "warning");
  if (typeof jsQR !== "function") return toast("QR library failed to load. Use manual entry.", "warning");
  try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } }); }
  catch { return toast("Camera permission denied or unavailable. Use manual entry.", "warning"); }
  const v = $("#cam"); v.srcObject = stream; await v.play(); scanning = true; $("#camWrap").classList.add("on"); loopScan();
}
function stopCam() { scanning = false; stream?.getTracks().forEach(t => t.stop()); stream = null; $("#camWrap")?.classList.remove("on"); }
function loopScan() {
  if (!scanning) return;
  const v = $("#cam");
  if (v && v.readyState === v.HAVE_ENOUGH_DATA) {
    const c = $("#camCanvas"); c.width = v.videoWidth; c.height = v.videoHeight;
    const ctx = c.getContext("2d", { willReadFrequently: true }); ctx.drawImage(v, 0, 0, c.width, c.height);
    const img = ctx.getImageData(0, 0, c.width, c.height), code = jsQR(img.data, img.width, img.height);
    if (code && code.data && Date.now() - lastScan > 2500) { lastScan = Date.now(); submitScan(code.data); }
  }
  requestAnimationFrame(loopScan);
}
async function submitScan(code) {
  const eventId = Number($("#scEvent").value); if (!eventId) return toast("Select an event first", "warning");
  const box = $("#scResult"); box.classList.remove("d-none");
  try {
    const d = await api("/tickets/check-in", { method: "POST", body: { qr_code: code, event_id: eventId } });
    box.className = "scan-result " + (d.admitted ? "ok" : "bad");
    box.innerHTML = d.admitted ? `✅ ADMIT${d.holder ? " — " + esc(d.holder) : ""}`
      : `⛔ ${esc(d.reason)}${d.detail ? `<div class="small fw-normal mt-2">${esc(d.detail)}</div>` : ""}`;
    navigator.vibrate?.(d.admitted ? 80 : [120, 60, 120]);
    const log = $("#scLog"); if (log.textContent.startsWith("Nothing")) log.innerHTML = "";
    log.insertAdjacentHTML("afterbegin", `<div class="list-row py-2"><code>${esc(code.slice(0, 12))}…</code>${d.admitted ? '<span class="pill ok">admitted</span>' : `<span class="pill bad">${esc(d.reason)}</span>`}</div>`);
  } catch (e) { box.className = "scan-result bad"; box.textContent = e.message; }
}

/* ---------- ADMIN ---------- */
async function viewAdmin() {
  const tabs = [["dash", "📊 Dashboard"], ["events", "🎪 Events"], ["venues", "🏛️ Venues"], ["hires", "🗝️ Hire requests"], ["log", "🤖 Agent log"]];
  $("#view").innerHTML = `<div class="container section"><div class="eyebrow">Manage the experience</div><h2 class="mb-3">Organiser workspace</h2>
    <div class="tabs">${tabs.map(([k, t]) => `<button class="tab ${S.adminTab === k ? "active" : ""}" data-act="adminTab" data-t="${k}">${t}</button>`).join("")}</div><div id="adminBody">${skeletons(1)}</div></div>`;
  if (!S.venues.length) { try { S.venues = await api("/venues/"); } catch { } }
  const fn = { dash: adminDash, events: adminEvents, venues: adminVenues, hires: adminHires, log: adminLog }[S.adminTab];
  try { await fn($("#adminBody")); } catch (e) { $("#adminBody").innerHTML = empty("⚠️", e.message); }
}
async function adminDash(box) {
  const d = await api("/admin/dashboard"), t = d.totals, max = Math.max(1, ...d.checkins_by_hour.map(x => x.count));
  box.innerHTML = `<div class="row g-3 mb-4">${[["🎟️", t.tickets_sold, "Tickets sold"], ["💰", lkr(t.revenue), "Simulated revenue"], ["✅", t.check_ins, "Check-ins"], ["🗝️", t.pending_hires, "Hire requests to review"]].map(([i, v, l]) => `<div class="col-6 col-lg-3"><div class="stat"><span>${i} ${l}</span><b>${v}</b></div></div>`).join("")}</div>
  <div class="panel mb-4"><h5>Sales &amp; check-ins per event</h5>${d.events.length ? d.events.map(e => { const p = Math.min(100, Math.round(e.tickets_sold / e.capacity * 100)), c = e.tickets_sold ? Math.round(e.check_ins / e.tickets_sold * 100) : 0; return `<div class="list-row d-block"><div class="d-flex justify-content-between flex-wrap gap-2"><b>${esc(e.title)}</b>${pill(e.status)}</div>
    <div class="meta mb-2">${e.tickets_sold} / ${e.capacity} sold · ${lkr(e.revenue)} · ${e.check_ins} check-ins</div><div class="bar mb-1"><i style="width:${p}%"></i></div><div class="bar mint"><i style="width:${c}%"></i></div></div>`; }).join("") : empty("📭", "No events yet.")}
    <div class="meta mt-2">Violet = capacity sold · Mint = share of sold tickets checked in</div></div>
  <div class="panel"><h5>Check-ins over time</h5>${d.checkins_by_hour.length ? `<div class="vbars">${d.checkins_by_hour.map(x => `<div title="${x.hour}"><span>${x.count}</span><i style="height:${Math.round(x.count / max * 80) + 4}%"></i><span>${x.hour.slice(5, 10)}<br>${x.hour.slice(11, 13)}h</span></div>`).join("")}</div>` : '<div class="meta">No check-ins recorded yet.</div>'}</div>`;
}
async function adminEvents(box) {
  const rows = await api("/events/manage");
  box.innerHTML = `<div class="d-flex justify-content-between align-items-center mb-3"><h5 class="m-0">All events</h5><button class="btn btn-brand" data-act="newEvent">+ New event</button></div>
  <div class="panel">${rows.length ? rows.map(e => `<div class="list-row"><div><b>${esc(e.title)}</b> ${pill(e.status)}<div class="meta">📍 ${esc(e.venue_name)} · 🕒 ${fmt(e.start_time)}</div><div class="meta">🎟️ ${e.tickets_total - e.tickets_left} sold of ${e.tickets_total} (capacity ${e.capacity})</div></div>
    <div class="d-flex flex-wrap gap-2">${e.status !== "cancelled" ? `<button class="btn btn-sm btn-soft" data-act="editEvent" data-id="${e.id}">Edit</button><button class="btn btn-sm btn-soft" data-act="cats" data-id="${e.id}">Tickets</button>` : ""}
    ${e.status === "draft" ? `<button class="btn btn-sm btn-brand" data-act="publish" data-id="${e.id}">Publish</button>` : ""}${e.status !== "cancelled" ? `<button class="btn btn-sm btn-outline-danger" data-act="cancelEvent" data-id="${e.id}">Cancel</button>` : ""}</div></div>`).join("") : empty("🎪", "Create your first event.")}</div>`;
}
const catRow = (c = {}) => `<div class="cat-row mb-2"><div class="row g-2 align-items-end"><div class="col-12 col-sm-5"><label class="form-label">Category</label><input name="cat_name" class="form-control" value="${esc(c.name || "")}" placeholder="General" required></div>
  <div class="col-6 col-sm-3"><label class="form-label">Price</label><input name="cat_price" type="number" min="0" step="0.01" class="form-control" value="${c.price ?? ""}" required></div>
  <div class="col-6 col-sm-3"><label class="form-label">Qty</label><input name="cat_qty" type="number" min="1" class="form-control" value="${c.qty ?? ""}" required></div>
  <div class="col-12 col-sm-1 text-end"><button type="button" class="btn btn-sm btn-outline-danger" data-act="rmCat" title="Remove" aria-label="Remove category">✕</button></div></div></div>`;
function eventForm(e) {
  const edit = !!e;
  return `<form data-form="event" data-id="${e?.id || ""}"><div class="row g-2">
  <div class="col-12"><label class="form-label">Title</label><input name="title" class="form-control" value="${esc(e?.title || "")}" required></div>
  <div class="col-6"><label class="form-label">Category</label><select name="category" class="form-select">${CATS.map(c => `<option ${e?.category === c ? "selected" : ""}>${c}</option>`).join("")}</select></div>
  <div class="col-6"><label class="form-label">Venue</label><select name="venue_id" class="form-select">${venueOptions(e?.venue_id)}</select></div>
  <div class="col-12 col-sm-6"><label class="form-label">Starts</label><input name="start_time" type="datetime-local" class="form-control" value="${e ? e.start_time.slice(0, 16) : ""}" required></div>
  <div class="col-12 col-sm-6"><label class="form-label">Ends</label><input name="end_time" type="datetime-local" class="form-control" value="${e ? e.end_time.slice(0, 16) : ""}" required></div>
  <div class="col-6"><label class="form-label">Event capacity</label><input name="capacity" type="number" min="1" class="form-control" value="${e?.capacity || ""}" required></div>
  ${edit ? "" : `<div class="col-6"><label class="form-label">Save as</label><select name="status" class="form-select"><option value="draft">Draft</option><option value="published">Publish now</option></select></div>`}
  <div class="col-12"><label class="form-label">Description</label><textarea name="description" rows="3" class="form-control">${esc(e?.description || "")}</textarea></div></div>
  ${edit ? "" : `<h6 class="mt-3">Ticket categories</h6><div id="catRows">${catRow()}</div><button type="button" class="btn btn-sm btn-soft mb-3" data-act="addCat">+ Add category</button>`}
  <button class="btn btn-brand w-100 mt-2">${edit ? "Save changes" : "Create event"}</button><div class="meta mt-2">Total tickets can't exceed the venue capacity, and venue times can't overlap (30-min turnaround buffer).</div></form>`;
}
async function adminVenues(box) {
  S.venues = await api("/venues/");
  box.innerHTML = `<div class="d-flex justify-content-between align-items-center mb-3"><h5 class="m-0">Venues</h5><button class="btn btn-brand" data-act="newVenue">+ New venue</button></div>
  <div class="panel">${S.venues.map(v => `<div class="list-row"><div><b>${esc(v.name)}</b> ${v.is_available ? "" : pill("unavailable")} ${v.open_for_hire ? '<span class="pill ok">open for hire</span>' : '<span class="pill">events only</span>'}<div class="meta">📍 ${esc(v.location)} · 👥 ${v.capacity} · ${lkr(v.price_per_hour)}/hour</div></div><button class="btn btn-sm btn-soft" data-act="editVenue" data-id="${v.id}">Edit</button></div>`).join("") || empty("🏛️", "No venues yet.")}</div>`;
}
function venueForm(v) {
  return `<form data-form="venue" data-id="${v?.id || ""}"><div class="row g-2">
  <div class="col-12"><label class="form-label">Name</label><input name="name" class="form-control" value="${esc(v?.name || "")}" required></div>
  <div class="col-12"><label class="form-label">Location</label><input name="location" class="form-control" value="${esc(v?.location || "")}" required></div>
  <div class="col-6"><label class="form-label">Capacity</label><input name="capacity" type="number" min="1" class="form-control" value="${v?.capacity || ""}" required></div>
  <div class="col-6"><label class="form-label">Hourly hire rate (LKR)</label><input name="price_per_hour" type="number" min="0" step="0.01" class="form-control" value="${v?.price_per_hour ?? ""}" required></div>
  <div class="col-12"><label class="form-label">Image URL</label><input name="image_url" class="form-control" value="${esc(v?.image_url || "")}" placeholder="https://…"></div>
  <div class="col-12"><label class="form-label">Description</label><textarea name="description" rows="3" class="form-control">${esc(v?.description || "")}</textarea></div>
  <div class="col-6"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" name="is_available" ${v?.is_available === false ? "" : "checked"}><label class="form-check-label">Venue is available</label></div></div>
  <div class="col-6"><div class="form-check form-switch"><input class="form-check-input" type="checkbox" name="open_for_hire" ${v?.open_for_hire === false ? "" : "checked"}><label class="form-check-label">Open for private hire</label></div></div></div>
  <button class="btn btn-brand w-100 mt-3">${v ? "Save venue" : "Create venue"}</button></form>`;
}
async function adminHires(box) {
  const rows = await api("/venue-hire/");
  box.innerHTML = `<div class="panel"><h5>Venue hire requests</h5>${rows.length ? rows.map(h => `<div class="list-row"><div><b>${esc(h.venue_name)}</b> ${pill(h.status)}<div class="meta">${esc(h.user_name)} · ${h.guest_count} guests · ${fmt(h.start_time)} → ${fmt(h.end_time)}</div><div class="small text-secondary">${esc(h.purpose || "")} — <i>${esc(h.decision_reason || "")}</i></div></div>
    <div>${h.status === "escalated" ? `<button class="btn btn-sm btn-brand" data-act="hireDecision" data-id="${h.id}" data-d="confirmed">Approve</button> <button class="btn btn-sm btn-outline-danger" data-act="hireDecision" data-id="${h.id}" data-d="rejected">Reject</button>` : (Number(h.quoted_price) ? `<span class="price">${lkr(h.quoted_price)}</span>` : "")}</div></div>`).join("") : empty("🗝️", "No hire requests yet.")}</div>`;
}
async function adminLog(box, cid = "") {
  const d = await api("/admin/dashboard" + (cid ? "?conversation_id=" + encodeURIComponent(cid) : ""));
  const groups = {}; d.agent_messages.slice().reverse().forEach(m => (groups[m.conversation_id] ||= []).push(m));
  const ids = Object.keys(groups).reverse();
  box.innerHTML = `<h5>Agent beliefs (persistent state)</h5><div class="row g-3 mb-4">${d.agent_states.map(s => `<div class="col-12 col-sm-6 col-lg-4"><div class="state-card"><b>${esc(s.agent)}</b>${Object.keys(s.state).length ? Object.entries(s.state).map(([k, v]) => `<small>${esc(k.replace(/_/g, " "))}: <b>${esc(v)}</b></small>`).join("") : "<small>no activity yet</small>"}</div></div>`).join("")}</div>
  <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3"><h5 class="m-0">Message log (grouped by conversation)</h5><div class="d-flex gap-2"><input id="cidFilter" class="form-control form-control-sm" placeholder="Filter by conversation id" aria-label="Conversation id" value="${esc(cid)}"><button class="btn btn-sm btn-soft" data-act="logFilter">Go</button><button class="btn btn-sm btn-brand" data-act="logRefresh" aria-label="Refresh">↻</button></div></div>
  ${ids.length ? ids.map(id => { const ms = groups[id], first = ms[0]; return `<details class="conv" ${cid ? "open" : ""}><summary>${esc(first.sender)} → ${esc(first.receiver)} <span class="perf ${first.performative}">${first.performative}</span> <span class="meta">· ${ms.length} msgs · ${fmt(first.created_at)}</span></summary>
    ${ms.map(m => `<div class="msg"><b>${esc(m.sender)}</b> → <b>${esc(m.receiver)}</b> <span class="perf ${m.performative}">${m.performative}</span><code>${esc(JSON.stringify(m.content))}</code></div>`).join("")}<div class="msg meta">conversation id: <a href="#" data-act="logOne" data-id="${id}">${id}</a></div></details>`; }).join("") : empty("🤖", "No agent messages yet — make a booking!")}`;
}

/* ---------- action + form delegation ---------- */
const ACT = {
  login: () => showAuth("login"), register: () => showAuth("register"), logout: () => logout(),
  switchAuth: () => showAuth(S.authMode === "login" ? "register" : "login"),
  demo: (d) => { $("#email").value = d.e; $("#password").value = d.p; },
  scrollEvents: () => $("#events")?.scrollIntoView({ behavior: "smooth" }),
  toggleMore: () => $("#moreFilters").classList.toggle("d-none"), search: () => loadEvents(),
  openEvent: d => openEvent(d.id), book: doBook, waitlist: doWaitlist,
  notifs: openNotifs,
  gotoTickets: () => { modal.hide(); S.ticketTab = "bookings"; if (location.hash === "#/tickets") viewTickets(); else location.hash = "#/tickets"; },
  gotoWaitlist: () => { modal.hide(); S.ticketTab = "waitlist"; if (location.hash === "#/tickets") viewTickets(); else location.hash = "#/tickets"; },
  gotoHires: () => { modal.hide(); S.adminTab = "hires"; if (location.hash === "#/admin") viewAdmin(); else location.hash = "#/admin"; },
  zoomQr: (d, el) => openModal("Ticket #" + d.id, `<div class="text-center"><img src="${el.src}" alt="Large QR code for ticket ${esc(d.id)}" style="width:100%;max-width:360px;image-rendering:pixelated;border-radius:12px"><p class="meta mt-2 mb-0">Raise your screen brightness and hold the code steady at the gate.</p></div>`),
  ticketTab: d => { S.ticketTab = d.t; viewTickets(); },
  cancelBooking: async d => { if (!confirm("Cancel this booking? Refund rules apply.")) return; const r = await api(`/bookings/${d.id}/cancel`, { method: "POST" }); toast(`Cancelled. Refund: ${lkr(r.refund_amount)}`, "success"); viewTickets(); renderNav(); },
  claim: async d => { await api(`/waitlist/${d.id}/accept`, { method: "POST" }); toast("Tickets claimed! 🎉", "success"); S.ticketTab = "bookings"; viewTickets(); },
  leaveWait: async d => { await api(`/waitlist/${d.id}/decline`, { method: "POST" }); toast("Removed from waitlist", "secondary"); viewTickets(); },
  pickVenue: d => { $("#hVenue").value = d.id; $("#hireFormBox").scrollIntoView({ behavior: "smooth" }); },
  useAlt: async d => { $("#hVenue").value = d.v; $("#hStart").value = d.s; $("#hEnd").value = d.e; await submitHire(); },
  startCam, stopCam, manualScan: () => { const c = $("#scCode").value.trim(); if (c) { submitScan(c); $("#scCode").value = ""; } },
  adminTab: d => { S.adminTab = d.t; viewAdmin(); },
  newEvent: () => openModal("New event", eventForm(), "modal-lg"),
  editEvent: async d => openModal("Edit event", eventForm(await api("/events/" + d.id)), "modal-lg"),
  addCat: () => $("#catRows").insertAdjacentHTML("beforeend", catRow()), rmCat: (d, el) => { const rows = document.querySelectorAll("#catRows .cat-row"); if (rows.length > 1) el.closest(".cat-row").remove(); },
  publish: async d => { await api(`/events/${d.id}/publish`, { method: "PUT" }); toast("Event published", "success"); viewAdmin(); },
  cancelEvent: async d => { if (!confirm("Cancel this event? All bookings will be refunded in full and tickets voided.")) return; const r = await api(`/events/${d.id}/cancel`, { method: "POST" }); toast(`Event cancelled. ${r.bookings_refunded} booking(s) refunded (${lkr(r.refunded_total)}).`, "success"); viewAdmin(); },
  cats: async d => showCats(d.id),
  delCat: async d => { await api(`/events/${d.event}/categories/${d.id}`, { method: "DELETE" }); showCats(d.event); },
  newVenue: () => openModal("New venue", venueForm()), editVenue: d => openModal("Edit venue", venueForm(S.venues.find(v => v.id == d.id))),
  hireDecision: async d => {
    let note = "";
    if (d.d === "rejected") { note = prompt("Reason for rejecting (optional, the attendee will see it):", ""); if (note === null) return; }
    await api(`/venue-hire/${d.id}/decision?decision=${d.d}&note=${encodeURIComponent(note)}`, { method: "POST" });
    toast("Decision recorded and user notified", "success"); viewAdmin();
  },
  logRefresh: () => adminLog($("#adminBody"), $("#cidFilter")?.value.trim()), logFilter: () => adminLog($("#adminBody"), $("#cidFilter").value.trim()),
  logOne: d => adminLog($("#adminBody"), d.id),
};
async function showCats(id) {
  const e = await api("/events/" + id);
  openModal("Ticket categories — " + e.title, `${e.categories.map(c => `<div class="list-row"><div><b>${esc(c.name)}</b><div class="meta">${lkr(c.price)} · ${c.available_quantity}/${c.total_quantity} left</div></div><button class="btn btn-sm btn-outline-danger" data-act="delCat" data-event="${e.id}" data-id="${c.id}">Delete</button></div>`).join("") || empty("🎟️", "No categories yet.")}
  <form data-form="cat" data-id="${e.id}" class="mt-3"><div class="cat-row"><div class="row g-2 align-items-end"><div class="col-12 col-sm-5"><label class="form-label">Name</label><input name="name" class="form-control" required></div><div class="col-6 col-sm-3"><label class="form-label">Price</label><input name="price" type="number" min="0" step="0.01" class="form-control" required></div><div class="col-6 col-sm-4"><label class="form-label">Qty</label><input name="qty" type="number" min="1" class="form-control" required></div></div></div><button class="btn btn-brand w-100 mt-2">Add category</button></form>
  <div class="meta mt-2">Event capacity: ${e.capacity}. Total tickets can't exceed it.</div>`);
}
const FORMS = {
  auth: f => submitAuth(f), hire: () => submitHire(),
  event: async f => {
    const fd = new FormData(f), id = f.dataset.id;
    const body = { title: fd.get("title"), category: fd.get("category"), venue_id: Number(fd.get("venue_id")), start_time: fd.get("start_time"), end_time: fd.get("end_time"),
      capacity: Number(fd.get("capacity")), description: fd.get("description") || null };
    if (id) { await api("/events/" + id, { method: "PUT", body: { ...body, status: "draft" } }); toast("Event updated", "success"); }
    else {
      const n = fd.getAll("cat_name"), p = fd.getAll("cat_price"), q = fd.getAll("cat_qty");
      body.status = fd.get("status"); body.categories = n.map((name, i) => ({ name, price: Number(p[i]), total_quantity: Number(q[i]) }));
      await api("/events/", { method: "POST", body }); toast("Event created", "success");
    }
    modal.hide(); viewAdmin();
  },
  venue: async f => {
    const fd = new FormData(f), id = f.dataset.id;
    const body = { name: fd.get("name"), location: fd.get("location"), capacity: Number(fd.get("capacity")), price_per_hour: Number(fd.get("price_per_hour")),
      image_url: fd.get("image_url") || null, description: fd.get("description") || null, is_available: fd.has("is_available"), open_for_hire: fd.has("open_for_hire") };
    await api(id ? "/venues/" + id : "/venues/", { method: id ? "PUT" : "POST", body }); S.venues = []; toast("Venue saved", "success"); modal.hide(); viewAdmin();
  },
  cat: async f => { const fd = new FormData(f); await api(`/events/${f.dataset.id}/categories`, { method: "POST", body: { name: fd.get("name"), price: Number(fd.get("price")), total_quantity: Number(fd.get("qty")) } }); toast("Category added", "success"); showCats(f.dataset.id); },
};
document.addEventListener("click", async e => {
  const el = e.target.closest("[data-act]"); if (!el) return;
  const fn = ACT[el.dataset.act]; if (!fn) return;
  if (el.tagName === "A" && el.getAttribute("href") === "#") e.preventDefault();
  if (el.dataset.act === "gotoTickets") e.preventDefault();
  if (el.dataset.act === "scrollEvents") e.preventDefault();
  el.disabled !== undefined && (el.disabled = true);
  try { await fn(el.dataset, el); } catch (err) { toast(err.message, "danger"); }
  finally { if (el.isConnected) el.disabled = false; }
});
document.addEventListener("submit", async e => {
  const f = e.target.closest("[data-form]"); if (!f) return;
  e.preventDefault();
  const btn = f.querySelector("button:not([type=button])"); btn && (btn.disabled = true);
  try { await FORMS[f.dataset.form](f); } catch (err) { toast(err.message, "danger"); } finally { if (btn) btn.disabled = false; }
});

/* ---------- boot ---------- */
(async function boot() {
  try { S.venues = await api("/venues/"); } catch { }
  route();
  setInterval(() => { if (!document.hidden) refreshBell(); }, 30000);   // picks up waitlist offers without a page reload
})();