"use client";

import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { useFmt } from "@/lib/format";
import { ConfidenceSwatch } from "./marks";
import { buildDemo, formatThousands, HOTELS, SCAN_TIMES, type DemoHotel, type HotelObs } from "./demo-data";

const LATEST = 5;

function cellKind(o: HotelObs): "sold_out" | "capped" | "hidden" | "exact" {
  if (o.status === "sold_out") return "sold_out";
  if (o.hasCapped) return "capped";
  if (o.hasHidden) return "hidden";
  return "exact";
}

type BoardT = ReturnType<typeof useTranslations<"landing.board">>;

/** Số hiển thị mức khách sạn: đúng X, ít nhất X, hoặc HẾT. */
function plaqueText(o: HotelObs, soldOut: string, available: string): string {
  if (o.status === "sold_out") return soldOut;
  if (o.hasCapped || o.hasHidden) return o.known > 0 ? `≥${o.known}` : available;
  return String(o.known);
}

function roomsText(o: HotelObs, t: BoardT): string {
  if (o.status === "sold_out") return t("soldOut");
  if (o.hasCapped || o.hasHidden) return o.known > 0 ? t("roomsAtLeast", { count: o.known }) : t("roomsAvailable");
  return t("roomsLeft", { count: o.known });
}

export function MarketBoard({ startISO }: { startISO: string }) {
  const t = useTranslations("landing.board");
  const td = useTranslations("landing.demo");
  const fmt = useFmt();
  const demo = useMemo(() => buildDemo(startISO, fmt.fmtWeekday), [startISO, fmt]);
  const [sel, setSel] = useState<{ hotel: string; night: number }>({ hotel: "catvang", night: demo.peak });

  const competitors = HOTELS.filter((h) => !h.self);
  const hotel = HOTELS.find((h) => h.id === sel.hotel)!;
  const nightInfo = demo.nights[sel.night];
  const obs = demo.obs[sel.hotel][sel.night][LATEST];
  const history = demo.obs[sel.hotel][sel.night];
  const events = demo.events
    .filter((e) => e.hotelId === sel.hotel && e.night === sel.night)
    .sort((a, b) => b.scan - a.scan);
  const nameOf = (h: DemoHotel) => (h.self ? td("selfHotel") : h.name);
  const scanLabel = (scan: number) => t(scan < 3 ? "scanYesterday" : "scanToday", { time: SCAN_TIMES[scan % 3] });

  return (
    <div className="lp-board">
      <div className="lp-board-sheet">
        <div className="lp-board-head">
          <span className="lp-board-title">{t("title")}</span>
          <span className="lp-board-meta">
            <i aria-hidden="true" /> {t("latestScan")}
          </span>
        </div>
        <div className="lp-board-scroll" tabIndex={0} aria-label={t("scrollLabel")}>
          <table className="lp-grid">
            <caption className="lp-sr">{t("caption")}</caption>
            <thead>
              <tr>
                <th scope="col" className="lp-grid-corner">
                  {t("hotelCol")}
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
                    {h.self ? t("yours") : h.name}
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
                          aria-label={t("cellLabel", { hotel: nameOf(h), night: n.label, rooms: roomsText(o, t) })}
                          onClick={() => setSel({ hotel: h.id, night: n.index })}
                        >
                          {kind === "sold_out" ? td("soldOutShort") : o.known > 0 ? o.known : ""}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr className="lp-grid-band">
                <th scope="row">{t("bandSoldOut")}</th>
                {demo.nights.map((n) => {
                  const sold = competitors.filter((h) => demo.obs[h.id][n.index][LATEST].status === "sold_out").length;
                  return (
                    <td key={n.iso}>
                      <span className="lp-band-meter" style={{ ["--v" as string]: sold / competitors.length }} aria-label={t("bandMeter", { sold, total: competitors.length })}>
                        <i />
                      </span>
                    </td>
                  );
                })}
              </tr>
              <tr className="lp-grid-band">
                <th scope="row">{t("bandPrice")}</th>
                {demo.nights.map((n) => {
                  const prices = competitors
                    .map((h) => demo.obs[h.id][n.index][LATEST].price)
                    .filter((p): p is number => p != null);
                  return (
                    <td key={n.iso} className="lp-band-price">
                      {prices.length ? formatThousands(Math.min(...prices), fmt) : "—"}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
        <ul className="lp-board-legend">
          <li>
            <i className="lp-cell-key lp-cell-exact" aria-hidden="true" /> {t("legend.exact")}
          </li>
          <li>
            <i className="lp-cell-key lp-cell-capped" aria-hidden="true" /> {t("legend.capped")}
          </li>
          <li>
            <i className="lp-cell-key lp-cell-hidden" aria-hidden="true" /> {t("legend.hidden")}
          </li>
          <li>
            <i className="lp-cell-key lp-cell-sold_out" aria-hidden="true" /> {t("legend.soldOut")}
          </li>
        </ul>
      </div>

      <aside className="lp-detail" aria-live="polite">
        <div className="lp-detail-main">
          <h3 className="lp-detail-hotel">
            {nameOf(hotel)} <span>{t("detailNight", { night: nightInfo.label })}</span>
          </h3>
          <p className="lp-detail-status" data-sold={obs.status === "sold_out"}>
            {roomsText(obs, t)}
            {obs.price != null && <> · {t("fromPrice", { price: fmt.fmtMoney(obs.price, "VND") })}</>}
          </p>

          <table className="lp-types">
            <caption className="lp-sr">{t("typesCaption")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("colType")}</th>
                <th scope="col">{t("colLeft")}</th>
                <th scope="col">{t("colPrice")}</th>
              </tr>
            </thead>
            <tbody>
              {obs.types.map((rt) => (
                <tr key={rt.name} data-sold={rt.confidence === "sold_out"}>
                  <td>
                    <span className="lp-type-name">{td(`roomTypes.${rt.name}`)}</span>
                    {rt.left > 0 && <span className="lp-type-plans">{rt.plans.map((p) => td(`plans.${p}`)).join(" · ")}</span>}
                  </td>
                  <td>
                    <span className="lp-type-stock">
                      <ConfidenceSwatch kind={rt.confidence} />
                      {rt.confidence === "exact" && rt.shown}
                      {rt.confidence === "capped" && `≥${rt.shown}`}
                      {rt.confidence === "hidden" && td("confidence.hidden")}
                      {rt.confidence === "sold_out" && td("confidence.sold_out")}
                    </span>
                    {rt.confidence !== "sold_out" && (
                      <span className="lp-type-conf">{td(`confidence.${rt.confidence}`)}</span>
                    )}
                  </td>
                  <td className="lp-num">{fmt.fmtMoney(rt.price, "VND")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="lp-history-wrap">
          <p className="lp-detail-sub">{t("historyTitle")}</p>
          <div className="lp-history" aria-label={t("historyLabel")}>
            {history.map((o, i) => (
              <div key={i} className="lp-print" style={{ ["--gen" as string]: LATEST - i }}>
                <span className="lp-print-val">{plaqueText(o, td("soldOutShort"), td("availableShort"))}</span>
                <span className="lp-print-when">
                  {i < 3 ? t("yesterdayShort") : t("todayShort")}
                  <br />
                  {SCAN_TIMES[i % 3]}
                </span>
              </div>
            ))}
          </div>
          <p className="lp-history-note">{t("historyNote")}</p>
        </div>

        <div className="lp-detail-events">
          <p className="lp-detail-sub">{t("eventsTitle")}</p>
          {events.length === 0 ? (
            <span className="lp-muted">{t("noEvents")}</span>
          ) : (
            <ul>
              {events.slice(0, 4).map((e, i) => (
                <li key={i}>
                  <span className="lp-event-kind" data-kind={e.kind}>
                    {td(`events.${e.kind}`)}
                  </span>
                  <span>
                    {e.kind === "price_down" || e.kind === "price_up"
                      ? t("priceChange", { from: formatThousands(e.from, fmt), to: formatThousands(e.to, fmt) })
                      : t("roomsChange", { from: e.from ?? 0, to: e.kind === "sold_out" ? 0 : (e.to ?? 0) })}
                  </span>
                  <span className="lp-muted">{scanLabel(e.scan)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}
