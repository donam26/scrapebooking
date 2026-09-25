/**
 * Dữ liệu minh hoạ cho trang giới thiệu. Hoàn toàn tổng hợp, sinh tất định từ ngày bắt đầu
 * nên server và client cho cùng kết quả. Mô phỏng đúng ngữ nghĩa của hệ thống thật:
 * số phòng còn theo loại phòng kèm mức tin cậy (exact / capped / hidden / sold_out),
 * 6 lượt quét (hôm qua và hôm nay lúc 06:00, 14:00, 22:00) và sự kiện giữa hai lượt.
 */

export type Confidence = "exact" | "capped" | "hidden" | "sold_out";

export const SCAN_TIMES = ["06:00", "14:00", "22:00"] as const;
export type ScanTime = (typeof SCAN_TIMES)[number];

/** Trần của ô chọn số phòng trên trang: nhiều hơn thì chỉ biết "ít nhất". */
const DROPDOWN_CAP = 10;
/** Booking.com chỉ hiện "Chỉ còn X phòng" khi tồn kho thấp. */
const BADGE_MAX = 5;

export interface DemoHotel {
  id: string;
  name: string;
  self: boolean;
  /** Số ô cửa sổ vẽ trên tranh. */
  windows: number;
  /** Số phòng đang mở bán trên Booking.com. */
  rooms: number;
  /** Khách sạn nhỏ, giá tốt kín sớm hơn. */
  pressure: number;
  basePrice: number;
  roomTypes: { name: string; share: number; priceMul: number; plans: string[] }[];
}

export const HOTELS: DemoHotel[] = [
  {
    id: "self",
    name: "Khách sạn của bạn",
    self: true,
    windows: 20,
    rooms: 48,
    pressure: 0.8,
    basePrice: 1_350_000,
    roomTypes: [
      { name: "Deluxe giường đôi hướng biển", share: 0.72, priceMul: 1, plans: ["Hoàn huỷ miễn phí", "Gồm bữa sáng"] },
      { name: "Superior hai giường", share: 0.18, priceMul: 0.86, plans: ["Không hoàn huỷ"] },
      { name: "Suite gia đình", share: 0.1, priceMul: 1.75, plans: ["Hoàn huỷ miễn phí"] },
    ],
  },
  {
    id: "haiau",
    name: "Hải Âu",
    self: false,
    windows: 16,
    rooms: 40,
    pressure: 1,
    basePrice: 1_200_000,
    roomTypes: [
      { name: "Deluxe giường đôi", share: 0.6, priceMul: 1, plans: ["Gồm bữa sáng"] },
      { name: "Standard hai giường", share: 0.4, priceMul: 0.85, plans: ["Không hoàn huỷ"] },
    ],
  },
  {
    id: "ngoclan",
    name: "Ngọc Lan",
    self: false,
    windows: 12,
    rooms: 22,
    pressure: 1.25,
    basePrice: 1_550_000,
    roomTypes: [
      { name: "Boutique giường đôi", share: 0.7, priceMul: 1, plans: ["Hoàn huỷ miễn phí", "Gồm bữa sáng"] },
      { name: "Junior suite", share: 0.3, priceMul: 1.45, plans: ["Gồm bữa sáng"] },
    ],
  },
  {
    id: "catvang",
    name: "Cát Vàng",
    self: false,
    windows: 16,
    rooms: 34,
    pressure: 1.1,
    basePrice: 1_100_000,
    roomTypes: [
      { name: "Superior giường đôi", share: 0.55, priceMul: 1, plans: ["Không hoàn huỷ"] },
      { name: "Deluxe ban công", share: 0.45, priceMul: 1.2, plans: ["Hoàn huỷ miễn phí"] },
    ],
  },
  {
    id: "saobien",
    name: "Sao Biển",
    self: false,
    windows: 24,
    rooms: 80,
    pressure: 0.7,
    basePrice: 1_800_000,
    roomTypes: [
      { name: "Premier hướng biển", share: 0.45, priceMul: 1, plans: ["Hoàn huỷ miễn phí", "Gồm bữa sáng"] },
      { name: "Deluxe hướng phố", share: 0.4, priceMul: 0.82, plans: ["Gồm bữa sáng"] },
      { name: "Căn hộ hai phòng ngủ", share: 0.15, priceMul: 2.1, plans: ["Hoàn huỷ miễn phí"] },
    ],
  },
];

export interface RoomTypeObs {
  name: string;
  left: number;
  confidence: Confidence;
  /** Con số hiển thị được: đúng X (exact), ít nhất X (capped), null (hidden). */
  shown: number | null;
  price: number | null;
  plans: string[];
}

export interface HotelObs {
  left: number;
  price: number | null;
  types: RoomTypeObs[];
  /** Tóm tắt mức khách sạn cho ô bảng và cửa sổ tranh. */
  status: "available" | "sold_out";
  /** Tổng phòng biết chắc (exact + mức sàn của capped). */
  known: number;
  hasCapped: boolean;
  hasHidden: boolean;
}

export interface DemoEvent {
  hotelId: string;
  night: number;
  scan: number;
  kind: "sold_out" | "restock" | "rooms_decrease" | "low_stock_enter" | "price_down" | "price_up";
  from: number | null;
  to: number | null;
}

export interface DemoNight {
  index: number;
  iso: string;
  label: string;
  weekday: string;
  day: string;
  weekend: boolean;
}

export interface Demo {
  nights: DemoNight[];
  /** obs[hotel][night][scan], scan 0..5: hôm qua 06/14/22, hôm nay 06/14/22. */
  obs: Record<string, HotelObs[][]>;
  events: DemoEvent[];
  /** Đêm cao điểm (thứ Bảy) mà câu chuyện xoay quanh. */
  peak: number;
  /** Công suất PMS của khách sạn bạn theo đêm (0..1). */
  occupancy: number[];
}

export const SCAN_LABELS = [
  "Hôm qua 06:00",
  "Hôm qua 14:00",
  "Hôm qua 22:00",
  "Hôm nay 06:00",
  "Hôm nay 14:00",
  "Hôm nay 22:00",
];

const WEEKDAYS = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"];

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function roundPrice(v: number): number {
  return Math.round(v / 10_000) * 10_000;
}

function confidenceOf(left: number): { confidence: Confidence; shown: number | null } {
  if (left <= 0) return { confidence: "sold_out", shown: 0 };
  if (left <= BADGE_MAX) return { confidence: "exact", shown: left };
  if (left >= DROPDOWN_CAP) return { confidence: "capped", shown: DROPDOWN_CAP };
  return { confidence: "hidden", shown: null };
}

/**
 * Kịch bản cố định cho đêm cao điểm (thứ Bảy) và đêm trước đó, để tranh đầu trang và bản
 * tin kể cùng một câu chuyện: thị trường kín dần trong ngày, Cát Vàng giảm giá đêm thứ Sáu.
 */
const PEAK_SCRIPT: Record<string, number[]> = {
  self: [19, 17, 16, 15, 14, 14],
  haiau: [5, 4, 3, 2, 0, 0],
  ngoclan: [3, 2, 2, 1, 1, 0],
  catvang: [7, 6, 5, 4, 2, 0],
  saobien: [14, 12, 11, 10, 7, 4],
};
const EVE_SCRIPT: Record<string, number[]> = {
  self: [22, 21, 20, 19, 19, 18],
  haiau: [6, 5, 5, 4, 3, 3],
  ngoclan: [4, 4, 3, 3, 2, 2],
  catvang: [9, 9, 9, 8, 8, 8],
  saobien: [16, 15, 14, 13, 12, 12],
};

function splitTypes(hotel: DemoHotel, total: number, rand: () => number): number[] {
  const counts = hotel.roomTypes.map((t) => Math.floor(total * t.share));
  let rest = total - counts.reduce((a, b) => a + b, 0);
  let i = 0;
  while (rest > 0) {
    counts[i % counts.length] += 1;
    rest -= 1;
    i += 1;
  }
  // Loại phòng đắt nhất hết trước khi thị trường nóng.
  if (total > 0 && total < 6 && counts.length > 2 && rand() < 0.6) {
    const last = counts.length - 1;
    counts[0] += counts[last];
    counts[last] = 0;
  }
  return counts;
}

function observe(hotel: DemoHotel, total: number, demand: number, rand: () => number, priceShift = 1): HotelObs {
  const counts = splitTypes(hotel, total, rand);
  const types: RoomTypeObs[] = hotel.roomTypes.map((t, i) => {
    const left = counts[i];
    const { confidence, shown } = confidenceOf(left);
    return {
      name: t.name,
      left,
      confidence,
      shown,
      price: left > 0 ? roundPrice(hotel.basePrice * t.priceMul * (1 + 0.32 * demand) * priceShift) : null,
      plans: t.plans,
    };
  });
  const open = types.filter((t) => t.left > 0);
  const known = types.reduce((a, t) => a + (t.confidence === "exact" || t.confidence === "capped" ? (t.shown ?? 0) : 0), 0);
  return {
    left: total,
    price: open.length ? Math.min(...open.map((t) => t.price ?? Infinity)) : null,
    types,
    status: total > 0 ? "available" : "sold_out",
    known,
    hasCapped: types.some((t) => t.confidence === "capped"),
    hasHidden: types.some((t) => t.confidence === "hidden"),
  };
}

function toISO(d: Date): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

export function buildDemo(startISO: string): Demo {
  const [y, m, d] = startISO.split("-").map(Number);
  const nights: DemoNight[] = Array.from({ length: 30 }, (_, i) => {
    const date = new Date(Date.UTC(y, m - 1, d + i));
    const wd = date.getUTCDay();
    const day = `${date.getUTCDate()}/${date.getUTCMonth() + 1}`;
    return {
      index: i,
      iso: toISO(date),
      label: `${WEEKDAYS[wd]} ${day}`,
      weekday: WEEKDAYS[wd],
      day,
      weekend: wd === 5 || wd === 6,
    };
  });

  // Thứ Bảy đầu tiên cách hôm nay ít nhất 10 đêm.
  const peak = nights.findIndex((n) => n.index >= 10 && n.weekday === "T7");

  const demand = nights.map((n) => {
    let v = 0.28 + (n.weekend ? 0.3 : 0);
    if (n.index === peak || n.index === peak - 1) v = 0.95;
    if (n.index === peak + 1) v = 0.6;
    if (n.index < 3) v += 0.12;
    return Math.min(1, v);
  });

  const obs: Record<string, HotelObs[][]> = {};
  HOTELS.forEach((hotel, h) => {
    obs[hotel.id] = nights.map((n) => {
      const rand = mulberry32(1000 * (h + 1) + n.index * 7 + 13);
      const script = n.index === peak ? PEAK_SCRIPT[hotel.id] : n.index === peak - 1 ? EVE_SCRIPT[hotel.id] : null;
      let totals: number[];
      if (script) {
        totals = script;
      } else {
        const capacity = hotel.rooms;
        const closeness = 1 - n.index / 40;
        const squeeze = demand[n.index] * hotel.pressure;
        let left = Math.round(capacity * (0.82 - squeeze * 0.62 - rand() * 0.18));
        // Cuối tuần gần, khách sạn nhỏ có lúc chỉ còn vài phòng lẻ hoặc kín hẳn.
        if (!hotel.self && n.weekend && rand() < squeeze * 0.55 * closeness) left = Math.floor(rand() * 4);
        left = Math.max(0, Math.min(capacity, left));
        totals = [];
        for (let s = 0; s < 6; s += 1) {
          if (s > 0) {
            const sale = rand() < squeeze * closeness * 0.75 ? 1 + Math.floor(rand() * 2) : 0;
            const cancel = left === 0 && rand() < 0.12 ? 1 : 0;
            left = Math.max(0, left - sale) + cancel;
          }
          totals.push(left);
        }
      }
      return totals.map((total, s) => {
        // Cát Vàng giảm giá 8% cho đêm thứ Sáu từ lượt 14:00 hôm nay.
        const shift = hotel.id === "catvang" && n.index === peak - 1 && s >= 4 ? 0.92 : 1;
        return observe(hotel, total, demand[n.index], mulberry32(77 * (h + 1) + n.index * 31 + s), shift);
      });
    });
  });

  const events: DemoEvent[] = [];
  for (const hotel of HOTELS) {
    nights.forEach((n) => {
      const row = obs[hotel.id][n.index];
      for (let s = 1; s < 6; s += 1) {
        const a = row[s - 1];
        const b = row[s];
        const push = (kind: DemoEvent["kind"], from: number | null, to: number | null) =>
          events.push({ hotelId: hotel.id, night: n.index, scan: s, kind, from, to });
        if (a.status === "available" && b.status === "sold_out") push("sold_out", a.left, 0);
        else if (a.status === "sold_out" && b.status === "available") push("restock", 0, b.left);
        else if (a.left <= BADGE_MAX && b.left <= BADGE_MAX && b.left < a.left) {
          if (a.left > 3 && b.left <= 3) push("low_stock_enter", a.left, b.left);
          else push("rooms_decrease", a.left, b.left);
        }
        if (a.price && b.price) {
          const pct = (b.price - a.price) / a.price;
          if (pct <= -0.03) push("price_down", a.price, b.price);
          if (pct >= 0.03) push("price_up", a.price, b.price);
        }
      }
    });
  }

  const occupancy = nights.map((n) => {
    const rand = mulberry32(5000 + n.index);
    if (n.index === peak) return 0.58;
    if (n.index === peak - 1) return 0.52;
    return Math.min(0.92, 0.34 + demand[n.index] * 0.42 + rand() * 0.08);
  });

  return { nights, obs, events, peak, occupancy };
}

export const EVENT_LABEL: Record<DemoEvent["kind"], string> = {
  sold_out: "Hết phòng",
  restock: "Có phòng lại",
  rooms_decrease: "Giảm phòng",
  low_stock_enter: "Sắp hết phòng",
  price_down: "Giảm giá",
  price_up: "Tăng giá",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  exact: "Chính xác",
  capped: "Ít nhất",
  hidden: "Ẩn",
  sold_out: "Hết",
};

/** Số hiển thị mức khách sạn: đúng X, ít nhất X, hoặc HẾT. */
export function plaqueText(o: HotelObs): string {
  if (o.status === "sold_out") return "HẾT";
  if (o.hasCapped || o.hasHidden) return o.known > 0 ? `≥${o.known}` : "CÒN";
  return String(o.known);
}

export function formatVnd(v: number | null): string {
  if (v == null) return "—";
  return `${v.toLocaleString("vi-VN")} ₫`;
}

export function formatThousands(v: number | null): string {
  if (v == null) return "—";
  return Math.round(v / 1000).toLocaleString("vi-VN");
}

export function hotelName(id: string): string {
  return HOTELS.find((h) => h.id === id)?.name ?? id;
}

/** Ngày hôm nay theo giờ Việt Nam, dạng YYYY-MM-DD. */
export function todayInVietnam(now = new Date()): string {
  const shifted = new Date(now.getTime() + 7 * 3600 * 1000);
  return toISO(shifted);
}
