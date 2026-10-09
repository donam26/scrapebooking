import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { cellState, type DateCell, type RoomSnapshotOut } from "@/lib/api";
import { cx } from "./ui";

/**
 * Dấu số phòng còn theo mức tin cậy: số chính xác tô theo thang nhiệt (đỏ hết → xanh lá nhiều),
 * sọc = ít nhất N, viền đứt = còn phòng nhưng không lộ số, đỏ đậm = hết phòng.
 * Năm trạng thái một ô (roadmap 2.7): còn bán / hết phòng / bị hạn chế (hổ phách, KHÔNG đỏ: bán
 * được ở số đêm khác hoặc đóng ngày đến) / không có giá (xám) / lỗi (sọc). Thêm: chưa quét, ngoài
 * phạm vi; ô có quan sát cũ hơn 48 giờ thì làm xám (`sb-stale`).
 */

export type MarkKind = "exact" | "capped" | "hidden" | "sold_out" | "restricted" | "no_price" | "error" | "unknown" | "nodata";

export type Mark = {
  kind: MarkKind;
  /** Lớp CSS nền của ô (kèm `sb-stale` khi dữ liệu cũ). */
  cls: string;
  /** Chữ trong ô (ngắn). */
  text: string;
  /** Mô tả đầy đủ cho trình đọc màn hình và tooltip. */
  label: string;
  /** Mức sàn suy từ số phòng còn của một mức giá, không phải của cả loại phòng. */
  rate?: boolean;
  /** Quan sát cũ hơn 48 giờ. */
  stale?: boolean;
  /** Khuyến mãi đang chạy: "Late Escape −40%, Mobile"; null khi không có. */
  promo?: string | null;
};

/** Ô chữ (HẾT, H.CHẾ, LỖI…) dùng cỡ chữ nhỏ hơn ô số. */
export function isWordMark(kind: MarkKind): boolean {
  return kind === "sold_out" || kind === "restricted" || kind === "error";
}

/**
 * Thang nhiệt theo số phòng còn (giao diện OTARadar): 0 đỏ, ≤3 cam, 4–10 hổ phách,
 * 11–20 vàng nhạt, 21–30 xanh nhạt, >30 xanh lá.
 */
export function exactShade(n: number): string {
  if (n <= 0) return "sb-heat-0";
  if (n <= 3) return "sb-heat-1";
  if (n <= 10) return "sb-heat-2";
  if (n <= 20) return "sb-heat-3";
  if (n <= 30) return "sb-heat-4";
  return "sb-heat-5";
}

/** Nhãn mức của thang nhiệt (chú giải, tooltip). */
/** Thang màu số phòng còn; chữ của từng mức: `label("heatLevel", h.key)`. */
export const HEAT_LEVELS = [
  { cls: "sb-heat-0", key: "soldOut" },
  { cls: "sb-heat-1", key: "veryFew" },
  { cls: "sb-heat-2", key: "few" },
  { cls: "sb-heat-3", key: "some" },
  { cls: "sb-heat-4", key: "many" },
  { cls: "sb-heat-5", key: "plenty" },
] as const;

export type MarksTranslator = ReturnType<typeof useTranslations<"components.marks">>;

/**
 * Dấu ô theo ngôn ngữ. Component: `const { cellMark, roomMark, beyondMark } = useMarks();`
 * Ngoài React: `createMarks(t)` với `t = await getTranslations("components.marks")`.
 */
export function createMarks(t: MarksTranslator) {
  /** Đêm sau phạm vi quét của tenant (hôm nay + horizon): chưa tới lượt, không phải thiếu dữ liệu. */
  const beyondMark: Mark = { kind: "nodata", cls: "sb-mark-beyond", text: "", label: t("beyond") };

  /** Khuyến mãi của ô thành chữ: "Late Escape −40%, Mobile". */
  function promoText(cell: Pick<DateCell, "promos"> | undefined): string | null {
    const entries = Object.entries(cell?.promos ?? {});
    if (entries.length === 0) return null;
    return entries
      .map(([name, depth]) => {
        const d = depth === null ? null : Math.round(Number(depth));
        return d !== null && Number.isFinite(d) && d > 0 ? t("promoDepth", { name, pct: d }) : name;
      })
      .join(", ");
  }

  /** Dấu cho một ô khách sạn × đêm (mức khách sạn). `beyond`: đêm nằm sau phạm vi quét. */
  function cellMark(cell: DateCell | undefined, beyond = false): Mark {
    const state = cellState(cell);
    if (!cell || state === null) {
      return beyond ? beyondMark : { kind: "nodata", cls: "sb-mark-nodata", text: "", label: t("noData") };
    }
    const base = ((): Mark => {
      switch (state) {
        case "sold_out":
          return { kind: "sold_out", cls: "sb-mark-sold_out", text: t("soldOutShort"), label: t("soldOut") };
        case "restricted": {
          const n = cell.min_stay ?? 1;
          const rooms = cell.exact_rooms_left;
          if (n > 1) {
            return {
              kind: "restricted",
              cls: "sb-mark-restricted",
              text: t("minStayShort", { count: n }),
              label: rooms === null ? t("minStay", { count: n }) : t("minStayRooms", { count: n, rooms }),
            };
          }
          return { kind: "restricted", cls: "sb-mark-restricted", text: t("restrictedShort"), label: t("restricted") };
        }
        case "no_price":
          return { kind: "no_price", cls: "sb-mark-no_price", text: "–", label: t("noPrice") };
        case "error":
          return { kind: "error", cls: "sb-mark-error", text: t("errorShort"), label: t("error") };
        default: {
          const n = cell.exact_rooms_left;
          if (n === null) return { kind: "hidden", cls: "sb-mark-hidden", text: "", label: t("hiddenChannel") };
          return { kind: "exact", cls: exactShade(n), text: String(n), label: t("exactChannel", { count: n }) };
        }
      }
    })();
    const promo = promoText(cell);
    const label = [base.label, promo ? t("promo", { promos: promo }) : null, cell.stale ? t("stale") : null].filter(Boolean).join(" · ");
    return { ...base, cls: cx(base.cls, cell.stale && "sb-stale"), label, stale: cell.stale, promo };
  }

  /**
   * Dấu cho một loại phòng ở một lần quét. `stock_scope = "rate"`: số phòng còn chỉ của một mức giá
   * ("còn N phòng có giá này"), nên với cả loại phòng đó chỉ là mức sàn ≥N.
   */
  function roomMark(s: Pick<RoomSnapshotOut, "stock_confidence" | "rooms_left" | "dropdown_max"> & { stock_scope?: string }): Mark {
    if (s.stock_scope === "rate" && s.stock_confidence === "exact" && s.rooms_left !== null) {
      return { kind: "capped", cls: "sb-mark-capped", text: `≥${s.rooms_left}`, label: t("cappedRate", { count: s.rooms_left }), rate: true };
    }
    switch (s.stock_confidence) {
      case "sold_out":
        return { kind: "sold_out", cls: "sb-mark-sold_out", text: t("soldOutShort"), label: t("soldOut") };
      case "capped": {
        const n = s.rooms_left ?? s.dropdown_max;
        return { kind: "capped", cls: "sb-mark-capped", text: n === null ? "≥" : `≥${n}`, label: n === null ? t("cappedSome") : t("capped", { count: n }) };
      }
      case "hidden":
        return { kind: "hidden", cls: "sb-mark-hidden", text: "", label: t("hiddenChannel") };
      default: {
        const n = s.rooms_left;
        if (n === null) return { kind: "hidden", cls: "sb-mark-hidden", text: "", label: t("hiddenUnknown") };
        return { kind: "exact", cls: exactShade(n), text: String(n), label: t("exact", { count: n }) };
      }
    }
  }

  return { cellMark, roomMark, beyondMark, promoText };
}

export type Marks = ReturnType<typeof createMarks>;

export function useMarks(): Marks {
  const t = useTranslations("components.marks");
  return useMemo(() => createMarks(t), [t]);
}

/** Ô dấu vuông (dùng trong chú giải, bảng, chip). */
export function MarkSwatch({ mark, size = 22, className }: { mark: Mark; size?: number; className?: string }) {
  return (
    <span
      aria-hidden
      className={cx("inline-grid shrink-0 place-items-center rounded-[5px] font-bold tabular leading-none", mark.cls, className)}
      style={{ width: size, height: size, fontSize: isWordMark(mark.kind) ? Math.max(7, size * (mark.text.length > 3 ? 0.3 : 0.36)) : Math.max(10, size * 0.5) }}
    >
      {mark.text || "\u200b"}
    </span>
  );
}

/** Ô dấu kèm chữ mô tả ngắn: "≥10 · Ít nhất". */
export function MarkChip({ mark, className }: { mark: Mark; className?: string }) {
  const t = useTranslations("components.marks.chip");
  return (
    <span className={cx("inline-flex items-center gap-2 whitespace-nowrap", className)} title={mark.label}>
      <MarkSwatch mark={mark} size={mark.kind === "capped" ? 30 : 24} className={mark.kind === "capped" ? "!w-auto min-w-[30px] px-1" : undefined} />
      <span className="text-sm text-muted max-sm:hidden">{mark.rate ? t("rate") : t(mark.kind)}</span>
    </span>
  );
}

/** Chấm khuyến mãi ở góc ô (đặt trong phần tử `relative`); tooltip liệt kê nhãn và độ sâu. */
export function PromoDot({ promo, className }: { promo: string | null | undefined; className?: string }) {
  if (!promo) return null;
  return <span aria-hidden title={promo} className={cx("pointer-events-none absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full bg-[#db2777] ring-1 ring-white", className)} />;
}

/** `key`: khoá trong components.marks.legend. Chữ "HẾT" trong ô hết phòng điền lúc render. */
type LegendItem = { mark: Mark; key: "hotelExact" | "hidden" | "soldOut" | "restricted" | "noPrice" | "error" | "unknown" | "notScanned" | "stale" | "roomExact" | "roomCapped" };

const LEGEND_HOTEL: LegendItem[] = [
  { mark: { kind: "exact", cls: "sb-heat-1", text: "2", label: "" }, key: "hotelExact" },
  { mark: { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "" }, key: "hidden" },
  { mark: { kind: "sold_out", cls: "sb-mark-sold_out", text: "", label: "" }, key: "soldOut" },
  { mark: { kind: "restricted", cls: "sb-mark-restricted", text: "", label: "" }, key: "restricted" },
  { mark: { kind: "no_price", cls: "sb-mark-no_price", text: "–", label: "" }, key: "noPrice" },
  { mark: { kind: "error", cls: "sb-mark-error", text: "", label: "" }, key: "error" },
  { mark: { kind: "exact", cls: "sb-heat-4 sb-stale", text: "9", label: "" }, key: "stale" },
  { mark: { kind: "nodata", cls: "sb-mark-nodata", text: "", label: "" }, key: "notScanned" },
];

const LEGEND_ROOM: LegendItem[] = [
  { mark: { kind: "exact", cls: "sb-heat-1", text: "2", label: "" }, key: "roomExact" },
  { mark: { kind: "capped", cls: "sb-mark-capped", text: "≥", label: "" }, key: "roomCapped" },
  { mark: { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "" }, key: "hidden" },
  { mark: { kind: "sold_out", cls: "sb-mark-sold_out", text: "", label: "" }, key: "soldOut" },
];

/** Chú giải dấu ô. `promo`: thêm mục chấm khuyến mãi (màn có hiện chấm này). */
export function MarksLegend({ variant = "hotel", promo = variant === "hotel", className, children }: { variant?: "hotel" | "room"; promo?: boolean; className?: string; children?: React.ReactNode }) {
  const t = useTranslations("components.marks");
  const items = variant === "hotel" ? LEGEND_HOTEL : LEGEND_ROOM;
  const filled = (m: Mark): Mark => (m.kind === "sold_out" ? { ...m, text: t("soldOutShort") } : m.kind === "restricted" ? { ...m, text: t("minStayShort", { count: 2 }) } : m.kind === "error" ? { ...m, text: t("errorShort") } : m);
  return (
    <ul className={cx("flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted", className)}>
      {items.map((it) => (
        <li key={it.key} className="flex items-center gap-2">
          <MarkSwatch mark={filled(it.mark)} size={18} />
          {t(`legend.${it.key}`)}
        </li>
      ))}
      {promo && (
        <li className="flex items-center gap-2">
          <span aria-hidden className="relative inline-block h-[18px] w-[18px] rounded-[5px] bg-sunken">
            <PromoDot promo="·" />
          </span>
          {t("legend.promo")}
        </li>
      )}
      {children}
    </ul>
  );
}
