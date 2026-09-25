"use client";

import { useMemo, useState } from "react";
import { ConfidenceSwatch } from "./marks";
import {
  buildDemo,
  CONFIDENCE_LABEL,
  EVENT_LABEL,
  formatThousands,
  formatVnd,
  HOTELS,
  plaqueText,
  SCAN_LABELS,
  type HotelObs,
} from "./demo-data";

const LATEST = 5;

function cellKind(o: HotelObs): "sold_out" | "capped" | "hidden" | "exact" {
  if (o.status === "sold_out") return "sold_out";
  if (o.hasCapped) return "capped";
  if (o.hasHidden) return "hidden";
  return "exact";
}

function roomsText(o: HotelObs): string {
  if (o.status === "sold_out") return "Hết phòng";
  const t = plaqueText(o);
  if (t === "CÒN") return "Còn phòng";
  return t.startsWith("≥") ? `Còn ít nhất ${t.slice(1)} phòng` : `Còn ${t} phòng`;
}

export function MarketBoard({ startISO }: { startISO: string }) {
  const demo = useMemo(() => buildDemo(startISO), [startISO]);
  const [sel, setSel] = useState<{ hotel: string; night: number }>({ hotel: "catvang", night: demo.peak });

  const competitors = HOTELS.filter((h) => !h.self);
  const hotel = HOTELS.find((h) => h.id === sel.hotel)!;
  const nightInfo = demo.nights[sel.night];
  const obs = demo.obs[sel.hotel][sel.night][LATEST];
  const history = demo.obs[sel.hotel][sel.night];
  const events = demo.events
    .filter((e) => e.hotelId === sel.hotel && e.night === sel.night)
    .sort((a, b) => b.scan - a.scan);

  return (
    <div className="lp-board">
      <div className="lp-board-sheet">
        <div className="lp-board-head">
          <span className="lp-board-title">Tổng quan · 30 đêm tới</span>
          <span className="lp-board-meta">
            <i aria-hidden="true" /> Lượt quét gần nhất: hôm nay 22:00
          </span>
        </div>
        <div className="lp-board-scroll" tabIndex={0} aria-label="Bảng phòng còn theo khách sạn và đêm, cuộn ngang">
          <table className="lp-grid">
            <caption className="lp-sr">Số phòng còn của khách sạn bạn và bốn đối thủ trong 30 đêm tới (minh hoạ)</caption>
            <thead>
              <tr>
                <th scope="col" className="lp-grid-corner">
                  Khách sạn
                </th>
                {demo.nights.map((n) => (
                  <th key={n.iso} scope="col" data-weekend={n.weekend} data-peak={n.index === demo.peak}>
                    <span>{n.weekday}</span>
                    <span>{n.day}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {HOTELS.map((h) => (
                <tr key={h.id} data-self={h.self}>
                  <th scope="row">
                    {h.self && <i className="lp-self-dot" aria-hidden="true" />}
                    {h.self ? "Của bạn" : h.name}
                  </th>
                  {demo.nights.map((n) => {
                    const o = demo.obs[h.id][n.index][LATEST];
                    const kind = cellKind(o);
                    const active = sel.hotel === h.id && sel.night === n.index;
                    return (
                      <td key={n.iso}>
                        <button
                          type="button"
                          className={`lp-cell lp-cell-${kind}`}
                          aria-pressed={active}
                          aria-label={`${h.name}, đêm ${n.label}: ${roomsText(o)}`}
                          onClick={() => setSel({ hotel: h.id, night: n.index })}
                        >
                          {kind === "sold_out" ? "HẾT" : o.known > 0 ? o.known : ""}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="lp-grid-band">
                <th scope="row">Đối thủ hết phòng</th>
                {demo.nights.map((n) => {
                  const sold = competitors.filter((h) => demo.obs[h.id][n.index][LATEST].status === "sold_out").length;
                  return (
                    <td key={n.iso}>
                      <span className="lp-band-meter" style={{ ["--v" as string]: sold / competitors.length }} aria-label={`${sold} trên ${competitors.length}`}>
                        <i />
                      </span>
                    </td>
                  );
                })}
              </tr>
              <tr className="lp-grid-band">
                <th scope="row">Giá thấp nhất (nghìn ₫)</th>
                {demo.nights.map((n) => {
                  const prices = competitors
                    .map((h) => demo.obs[h.id][n.index][LATEST].price)
                    .filter((p): p is number => p != null);
                  return (
                    <td key={n.iso} className="lp-band-price">
                      {prices.length ? formatThousands(Math.min(...prices)) : "—"}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
        <ul className="lp-board-legend">
          <li>
            <i className="lp-cell-key lp-cell-exact" aria-hidden="true" /> Chính xác: trang hiện “chỉ còn X phòng”
          </li>
          <li>
            <i className="lp-cell-key lp-cell-capped" aria-hidden="true" /> Ít nhất: số trong ô là mức sàn
          </li>
          <li>
            <i className="lp-cell-key lp-cell-hidden" aria-hidden="true" /> Ẩn: còn phòng, không lộ số
          </li>
          <li>
            <i className="lp-cell-key lp-cell-sold_out" aria-hidden="true" /> Hết phòng
          </li>
        </ul>
      </div>

      <aside className="lp-detail" aria-live="polite">
        <div className="lp-detail-main">
          <h3 className="lp-detail-hotel">
            {hotel.name} <span>· đêm {nightInfo.label}</span>
          </h3>
          <p className="lp-detail-status" data-sold={obs.status === "sold_out"}>
            {roomsText(obs)}
            {obs.price != null && <> · từ {formatVnd(obs.price)}</>}
          </p>

          <table className="lp-types">
            <caption className="lp-sr">Từng loại phòng ở lượt quét gần nhất</caption>
            <thead>
              <tr>
                <th scope="col">Loại phòng</th>
                <th scope="col">Còn</th>
                <th scope="col">Giá / đêm</th>
              </tr>
            </thead>
            <tbody>
              {obs.types.map((t) => (
                <tr key={t.name} data-sold={t.confidence === "sold_out"}>
                  <td>
                    <span className="lp-type-name">{t.name}</span>
                    {t.left > 0 && <span className="lp-type-plans">{t.plans.join(" · ")}</span>}
                  </td>
                  <td>
                    <span className="lp-type-stock">
                      <ConfidenceSwatch kind={t.confidence} />
                      {t.confidence === "exact" && t.shown}
                      {t.confidence === "capped" && `≥${t.shown}`}
                      {t.confidence === "hidden" && "Ẩn"}
                      {t.confidence === "sold_out" && "Hết"}
                    </span>
                    {t.confidence !== "sold_out" && (
                      <span className="lp-type-conf">{CONFIDENCE_LABEL[t.confidence]}</span>
                    )}
                  </td>
                  <td className="lp-num">{formatVnd(t.price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="lp-history-wrap">
          <p className="lp-detail-sub">Sáu lượt quan sát gần nhất</p>
          <div className="lp-history" aria-label="Các lượt quan sát trước, lượt cũ in nhạt hơn">
            {history.map((o, i) => (
              <div key={i} className="lp-print" style={{ ["--gen" as string]: LATEST - i }}>
                <span className="lp-print-val">{o.status === "sold_out" ? "HẾT" : plaqueText(o)}</span>
                <span className="lp-print-when">
                  {i < 3 ? "Qua" : "Nay"}
                  <br />
                  {SCAN_LABELS[i].slice(-5)}
                </span>
              </div>
            ))}
          </div>
          <p className="lp-history-note">Lượt càng cũ in càng nhạt. Tốc độ bán chỉ tính giữa hai số chính xác.</p>
        </div>

        <div className="lp-detail-events">
          <p className="lp-detail-sub">Sự kiện của đêm này</p>
          {events.length === 0 ? (
            <span className="lp-muted">Không có thay đổi đáng kể giữa các lượt quét.</span>
          ) : (
            <ul>
              {events.slice(0, 4).map((e, i) => (
                <li key={i}>
                  <span className="lp-event-kind" data-kind={e.kind}>
                    {EVENT_LABEL[e.kind]}
                  </span>
                  <span>
                    {e.kind === "price_down" || e.kind === "price_up"
                      ? `${formatThousands(e.from)} → ${formatThousands(e.to)} nghìn`
                      : e.kind === "sold_out"
                        ? `${e.from} → 0 phòng`
                        : `${e.from} → ${e.to} phòng`}
                  </span>
                  <span className="lp-muted">{SCAN_LABELS[e.scan]}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
