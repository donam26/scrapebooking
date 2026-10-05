import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { useFmt } from "@/lib/format";
import { buildDemo, formatThousands, HOTELS, type Demo, type DemoEvent } from "./demo-data";

const SCAN_HOURS = ["06:00", "14:00", "22:00"];

/** Mốc tuyệt đối của một lượt quét, ví dụ "14:00 25/9". Lượt 0..2 là ngày trước ngày bắt đầu. */
function scanStamp(startISO: string, scan: number): string {
  const [y, m, d] = startISO.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + (scan < 3 ? -1 : 0)));
  return `${SCAN_HOURS[scan % 3]} ${date.getUTCDate()}/${date.getUTCMonth() + 1}`;
}

function dayAfter(startISO: string, t: ReturnType<typeof useTranslations<"landing.brief">>): string {
  const [y, m, d] = startISO.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + 1));
  const wd = t("weekday", { day: String(date.getUTCDay()) });
  return `${wd} ${date.getUTCDate()}/${date.getUTCMonth() + 1}`;
}

function name(id: string) {
  return HOTELS.find((h) => h.id === id)?.name ?? id;
}

function find(demo: Demo, hotelId: string, night: number, kind: DemoEvent["kind"]) {
  return demo.events.find((e) => e.hotelId === hotelId && e.night === night && e.kind === kind);
}

type Evidence = { who: string; what: string; when: string };

/** Bản tin mẫu dựng từ chính dữ liệu minh hoạ, nên mọi bằng chứng đều khớp với bảng phía trên. */
export function BriefSheet({ startISO }: { startISO: string }) {
  const t = useTranslations("landing.brief");
  const td = useTranslations("landing.demo");
  const fmt = useFmt();
  const demo = buildDemo(startISO, fmt.fmtWeekday);
  const peak = demo.nights[demo.peak];
  const eve = demo.nights[demo.peak - 1];
  const after = demo.nights[demo.peak + 1];
  const competitors = HOTELS.filter((h) => !h.self);
  const soldOut = competitors.filter((h) => demo.obs[h.id][demo.peak][5].status === "sold_out");
  const selfPeak = demo.obs.self[demo.peak][5];
  const occupancy = Math.round(demo.occupancy[demo.peak] * 100);

  const soldEvidence: Evidence[] = soldOut
    .map((h) => find(demo, h.id, demo.peak, "sold_out"))
    .filter((e): e is DemoEvent => Boolean(e))
    .map((e) => ({ who: name(e.hotelId), what: td("events.sold_out"), when: scanStamp(startISO, e.scan) }));

  const drop = find(demo, "catvang", demo.peak - 1, "price_down");
  const dropPct = drop ? Math.round(((drop.from! - drop.to!) / drop.from!) * 100) : 0;
  const b = (c: ReactNode) => <b>{c}</b>;

  return (
    <article className="lp-brief" aria-label={t("label")}>
      <header className="lp-brief-head">
        <p className="lp-brief-title">{t("title")}</p>
        <p className="lp-brief-meta">{t("meta", { day: dayAfter(startISO, t), scan: scanStamp(startISO, 5) })}</p>
      </header>

      <p className="lp-brief-summary">
        {t("summary", {
          eve: eve.label,
          peak: peak.label,
          sold: soldOut.length,
          total: competitors.length,
          known: selfPeak.known,
          occupancy,
        })}
      </p>

      <ol className="lp-highlights">
        <li>
          <div className="lp-hl-top">
            <h3>{t("peakTitle", { night: peak.label })}</h3>
            <span className="lp-conf" data-level="high">
              {t("confHigh")}
            </span>
          </div>
          <p className="lp-hl-rec">{t("peakRec")}</p>
          <ul className="lp-evidence" aria-label={t("evidence")}>
            {soldEvidence.map((e) => (
              <li key={e.who}>
                <b>{e.who}</b> {e.what} <span>{e.when}</span>
              </li>
            ))}
            <li>{t.rich("compset", { sold: soldOut.length, total: competitors.length, b })}</li>
          </ul>
        </li>
        {drop && (
          <li>
            <div className="lp-hl-top">
              <h3>{t("dropTitle", { hotel: name(drop.hotelId), pct: dropPct, night: eve.label })}</h3>
              <span className="lp-conf" data-level="medium">
                {t("confMedium")}
              </span>
            </div>
            <p className="lp-hl-rec">{t("dropRec")}</p>
            <ul className="lp-evidence" aria-label={t("evidence")}>
              <li>
                {t.rich("dropEvidence", {
                  hotel: name(drop.hotelId),
                  from: formatThousands(drop.from, fmt),
                  to: formatThousands(drop.to, fmt),
                  when: scanStamp(startISO, drop.scan),
                  b,
                  span: (c) => <span>{c}</span>,
                })}
              </li>
            </ul>
          </li>
        )}
      </ol>

      <div className="lp-signals">
        <p>{t("signals")}</p>
        <ul>
          <li data-level="high">
            <b>{peak.label}</b> {t("high")}
          </li>
          <li data-level="high">
            <b>{eve.label}</b> {t("high")}
          </li>
          <li data-level="medium">
            <b>{after.label}</b> {t("medium")}
          </li>
        </ul>
      </div>

      <footer className="lp-brief-foot">
        <p>{t.rich("dropped", { b })}</p>
        <p>{t("quality", { hotel: name("saobien") })}</p>
      </footer>
    </article>
  );
}
