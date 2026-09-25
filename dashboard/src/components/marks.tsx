import type { DateCell, RoomSnapshotOut } from "@/lib/api";
import { fmtInt } from "@/lib/format";
import { cx } from "./ui";

/**
 * Bốn dấu mức tin cậy (cùng quy ước với trang giới thiệu):
 * vàng = Booking báo số chính xác (càng đậm càng ít phòng), sọc = ít nhất N,
 * viền đứt = còn phòng nhưng không lộ số, tím đậm = hết phòng.
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
};

/** Độ đậm vàng theo số phòng còn: ≤3 đậm, 4–10 vừa, >10 nhạt. */
export function exactShade(n: number): string {
  if (n <= 3) return "sb-mark-exact";
  if (n <= 10) return "sb-mark-exact-2";
  return "sb-mark-exact-1";
}

/** Dấu cho một ô khách sạn × đêm (mức khách sạn). */
export function cellMark(cell: DateCell | undefined): Mark {
  if (!cell || cell.availability_status === null) {
    return { kind: "nodata", cls: "sb-mark-nodata", text: "", label: "Chưa có dữ liệu" };
  }
  if (cell.availability_status === "sold_out") {
    return { kind: "sold_out", cls: "sb-mark-sold_out", text: "HẾT", label: "Hết phòng" };
  }
  if (cell.availability_status === "unknown") {
    return { kind: "unknown", cls: "sb-mark-unknown", text: "?", label: "Không đọc được (bị chặn hoặc lỗi)" };
  }
  const n = cell.exact_rooms_left;
  if (n === null) {
    return { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "Còn phòng, Booking không lộ số" };
  }
  return { kind: "exact", cls: exactShade(n), text: String(n), label: `Còn ${n} phòng (Booking báo chính xác)` };
}

/** Dấu cho một loại phòng ở một lần quét. */
export function roomMark(s: Pick<RoomSnapshotOut, "stock_confidence" | "rooms_left" | "dropdown_max">): Mark {
  switch (s.stock_confidence) {
    case "sold_out":
      return { kind: "sold_out", cls: "sb-mark-sold_out", text: "HẾT", label: "Hết phòng" };
    case "capped": {
      const n = s.rooms_left ?? s.dropdown_max;
      return { kind: "capped", cls: "sb-mark-capped", text: n === null ? "≥" : `≥${n}`, label: n === null ? "Còn ít nhất vài phòng" : `Còn ít nhất ${fmtInt(n)} phòng` };
    }
    case "hidden":
      return { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "Còn phòng, Booking không lộ số" };
    default: {
      const n = s.rooms_left;
      if (n === null) return { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "Còn phòng, không rõ số" };
      return { kind: "exact", cls: exactShade(n), text: String(n), label: `Còn ${n} phòng (chính xác)` };
    }
  }
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
  const short: Record<MarkKind, string> = {
    exact: "Chính xác",
    capped: "Ít nhất",
    hidden: "Ẩn số",
    sold_out: "Hết phòng",
    unknown: "Không rõ",
    nodata: "Chưa có",
  };
  return (
    <span className={cx("inline-flex items-center gap-2 whitespace-nowrap", className)} title={mark.label}>
      <MarkSwatch mark={mark} size={mark.kind === "capped" ? 30 : 24} className={mark.kind === "capped" ? "!w-auto min-w-[30px] px-1" : undefined} />
      <span className="text-sm text-muted max-sm:hidden">{short[mark.kind]}</span>
    </span>
  );
}

const LEGEND_HOTEL: Array<{ mark: Mark; text: string }> = [
  { mark: { kind: "exact", cls: "sb-mark-exact", text: "2", label: "" }, text: "Số phòng Booking báo chính xác, vàng càng đậm càng ít phòng" },
  { mark: { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "" }, text: "Còn phòng, không lộ số" },
  { mark: { kind: "sold_out", cls: "sb-mark-sold_out", text: "HẾT", label: "" }, text: "Hết phòng" },
  { mark: { kind: "unknown", cls: "sb-mark-unknown", text: "?", label: "" }, text: "Không đọc được" },
  { mark: { kind: "nodata", cls: "sb-mark-nodata", text: "", label: "" }, text: "Chưa quét" },
];

const LEGEND_ROOM: Array<{ mark: Mark; text: string }> = [
  { mark: { kind: "exact", cls: "sb-mark-exact", text: "2", label: "" }, text: "Chính xác (“Chỉ còn 2 phòng”)" },
  { mark: { kind: "capped", cls: "sb-mark-capped", text: "≥", label: "" }, text: "Ít nhất N (số trong ô chọn phòng)" },
  { mark: { kind: "hidden", cls: "sb-mark-hidden", text: "", label: "" }, text: "Còn phòng, không lộ số" },
  { mark: { kind: "sold_out", cls: "sb-mark-sold_out", text: "HẾT", label: "" }, text: "Hết phòng" },
];

export function MarksLegend({ variant = "hotel", className, children }: { variant?: "hotel" | "room"; className?: string; children?: React.ReactNode }) {
  const items = variant === "hotel" ? LEGEND_HOTEL : LEGEND_ROOM;
  return (
    <ul className={cx("flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted", className)}>
      {items.map((it) => (
        <li key={it.text} className="flex items-center gap-2">
          <MarkSwatch mark={it.mark} size={18} />
          {it.text}
        </li>
      ))}
      {children}
    </ul>
  );
}
