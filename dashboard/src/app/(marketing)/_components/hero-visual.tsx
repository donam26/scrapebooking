"use client";

import { useEffect, useMemo, useState } from "react";
import { buildDemo, HOTELS, SCAN_TIMES, type HotelObs } from "./demo-data";
import { IconBell, IconChart, IconChevron, IconSearch, IconSpark } from "./marks";
import { PhotoFrame } from "./photo";
import { PHOTOS } from "./photos";

const TODAY = 3;

function cellKind(o: HotelObs): string {
  if (o.status === "sold_out") return "sold_out";
  if (o.hasCapped) return "capped";
  if (o.hasHidden) return "hidden";
  return "exact";
}

/** Ảnh ghép đầu trang: ảnh thật + các mảnh giao diện của sản phẩm nổi phía trên. */
export function HeroVisual({ startISO }: { startISO: string }) {
  const demo = useMemo(() => buildDemo(startISO), [startISO]);
  const peak = demo.nights[demo.peak];
  const eve = demo.nights[demo.peak - 1];
  const brief = `Cuối tuần ${eve.day}–${peak.day} đang kín nhanh: 3/4 đối thủ đã hết phòng đêm ${peak.label}. Đề xuất: giữ giá phòng còn lại.`;

  const [scan, setScan] = useState(2);
  const [typed, setTyped] = useState(brief.length);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timers: number[] = [];
    // Gõ lại bản tin một lần, rồi cho lượt quét chạy vòng 06:00 → 14:00 → 22:00.
    timers.push(window.setTimeout(() => setTyped(0), 0));
    const typing = window.setInterval(() => {
      setTyped((n) => {
        if (n >= brief.length) {
          window.clearInterval(typing);
          return n;
        }
        return n + 1;
      });
    }, 26);
    timers.push(window.setTimeout(() => setScan(0), 200));
    const cycle = window.setInterval(() => setScan((s) => (s + 1) % 3), 2600);
    return () => {
      timers.forEach((t) => window.clearTimeout(t));
      window.clearInterval(typing);
      window.clearInterval(cycle);
    };
  }, [brief.length]);

  const s = TODAY + scan;
  const competitors = HOTELS.filter((h) => !h.self);
  const soldOut = competitors.filter((h) => demo.obs[h.id][demo.peak][s].status === "sold_out").length;
  const nights = demo.nights.slice(demo.peak - 4, demo.peak + 3);
  const catvang = demo.obs.catvang[demo.peak][s];

  return (
    <div className="lp-hv">
      <div className="lp-hv-card">
        <PhotoFrame
          photo={PHOTOS.coast}
          priority
          sizes="(min-width: 1000px) 640px, 100vw"
          className="lp-hv-photo"
          position="62% 50%"
        />
        <div className="lp-hv-shade" aria-hidden="true" />

        <div className="lp-hv-nav" aria-hidden="true">
          <IconSpark />
          <span>Tổng quan</span>
          <span>Sự kiện</span>
          <span>Bản tin</span>
          <i />
          <IconSearch />
          <IconBell />
        </div>

        <span className="lp-hv-pill" aria-hidden="true">
          <b>
            <IconBell />
          </b>
          {catvang.status === "sold_out" ? "Cát Vàng vừa hết phòng" : `Cát Vàng · còn ${catvang.known} phòng`}
        </span>

        <div className="lp-hv-board" role="img" aria-label={`Minh hoạ: đêm ${peak.label}, lượt ${SCAN_TIMES[scan]}, ${soldOut} trên 4 đối thủ hết phòng.`}>
          <p className="lp-hv-board-when">
            Đêm {peak.label} · lượt {SCAN_TIMES[scan]}
          </p>
          <p className="lp-hv-board-big">
            {soldOut}/4 <span>đối thủ hết phòng</span>
          </p>
          <div className="lp-hv-grid" aria-hidden="true">
            {HOTELS.map((h) => (
              <div key={h.id} className="lp-hv-row">
                <span>{h.self ? "Bạn" : h.name}</span>
                {nights.map((n) => (
                  <i
                    key={n.iso}
                    className={`lp-hv-cell lp-cell-${cellKind(demo.obs[h.id][n.index][s])}`}
                    data-peak={n.index === demo.peak}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="lp-hv-prompt">
        <p>
          <span className="lp-hv-prompt-label">Bản tin 07:30</span>
          <span className="lp-hv-typed" aria-hidden="true">
            {brief.slice(0, typed)}
            <span className="lp-hv-caret" aria-hidden="true" />
          </span>
          <span className="lp-sr">{brief}</span>
        </p>
        <div className="lp-hv-tools" aria-hidden="true">
          <IconChart />
          <IconBell />
          <IconSpark />
          <span className="lp-hv-go">
            <IconChevron />
          </span>
        </div>
      </div>

      <div className="lp-hv-scans" aria-hidden="true">
        {SCAN_TIMES.map((t, i) => (
          <span key={t} data-active={scan === i}>
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}
