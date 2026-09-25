import { buildDemo, formatThousands, HOTELS, type Demo, type DemoEvent } from "./demo-data";

const SCAN_HOURS = ["06:00", "14:00", "22:00"];

/** Mốc tuyệt đối của một lượt quét, ví dụ "14:00 25/9". Lượt 0..2 là ngày trước ngày bắt đầu. */
function scanStamp(startISO: string, scan: number): string {
  const [y, m, d] = startISO.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + (scan < 3 ? -1 : 0)));
  return `${SCAN_HOURS[scan % 3]} ${date.getUTCDate()}/${date.getUTCMonth() + 1}`;
}

function dayAfter(startISO: string): string {
  const [y, m, d] = startISO.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + 1));
  const wd = ["Chủ nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"][date.getUTCDay()];
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
  const demo = buildDemo(startISO);
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
    .map((e) => ({ who: name(e.hotelId), what: "Hết phòng", when: scanStamp(startISO, e.scan) }));

  const drop = find(demo, "catvang", demo.peak - 1, "price_down");
  const dropPct = drop ? Math.round(((drop.from! - drop.to!) / drop.from!) * 100) : 0;

  return (
    <article className="lp-brief" aria-label="Bản tin mẫu">
      <header className="lp-brief-head">
        <p className="lp-brief-title">Bản tin sáng</p>
        <p className="lp-brief-meta">
          {dayAfter(startISO)} · 07:30 · dữ liệu đến lượt {scanStamp(startISO, 5)}
        </p>
      </header>

      <p className="lp-brief-summary">
        Cuối tuần {eve.label}–{peak.label} đang kín nhanh: {soldOut.length}/{competitors.length} đối thủ đã hết phòng đêm{" "}
        {peak.label}. Khách sạn của bạn vẫn còn ít nhất {selfPeak.known} phòng cho đêm này, công suất PMS mới {occupancy}%.
      </p>

      <ol className="lp-highlights">
        <li>
          <div className="lp-hl-top">
            <h3>Đêm {peak.label} gần kín thị trường</h3>
            <span className="lp-conf" data-level="high">
              Tin cậy cao
            </span>
          </div>
          <p className="lp-hl-rec">
            Đề xuất: giữ giá phòng còn lại, cân nhắc tăng giá hạng hướng biển trước lượt quét 14:00.
          </p>
          <ul className="lp-evidence" aria-label="Bằng chứng">
            {soldEvidence.map((e) => (
              <li key={e.who}>
                <b>{e.who}</b> {e.what} <span>{e.when}</span>
              </li>
            ))}
            <li>
              <b>Compset</b> {soldOut.length}/{competitors.length} đối thủ hết phòng
            </li>
          </ul>
        </li>
        {drop && (
          <li>
            <div className="lp-hl-top">
              <h3>
                Cát Vàng giảm giá {dropPct}% cho đêm {eve.label}
              </h3>
              <span className="lp-conf" data-level="medium">
                Tin cậy trung bình
              </span>
            </div>
            <p className="lp-hl-rec">Đề xuất: chưa cần phản ứng, xem lượt 06:00 các đối thủ khác có giảm theo không.</p>
            <ul className="lp-evidence" aria-label="Bằng chứng">
              <li>
                <b>Cát Vàng</b> Giảm giá {formatThousands(drop.from)} → {formatThousands(drop.to)} nghìn{" "}
                <span>{scanStamp(startISO, drop.scan)}</span>
              </li>
            </ul>
          </li>
        )}
      </ol>

      <div className="lp-signals">
        <p>Tín hiệu cầu</p>
        <ul>
          <li data-level="high">
            <b>{peak.label}</b> Cao
          </li>
          <li data-level="high">
            <b>{eve.label}</b> Cao
          </li>
          <li data-level="medium">
            <b>{after.label}</b> Trung bình
          </li>
        </ul>
      </div>

      <footer className="lp-brief-foot">
        <p>
          <b>1 nhận định bị loại</b> vì không trích được sự kiện hay chỉ số nào làm bằng chứng.
        </p>
        <p>Chất lượng dữ liệu: Sao Biển có loại phòng chỉ biết mức “ít nhất”, tốc độ bán chỉ tính trên số chính xác.</p>
      </footer>
    </article>
  );
}
