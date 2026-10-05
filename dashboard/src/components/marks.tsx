import { useTranslations } from "next-intl";
import { useMemo } from "react";
import type { DateCell, RoomSnapshotOut } from "@/lib/api";
import { cx } from "./ui";

/**
 * Dấu số phòng còn theo mức tin cậy: số chính xác tô theo thang nhiệt (đỏ hết → xanh lá nhiều),
 * sọc = ít nhất N, viền đứt = còn phòng nhưng không lộ số, đỏ đậm = hết phòng.
 * Thêm hai trạng thái chất lượng dữ liệu: không đọc được, chưa quét.
 */

export type MarkKind = "exact" | "capped" | "hidden" | "sold_out" | "unknown" | "nodata";

export type Mark = {
  kind: MarkKind;
  /** Lớp CSS nền của ô. */
  cls: string;
  /** Chữ trong ô (ngắn). */
  text: string;
  /** Mô tả đầy đủ cho trình đọc màn hình và tooltip. */
  label: string;
  /** Mức sàn suy từ số phòng còn của một mức giá, không phải của cả loại phòng. */
  rate?: boolean;
};

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

  /** Dấu cho một ô khách sạn × đêm (mức khách sạn). `beyond`: đêm nằm sau phạm vi quét. */
  function cellMark(cell: DateCell | undefined, beyond = false): Mark {
    if (!cell || cell.availability_status === null) {
      return beyond ? beyondMark : { kind: "nodata", cls: "sb-mark-nodata", text: "", label: t("noData") };
    }
    if (cell.availability_status === "sold_out") {
      return { kind: "sold_out", cls: "sb-mark-sold_out", text: t("soldOutShort"), label: t("soldOut") };
    }
    if (cell.availability_status === "unknown") {
      return { kind: "unknown", cls: "sb-mark-unknown", text: "?", label: t("unknown") };
    }
    const n = cell.exact_rooms_left;
    if (n === null) {
      return { kind: "hidden", cls: "sb-mark-hidden", text: "", label: t("hiddenChannel") };
    }
    return { kind: "exact", cls: exactShade(n), text: String(n), label: t("exactChannel", { count: n }) };
  }

  /**
   * Dấu cho một loại phòng ở một lần quét. `stock_scope = "rate"`: kênh chỉ báo "còn N phòng có giá
   * này" (Trip.com), nên với cả loại phòng đó chỉ là mức sàn ≥N.
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

  return { cellMark, roomMark, beyondMark };
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
      style={{ width: size, height: size, fontSize: mark.kind === "sold_out" ? Math.max(8, size * 0.36) : Math.max(10, size * 0.5) }}
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

/** `key`: khoá trong components.marks.legend. Chữ "HẾT" trong ô hết phòng điền lúc render. */
type LegendItem = { mark: Mark; key: "hotelExact" | "hidden" | "soldOut" | "unknown" | "notScanned" | "roomExact" | "roomCapped" };

const LEGEND_HOTEL: LegendItem[] = [
  { mark: { kind: "exact", cls: "sb-heat-1", text: "2", label: "" }, key: "hotelExact" },
  { mark: { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "" }, key: "hidden" },
  { mark: { kind: "sold_out", cls: "sb-mark-sold_out", text: "", label: "" }, key: "soldOut" },
  { mark: { kind: "unknown", cls: "sb-mark-unknown", text: "?", label: "" }, key: "unknown" },
  { mark: { kind: "nodata", cls: "sb-mark-nodata", text: "", label: "" }, key: "notScanned" },
];

const LEGEND_ROOM: LegendItem[] = [
  { mark: { kind: "exact", cls: "sb-heat-1", text: "2", label: "" }, key: "roomExact" },
  { mark: { kind: "capped", cls: "sb-mark-capped", text: "≥", label: "" }, key: "roomCapped" },
  { mark: { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "" }, key: "hidden" },
  { mark: { kind: "sold_out", cls: "sb-mark-sold_out", text: "", label: "" }, key: "soldOut" },
];

export function MarksLegend({ variant = "hotel", className, children }: { variant?: "hotel" | "room"; className?: string; children?: React.ReactNode }) {
  const t = useTranslations("components.marks");
  const items = variant === "hotel" ? LEGEND_HOTEL : LEGEND_ROOM;
  return (
    <ul className={cx("flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted", className)}>
      {items.map((it) => (
        <li key={it.key} className="flex items-center gap-2">
          <MarkSwatch mark={it.mark.kind === "sold_out" ? { ...it.mark, text: t("soldOutShort") } : it.mark} size={18} />
          {t(`legend.${it.key}`)}
        </li>
      ))}
      {children}
    </ul>
  );
}
