import { buildDemo, HOTELS } from "./demo-data";

const W = 720;
const H = 280;
const PAD = { l: 8, r: 60, t: 30, b: 44 };

/** Công suất PMS của bạn (đường) đặt cạnh tỷ lệ đối thủ hết phòng (cột), 30 đêm tới. */
export function PmsChart({ startISO }: { startISO: string }) {
  const demo = buildDemo(startISO);
  const competitors = HOTELS.filter((h) => !h.self);
  const n = demo.nights.length;
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const step = iw / n;
  const y = (v: number) => PAD.t + ih * (1 - v);
  const share = demo.nights.map(
    (night) => competitors.filter((h) => demo.obs[h.id][night.index][5].status === "sold_out").length / competitors.length,
  );
  const line = demo.occupancy.map((v, i) => `${i ? "L" : "M"}${(PAD.l + step * (i + 0.5)).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const peak = demo.peak;
  const px = PAD.l + step * (peak + 0.5);

  return (
    <figure className="lp-pms-chart">
      <figcaption className="lp-pms-head">
        <span className="lp-pms-title">Công suất của bạn và thị trường</span>
        <span className="lp-pms-legend">
          <span>
            <i className="lp-key-bar" aria-hidden="true" /> Đối thủ hết phòng
          </span>
          <span>
            <i className="lp-key-line" aria-hidden="true" /> Công suất từ PMS
          </span>
        </span>
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Minh hoạ: đêm ${demo.nights[peak].label} đối thủ hết phòng ${Math.round(share[peak] * 100)}%, công suất của bạn ${Math.round(demo.occupancy[peak] * 100)}%.`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className={t === 0 ? "lp-axis-base" : "lp-axis-grid"} />
            {t > 0 && (
              <text x={W - 2} y={y(t) + 4} textAnchor="end" className="lp-axis">
                {t * 100}%
              </text>
            )}
          </g>
        ))}
        {share.map((v, i) =>
          v > 0 ? (
            <rect
              key={i}
              x={PAD.l + step * i + step * 0.18}
              y={y(v)}
              width={step * 0.64}
              height={ih * v}
              rx={3}
              className={i === peak ? "lp-bar lp-bar-peak" : "lp-bar"}
            />
          ) : null,
        )}
        <path d={line} fill="none" className="lp-occ-line" />
        {demo.occupancy.map((v, i) => (
          <circle key={i} cx={PAD.l + step * (i + 0.5)} cy={y(v)} r={i === peak ? 5 : 2.4} className="lp-occ-dot" />
        ))}
        {demo.nights.map((night, i) =>
          i % 5 === 0 || i === peak ? (
            <text
              key={night.iso}
              x={PAD.l + step * (i + 0.5)}
              y={H - 14}
              textAnchor="middle"
              className="lp-axis"
              data-peak={i === peak}
            >
              {night.day}
            </text>
          ) : null,
        )}
        <line x1={px} x2={px} y1={PAD.t - 12} y2={y(share[peak])} className="lp-axis-peak" />
      </svg>
      <p className="lp-note">Số liệu minh hoạ</p>
    </figure>
  );
}
