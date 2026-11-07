// Dựng video OTARadar trên một sân khấu 1920×1080. Mọi chuyển động là Web Animations với mốc
// tuyệt đối (giây) lấy từ assets/timeline.json (giọng đọc), nên render.py tua được tới từng khung:
// window.seek(t). Ảnh dashboard + toạ độ vùng nổi bật lấy từ assets/shots (capture.py).

const EASE = "cubic-bezier(.22,.61,.36,1)";
const EASE_IO = "cubic-bezier(.65,0,.35,1)";
const BACK = "cubic-bezier(.34,1.56,.64,1)";
const ICON = `<svg viewBox="0 0 28 28" width="100%" height="100%"><rect x="1" y="1" width="26" height="26" rx="6" fill="#0062ff"/><g stroke="#fff" stroke-width="2.2" stroke-linecap="round"><path d="M14 7.5v13M7.5 14h13M9.4 9.4l9.2 9.2M18.6 9.4l-9.2 9.2"/></g></svg>`;
const CURSOR = `<svg viewBox="0 0 24 24" width="100%" height="100%"><path d="M3 2l7.5 19 2.6-7.9L21 10.6z" fill="#fff" stroke="#0f1733" stroke-width="1.6" stroke-linejoin="round"/></svg>`;

// Cửa sổ dashboard: ảnh chụp rộng 1440 px CSS hiển thị trong khung 1328×830.
const VW = 1328, VH = 830, B = VW / 1440;
const cues = [];
const root = document.getElementById("root");

function el(html, parent = root) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  const node = t.content.firstElementChild;
  parent.appendChild(node);
  return node;
}

// Một chuyển động cho từng thuộc tính. Lần đầu của một thuộc tính trên phần tử giữ giá trị đầu cả
// trước khi chạy (fill both); các lần sau chỉ giữ giá trị cuối (forwards) để không đè lần trước.
const seen = new WeakMap();
function tw(node, props, t, d, ease = EASE) {
  const used = seen.get(node) || new Set();
  seen.set(node, used);
  for (const [p, vals] of Object.entries(props)) {
    const first = !used.has(p);
    used.add(p);
    node.animate(vals.map((v) => ({ [p]: v })), {
      delay: t * 1000, duration: Math.max(1, d * 1000), fill: first ? "both" : "forwards", easing: ease,
    });
  }
}
const fadeIn = (n, t, d = 0.45, y = 18) =>
  tw(n, { opacity: [0, 1], transform: [`translateY(${y}px)`, "translateY(0px)"] }, t, d);
const fadeOut = (n, t, d = 0.35) => tw(n, { opacity: [1, 0] }, t, d);

async function main() {
  const TL = await (await fetch("assets/timeline.json")).json();
  const BOX = await (await fetch("assets/shots/boxes.json")).json();
  const S = Object.fromEntries(TL.scenes.map((s) => [s.id, s]));
  const L = (id, i) => S[id].lines[i];

  // ---------- Cửa sổ dashboard (dùng từ cảnh giới thiệu tới trước cảnh kêu gọi) ----------
  const win = el(`<div id="win" class="abs" style="opacity:0">
      <div class="bar"><span class="dot" style="background:#ff5f57"></span><span class="dot" style="background:#febc2e"></span>
      <span class="dot" style="background:#28c840"></span><div class="tab"><span style="width:16px;height:16px">${ICON}</span>OTARadar</div></div>
      <div id="view"><div id="cam"></div><div id="flash"></div></div></div>`);
  const camEl = win.querySelector("#cam");
  const flash = win.querySelector("#flash");
  const names = ["today", "today_dialog", "today_applied", "calendar_rooms", "calendar_price", "calendar_diff", "market"];
  const shots = {}, pageH = {};
  for (const n of names) {
    const img = el(`<img class="shot" src="assets/shots/${n}.png">`, camEl);
    await img.decode();
    shots[n] = img;
    pageH[n] = img.naturalHeight / 2;
  }
  let current = null;
  function show(name, t, fade = 0.3) {
    tw(shots[name], { opacity: [0, 1] }, t, fade);
    if (current && current !== name) tw(shots[current], { opacity: [1, 0] }, t + fade, 0.05);
    current = name;
  }
  // Sang trang khác: cắt cảnh, che bằng một nháy trắng ngắn như lúc trang tải (không chồng mờ hai
  // giao diện khác nhau). Đổi chế độ trên cùng trang thì dùng show() (hoà mờ).
  function navigate(name, t) {
    tw(flash, { opacity: [0, 0.92] }, t - 0.1, 0.1, "linear");
    show(name, t, 0.01);
    tw(flash, { opacity: [0.92, 0] }, t + 0.02, 0.3, "ease-out");
  }
  // Camera: tâm (cx, cy) theo px CSS của trang, z = 1 khi trang vừa khít chiều ngang khung.
  let camNow = null;
  function camT(cx, cy, z, shot) {
    const s = B * z;
    let tx = VW / 2 - cx * s, ty = VH / 2 - cy * s;
    tx = Math.min(0, Math.max(VW - 1440 * s, tx));
    const h = pageH[shot] * s;
    ty = h <= VH ? 0 : Math.min(0, Math.max(VH - h, ty));
    return `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${s.toFixed(4)})`;
  }
  function cam(t, d, cx, cy, z, shot, ease = EASE_IO) {
    const to = camT(cx, cy, z, shot);
    tw(camEl, { transform: [camNow ?? to, to] }, t, d, ease);
    camNow = to;
  }
  const center = (b) => [b.x + b.w / 2, b.y + b.h / 2];
  // Khung nổi bật/vùng sáng theo toạ độ trang; `pulse` = mốc nhấp nháy (tạo trước lúc tắt để
  // lần tắt luôn thắng).
  function mark(cls, b, t0, t1, pad = 8, pulse = null) {
    const n = el(`<div class="${cls}" style="left:${b.x - pad}px;top:${b.y - pad}px;width:${b.w + 2 * pad}px;height:${b.h + 2 * pad}px"></div>`, camEl);
    tw(n, { opacity: [0, 1], transform: ["scale(1.04)", "scale(1)"] }, t0, 0.4);
    if (pulse !== null) tw(n, { opacity: [1, 0.35, 1, 0.35, 1] }, pulse, 1.6, "linear");
    fadeOut(n, t1, 0.35);
    return n;
  }
  // Con trỏ: đi qua các điểm (t, x, y) theo px trang, nhấp ở các mốc `clicks`.
  function cursor(z, path, clicks, hideAt) {
    const size = 30 / (B * z);
    const n = el(`<div class="cursor" style="width:${size}px;height:${size}px">${CURSOR}</div>`, camEl);
    const [p0] = path;
    tw(n, { opacity: [0, 1] }, p0.t, 0.25);
    tw(n, { transform: [`translate(${p0.x}px, ${p0.y}px)`, `translate(${p0.x}px, ${p0.y}px)`] }, p0.t, 0.01);
    for (let i = 1; i < path.length; i++) {
      const a = path[i - 1], b = path[i];
      tw(n, { transform: [`translate(${a.x}px, ${a.y}px)`, `translate(${b.x}px, ${b.y}px)`] }, a.t + (a.hold || 0), b.t - a.t - (a.hold || 0), EASE_IO);
    }
    for (const c of clicks) {
      const r = 30 / (B * z);
      const rp = el(`<div class="ripple" style="left:${c.x - r}px;top:${c.y - r}px;width:${2 * r}px;height:${2 * r}px;border-width:${3 / (B * z)}px"></div>`, camEl);
      tw(rp, { opacity: [0, 0.9, 0], transform: ["scale(.3)", "scale(.8)", "scale(1.3)"] }, c.t, 0.5, "ease-out");
      tw(n, { scale: ["1", "0.85", "1"] }, c.t - 0.05, 0.2, "ease-out");
      cues.push({ kind: "click", t: c.t });
    }
    fadeOut(n, hideAt, 0.3);
  }

  // ---------- Chữ chú thích phía trên cửa sổ ----------
  const caps = [];
  function caption(kicker, title, t, until) {
    const n = el(`<div class="abs cap"><div class="kicker">${kicker}</div><div class="title">${title}</div></div>`);
    fadeIn(n, t, 0.5, 14);
    fadeOut(n, until, 0.3);
    caps.push(n);
  }

  // ---------- Phụ đề (giọng đọc) ----------
  const subsBox = document.getElementById("subs");
  for (const s of TL.scenes) {
    if (s.id === "hook" || s.id === "cta") continue; // chữ lớn trên màn đã trùng lời đọc
    s.lines.forEach((ln, i) => {
      const n = el(`<div class="sub">${ln.text}</div>`, subsBox);
      const next = s.lines[i + 1];
      const out = Math.min(ln.end + 0.35, next ? next.start - 0.02 : s.start + s.dur - 0.1);
      tw(n, { opacity: [0, 1] }, ln.start - 0.05, 0.15, "linear");
      tw(n, { opacity: [1, 0] }, out - 0.12, 0.12, "linear");
    });
  }

  // =========================== 1. HOOK ===========================
  const hk = S.hook;
  const pages = [["#3b5bdb", "#845ef7"], ["#0b7285", "#3bc9db"], ["#5f3dc4", "#e64980"], ["#2b8a3e", "#94d82d"],
                 ["#c2255c", "#ff922b"], ["#1864ab", "#4dabf7"], ["#862e9c", "#f06595"]];
  const fake = el(`<div class="abs fake" style="left:440px;top:170px">
      <div class="tabs">${pages.map((_, i) => `<div class="t">Đối thủ ${i + 1}</div>`).join("")}<div class="ind"></div></div>
      <div class="pages">${pages.map(([a, b], i) => `<div class="pg"><div class="hero" style="background:linear-gradient(120deg,${a},${b})"></div>
        <div class="l" style="width:${55 + (i * 7) % 30}%"></div><div class="l" style="width:${35 + (i * 11) % 40}%"></div>
        <div class="price">${["1.650.000", "1.890.000", "1.540.000", "1.760.000", "2.120.000", "1.600.000", "1.980.000"][i]} ₫</div></div>`).join("")}</div></div>`);
  const ind = fake.querySelector(".ind"), pg = fake.querySelector(".pages");
  const stepKF = (f) => [...pages.map((_, i) => ({ transform: f(i), easing: "steps(1, end)" })), { transform: f(0) }];
  ind.animate(stepKF((i) => `translateX(${i * 144}px)`), { duration: 2450, iterations: 2.6, fill: "both", delay: 300 });
  pg.animate(stepKF((i) => `translateY(${-554 * i}px)`), { duration: 2450, iterations: 2.6, fill: "both", delay: 300 });
  tw(fake, { opacity: [0, 1] }, 0, 0.5);
  tw(fake, { transform: ["scale(1.06)", "scale(1)"] }, 0, 5.9, "linear");

  const clock1 = el(`<div class="abs clock"><span class="lab">Sáng thứ Bảy</span>06<span class="colon">:</span>58</div>`);
  fadeIn(clock1, 0.2, 0.5);
  clock1.querySelector(".colon").animate([{ opacity: 1, easing: "steps(1,end)" }, { opacity: 0.25, easing: "steps(1,end)" }, { opacity: 1 }],
    { duration: 1000, iterations: 6, fill: "both" });
  const q = el(`<div class="abs hook-q">${"Đối thủ đêm nay bán bao nhiêu?".split(" ").map((w) => `<span>${w}</span>`).join(" ")}</div>`);
  [...q.children].forEach((w, i) => tw(w, { opacity: [0, 1], transform: ["translateY(26px)", "translateY(0)"] }, 0.35 + i * 0.16, 0.45, BACK));
  const q2 = el(`<div class="abs hook-q2">Bạn có chắc không?</div>`);
  fadeIn(q2, L("hook", 1).start, 0.4, 12);

  // =========================== 2. PAIN ===========================
  const pn = S.pain, t2 = pn.start;
  fadeOut(q, t2 - 0.1, 0.3); fadeOut(q2, t2 - 0.1, 0.3); fadeOut(clock1, t2, 0.3);
  tw(fake, { transform: ["scale(1)", "translate(-400px, 70px) scale(.6)"] }, t2, 0.8, EASE_IO);
  tw(fake, { opacity: [1, 0.85] }, t2, 0.8);

  const clock2 = el(`<div class="abs clock"><span class="lab">Sáng thứ Bảy</span>07:<div class="mins"><div class="strip">${
    Array.from({ length: 41 }, (_, i) => `<div>${String(i).padStart(2, "0")}</div>`).join("")}</div></div></div>`);
  fadeIn(clock2, t2 + 0.1, 0.4);
  const strip = clock2.querySelector(".strip");
  strip.animate([{ transform: "translateY(0)" }, { transform: `translateY(${-76 * 40}px)` }],
    { delay: (t2 + 0.3) * 1000, duration: 4800, easing: "steps(40, end)", fill: "both" });

  const rows = [["Đối thủ 1", "1.650.000", "1.890.000", "1.540.000"], ["Đối thủ 2", "1.780.000", "?", "1.620.000"],
                ["Đối thủ 3", "1.520.000", "1.760.000", "1.490.000"], ["Đối thủ 4", "?", "2.050.000", "1.700.000"],
                ["Đối thủ 5", "1.600.000", "1.880.000", "?"], ["Đối thủ 6", "1.710.000", "1.950.000", "1.560.000"]];
  const sheet = el(`<div class="abs sheet" style="left:1010px;top:250px;opacity:0">
      <div class="hd"><span>▦</span> Giá đối thủ (tự ghi).xlsx</div>
      <table><tr><th>Khách sạn</th><th>T6 30/10</th><th>T7 31/10</th><th>CN 01/11</th></tr>
      ${rows.map((r) => `<tr>${r.map((c, j) => j === 0 ? `<td>${c}</td>` : `<td class="${c === "?" ? "q" : ""}"><span>${c}</span></td>`).join("")}</tr>`).join("")}
      </table></div>`);
  tw(sheet, { opacity: [0, 1], transform: ["translateX(80px)", "translateX(0)"] }, t2 + 0.25, 0.6);
  const cells = [...sheet.querySelectorAll("td span")];
  cells.forEach((c, i) => {
    const at = t2 + 0.7 + i * 0.22;
    tw(c, { opacity: [0, 1] }, at, 0.08, "linear");
    tw(c.parentElement, { backgroundColor: ["rgba(255,205,53,.55)", "rgba(255,205,53,0)"] }, at, 0.6);
  });
  const ph = el(`<div class="abs pain-h">Đặt giá theo <em>cảm tính?</em></div>`);
  fadeIn(ph, L("pain", 0).end - 1.7, 0.5);
  const note = el(`<div class="abs note" style="left:1480px;top:660px">1.450.000 ₫ ?</div>`);
  tw(note, { opacity: [0, 1], transform: ["rotate(-14deg) scale(.6)", "rotate(-5deg) scale(1)"] }, L("pain", 0).end - 1.2, 0.5, BACK);
  const arrow = (up) => `<svg width="56" height="56" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="rgba(239,68,68,.25)"/><path d="${up ? "M12 17V7m0 0l-4 4m4-4l4 4" : "M12 7v10m0 0l-4-4m4 4l4-4"}" stroke="#fca5a5" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const bad1 = el(`<div class="abs bad" style="left:330px">${arrow(false)}<div><small>Đêm đông khách</small>vẫn bán rẻ</div></div>`);
  const bad2 = el(`<div class="abs bad" style="left:1030px">${arrow(true)}<div><small>Đêm vắng khách</small>lại treo giá cao</div></div>`);
  const l2 = L("pain", 1);
  fadeIn(bad1, l2.start + 0.2, 0.45);
  fadeIn(bad2, l2.start + (l2.end - l2.start) * 0.5, 0.45);

  // =========================== 3. REVEAL ===========================
  const rv = S.reveal, t3 = rv.start;
  cues.push({ kind: "whoosh", t: t3 });
  for (const n of [fake, clock2, sheet, ph, note, bad1, bad2]) tw(n, { opacity: [1, 0] }, t3 - 0.3, 0.35);
  const glow = el(`<div class="abs glow"></div>`);
  tw(glow, { opacity: [0, 1, 0.3] }, t3 - 0.05, 1.1);
  fadeOut(glow, t3 + 3.2, 0.6);
  const logo = el(`<div class="abs" style="left:0;right:0;top:390px;display:flex;justify-content:center;opacity:0">
      <div class="logo"><div style="width:150px;height:150px">${ICON}</div><div class="word">OTARadar</div></div></div>`);
  tw(logo, { opacity: [0, 1], transform: ["scale(.7)", "scale(1)"] }, t3 + 0.15, 0.7, BACK);
  const tag = el(`<div class="abs reveal-tag">Theo dõi giá &amp; phòng trống của đối thủ trên Booking.com</div>`);
  fadeIn(tag, t3 + 0.75, 0.5);
  const chip = el(`<div class="abs reveal-chip"><span>Quét tự động 3 lần mỗi ngày · 06:00 · 14:00 · 22:00</span></div>`);
  fadeIn(chip, t3 + 1.35, 0.5);
  const tw3 = t3 + 3.4; // chuyển sang dashboard
  for (const n of [logo, tag, chip]) fadeOut(n, tw3 - 0.1, 0.4);
  tw(document.getElementById("bg-light"), { opacity: [0, 1] }, tw3, 0.7);
  show("today", tw3, 0.01);
  cam(tw3, 0.01, 720, 415, 1, "today");
  tw(win, { opacity: [0, 1], transform: ["translateY(700px) scale(.92)", "translateY(0) scale(1)"] }, tw3 + 0.05, 1.0, EASE);
  const demoTag = el(`<div class="abs demo-tag">Dữ liệu minh hoạ</div>`);
  fadeIn(demoTag, tw3 + 0.8, 0.4, 0);
  caption("OTARadar · Hôm nay", "Đối thủ trên Booking.com, <b>3 lần mỗi ngày</b>", tw3 + 0.7, S.grid.start + 0.05);
  cam(tw3 + 1.2, rv.start + rv.dur - tw3 - 1.2, 720, 400, 1.06, "today", "linear");

  // =========================== 4. GRID ===========================
  const gd = S.grid, t4 = gd.start, cal = BOX.calendar;
  caption("Lịch giá &amp; phòng", "Giá từng đêm · <b>90 ngày tới</b> · cạnh giá của bạn", t4 + 0.25, S.soldout.start + 0.2);
  navigate("calendar_rooms", t4);
  cam(t4, 0.01, 720, 415, 1, "calendar_rooms");
  const [bpx, bpy] = center(cal.btn_price), [bdx, bdy] = center(cal.btn_diff);
  const c1 = t4 + 1.65;
  cursor(1, [{ t: t4 + 0.5, x: 560, y: 560 }, { t: c1 - 0.1, x: bpx, y: bpy }], [{ t: c1, x: bpx, y: bpy }], c1 + 0.6);
  show("calendar_price", c1 + 0.1, 0.25);
  cam(c1 + 0.45, 1.2, 590, 470, 1.22, "calendar_price");
  const ownAt = L("grid", 0).end - 2.4;
  mark("spot", cal.own_row, ownAt, L("grid", 0).end + 0.15, 4);
  mark("hl", cal.own_row, ownAt, L("grid", 0).end + 0.15, 4);
  const c2 = L("grid", 1).start + 0.9;
  cursor(1.22, [{ t: c2 - 0.8, x: 620, y: 600 }, { t: c2 - 0.1, x: bdx, y: bdy }], [{ t: c2, x: bdx, y: bdy }], c2 + 0.6);
  show("calendar_diff", c2 + 0.1, 0.25);
  cam(c2 + 0.5, t4 + gd.dur - c2 - 0.5, 560, 480, 1.28, "calendar_diff", "linear");

  // =========================== 5. SOLD OUT ===========================
  const so = S.soldout, t5 = so.start;
  caption("Phòng còn của đối thủ", "Đối thủ hết phòng? <b>Bạn biết trước.</b>", t5 + 0.35, S.suggest.start + 0.1);
  cam(t5, 0.6, 720, 415, 1, "calendar_diff");
  show("calendar_rooms", t5 + 0.1, 0.3);
  const [sx, sy] = center(cal.sat_col);
  cam(t5 + 1.0, 1.2, sx, sy, 1.85, "calendar_rooms");
  mark("spot", cal.sat_col, t5 + 2.2, t5 + so.dur - 0.2, 6);
  mark("hl", cal.sat_col, t5 + 2.2, t5 + so.dur - 0.2, 6);
  const soldAt = L("soldout", 1).start + 1.1;
  for (const b of cal.sat_sold) mark("hl red", b, soldAt, t5 + so.dur - 0.2, 3, soldAt + 0.5);
  const toastAt = L("soldout", 1).end - 2.6;
  const toast = el(`<div class="abs toast"><div style="width:48px;height:48px;flex:none">${ICON}</div><div>
      <div class="t1">OTARadar · Cảnh báo lượt quét 06:00</div>
      <div class="t2">2 đối thủ hết phòng đêm T7 31/10</div>
      <div class="t3">Hoa Ban, Lam Sơn · 2 đối thủ khác còn ≤ 3 phòng</div></div></div>`);
  tw(toast, { opacity: [0, 1], transform: ["translateX(60px) scale(.96)", "translateX(0) scale(1)"] }, toastAt, 0.5, BACK);
  fadeOut(toast, t5 + so.dur - 0.25, 0.3);
  cues.push({ kind: "chime", t: toastAt + 0.05 });

  // =========================== 6. SUGGEST ===========================
  const sg = S.suggest, t6 = sg.start, td = BOX.today;
  caption("Việc cần làm hôm nay", "Gợi ý giá — <b>có lý do rõ ràng</b>", t6 + 0.3, L("suggest", 2).start - 0.1);
  navigate("today", t6);
  cam(t6, 0.01, 720, 415, 1, "today");
  const [hx, hy] = center(td.hero_card);
  cam(t6 + 0.7, 1.2, hx, hy, 1.42, "today");
  mark("spot", td.hero_card, t6 + 1.9, L("suggest", 1).start + 0.2, 6);
  mark("hl", td.hero_card, t6 + 1.9, L("suggest", 1).start + 0.2, 6);
  mark("hl amber", td.hero_reason, L("suggest", 0).end - 2.0, L("suggest", 1).start + 0.2, 6);
  const [ax, ay] = center(td.hero_apply), [cx2, cy2] = center(td.dialog_confirm);
  const k1 = L("suggest", 1).start + 0.85, k2 = k1 + 0.95;
  cursor(1.42, [{ t: k1 - 0.75, x: 470, y: 760 }, { t: k1 - 0.08, x: ax, y: ay }, { t: k2 - 0.08, x: cx2, y: cy2, hold: 0 }],
    [{ t: k1, x: ax, y: ay }, { t: k2, x: cx2, y: cy2 }], k2 + 0.5);
  show("today_dialog", k1 + 0.1, 0.15);
  show("today_applied", k2 + 0.1, 0.15);
  const [rx, ry] = center(td.applied_row);
  cam(k2 + 0.3, 0.8, rx, ry, 1.42, "today_applied");
  mark("hl green", td.applied_row, k2 + 0.9, t6 + sg.dur - 0.15, 6);
  caption("Bạn bấm — app ghi lại", "Quyết định <b>vẫn là của bạn.</b>", L("suggest", 2).start, S.market.start + 0.05);

  // =========================== 7. MARKET ===========================
  const mk = S.market, t7 = mk.start, mb = BOX.market;
  caption("Thị trường", "Cả khu vực <b>bán kính 1–5 km</b>", t7 + 0.35, L("market", 1).start + 3.2);
  navigate("market", t7);
  cam(t7, 0.01, 720, 330, 1.6, "market");
  cam(t7 + 0.15, 1.5, 720, 415, 1, "market");
  const [tx7, ty7] = center(mb.tension);
  cam(L("market", 1).start + 0.1, 1.0, tx7, ty7, 1.05, "market");
  mark("spot", mb.tension, L("market", 1).start + 1.1, L("market", 1).start + 3.3, 4);
  mark("hl amber", mb.sat_col, L("market", 1).start + 1.6, L("market", 1).start + 3.4, 4);
  cam(L("market", 1).start + 3.4, 1.0, 720, 920, 1.05, "market");
  caption("Lễ, Tết, sự kiện", "Biết trước <b>những ngày cầu tăng</b>", L("market", 1).start + 3.5, S.trust.start + 0.05);
  mark("hl amber", mb.conference, L("market", 1).start + 4.4, t7 + mk.dur - 0.1, 5);

  // =========================== 8. TRUST ===========================
  const tr = S.trust, t8 = tr.start;
  navigate("today", t8);
  const [fx, fy] = center(td.fresh);
  cam(t8, 0.01, fx, fy, 2.2, "today");
  cam(t8 + 0.01, 1.2, fx, fy + 30, 2.05, "today", "linear");
  mark("spot", td.fresh, t8 + 0.6, t8 + 3.0, 8);
  mark("hl", td.fresh, t8 + 0.6, t8 + 3.0, 8);
  const [stx, sty] = center(td.strip);
  cam(t8 + 3.0, 1.0, stx, sty, 1.3, "today");
  mark("spot", td.strip, t8 + 3.9, L("trust", 1).start + 0.3, 6);
  cam(L("trust", 1).start + 0.2, 1.2, 720, 415, 1, "today");
  const chips = el(`<div class="abs chips"></div>`);
  const chipAt = [t8 + 0.4, t8 + 2.0, L("trust", 1).start];
  ["Rõ nguồn", "Rõ giờ cập nhật", "Không đoán"].forEach((txt, i) => {
    const c = el(`<div class="chip"><i></i>${txt}</div>`, chips);
    tw(c, { opacity: [0, 1], transform: ["translateY(14px) scale(.95)", "translateY(0) scale(1)"] }, chipAt[i], 0.45, BACK);
  });

  // =========================== 9. CTA ===========================
  const ct = S.cta, t9 = ct.start;
  cues.push({ kind: "whoosh", t: t9 - 0.1 });
  tw(win, { opacity: [1, 0], transform: ["translateY(0) scale(1)", "translateY(80px) scale(.96)"] }, t9 - 0.35, 0.55, EASE_IO);
  for (const n of [chips, demoTag]) fadeOut(n, t9 - 0.35, 0.35);
  tw(document.getElementById("bg-light"), { opacity: [1, 0] }, t9 - 0.3, 0.6);
  const logo2 = el(`<div class="abs" style="left:0;right:0;top:200px;display:flex;justify-content:center">
      <div class="logo" style="gap:18px"><div style="width:88px;height:88px">${ICON}</div><div class="word" style="font-size:60px">OTARadar</div></div></div>`);
  fadeIn(logo2, t9 + 0.1, 0.5);
  const h = el(`<div class="abs cta-h">Đặt lịch demo</div>`);
  tw(h, { opacity: [0, 1], transform: ["translateY(30px) scale(.96)", "translateY(0) scale(1)"] }, t9 + 0.3, 0.6, BACK);
  const sub = el(`<div class="abs cta-s">Gửi link <b>Booking.com</b> của khách sạn bạn —<br>xem bảng giá đối thủ <b>của chính bạn</b>.</div>`);
  fadeIn(sub, L("cta", 1).start + 0.1, 0.5);
  const btn = el(`<div class="abs cta-btn"><span>Đặt lịch demo →</span></div>`);
  fadeIn(btn, L("cta", 1).start + 1.0, 0.5);
  tw(btn.firstElementChild, { transform: ["scale(1)", "scale(1.05)", "scale(1)"] }, L("cta", 1).start + 3.0, 1.0, EASE_IO);
  tw(btn.firstElementChild, { transform: ["scale(1)", "scale(1.05)", "scale(1)"] }, L("cta", 1).start + 5.0, 1.0, EASE_IO);
  if (TL.contact) fadeIn(el(`<div class="abs cta-contact">${TL.contact}</div>`), L("cta", 1).start + 1.6, 0.5);
  fadeIn(el(`<div class="abs disclaimer">Dữ liệu trong video là dữ liệu minh hoạ · Giọng đọc tạo bằng AI · OTARadar không liên kết với Booking.com.</div>`), t9 + 0.8, 0.5, 0);
  tw(document.getElementById("fade"), { opacity: [0, 1] }, TL.total - 0.45, 0.45, "linear");

  window.__cues = cues.sort((a, b) => a.t - b.t);
  window.__duration = TL.total;
  window.seek = (t) => {
    for (const a of document.getAnimations()) {
      a.pause();
      a.currentTime = t * 1000;
    }
  };
  window.seek(0);
  window.__ready = true;
}

document.fonts.ready.then(main);
