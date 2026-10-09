/**
 * Độ mới dữ liệu: MỘT định nghĩa "Dữ liệu mới nhất lúc …" cho mọi màn (Bảng điều khiển, Hôm nay,
 * Đối thủ, Giá, Phòng trống, Terminal+, khung app). Roadmap 0.6, 0.7.
 *
 * "Dữ liệu mới nhất lúc" = QUAN SÁT THÀNH CÔNG cuối cùng trên Booking.com (`GET /data-status`:
 * `last_data_at`), không phải lượt quét kết thúc cuối cùng: lượt 0 dữ liệu không làm mới mốc này.
 * Không có dữ liệu mới quá một chu kỳ quét (`stale_after_hours`) là "cũ" (`stale`) và được tô đỏ.
 * Danh sách lượt quét vẫn được đọc để biết lượt đang chạy và lượt gần nhất không thu được gì. Backend
 * cũ chưa có `/data-status` thì rơi về cách tính theo lượt quét.
 */

import { api, type DataStatusOut, type ScanRunOut } from "./api";
import { num, scanOverdue } from "./format";
import { useApi } from "./hooks";

/** Số lượt đọc để tìm lượt có dữ liệu gần nhất (API cho tối đa 100). */
export const FRESHNESS_RUNS = 50;

const DAY_MS = 24 * 3600 * 1000;

type RunLike = Pick<ScanRunOut, "trigger_key" | "status" | "finished_at" | "ok_count" | "sold_out_count">;

/** Lượt quét thị trường cả khu vực (Cài đặt › Thị trường), không phải lượt compset. */
export function isMarketRun(r: Pick<ScanRunOut, "trigger_key">): boolean {
  return r.trigger_key === "market" || r.trigger_key.startsWith("market:");
}

export function runFinished(r: RunLike): boolean {
  return r.status !== "running" && r.finished_at !== null;
}

/** Lượt thu được ít nhất một đêm (còn phòng hoặc hết phòng). */
export function runCollected(r: RunLike): boolean {
  return r.ok_count + r.sold_out_count > 0;
}

export type DataFreshness = {
  /** Mốc "Dữ liệu mới nhất lúc": quan sát thành công cuối cùng. */
  updatedAt: string | null;
  /** Không có dữ liệu Booking.com mới quá một chu kỳ quét. */
  stale: boolean;
  /** Ngưỡng "cũ" (giờ) theo lịch quét của tenant; null khi chưa có `/data-status`. */
  staleAfterHours: number | null;
  /** Lượt compset đã kết thúc mới nhất (có hoặc không có dữ liệu). */
  latest: ScanRunOut | null;
  /** Lượt đã kết thúc mới nhất không thu được gì. */
  latestEmpty: boolean;
  /** Có lượt compset đang chạy. */
  running: boolean;
  /** Đã lỡ ít nhất một mốc quét theo lịch (chỉ tính khi truyền `scanTimes`). */
  overdue: boolean;
  /** ok | warn (vàng: lượt mới nhất rỗng nhưng còn dữ liệu trong 24 giờ, hoặc lỡ lịch) | bad (đỏ: dữ liệu cũ / không có dữ liệu trong 24 giờ). */
  tone: "ok" | "warn" | "bad";
};

/** Tính độ mới từ `/data-status` (ưu tiên) và danh sách lượt quét (`api.runs`, mọi thứ tự). */
export function dataFreshness(status: DataStatusOut | undefined, runs: ScanRunOut[] | undefined, opts: { scanTimes?: string[]; now?: number } = {}): DataFreshness {
  const now = opts.now ?? Date.now();
  const compset = (runs ?? []).filter((r) => !isMarketRun(r));
  const finished = compset.filter(runFinished).sort((a, b) => (b.finished_at ?? "").localeCompare(a.finished_at ?? ""));
  const latest = finished[0] ?? null;
  const latestEmpty = latest !== null && !runCollected(latest);
  const running = compset.some((r) => r.status === "running");

  // Mốc chung: quan sát thành công cuối cùng; dữ liệu cũ (chưa có /data-status) thì theo lượt có dữ liệu.
  const updatedAt = status ? status.last_data_at : (finished.find(runCollected)?.finished_at ?? null);
  const stale = status?.stale ?? false;

  const overdue = !running && !latestEmpty && !!opts.scanTimes && scanOverdue(updatedAt, opts.scanTimes, new Date(now));
  const recent = updatedAt !== null && now - new Date(updatedAt).getTime() <= DAY_MS;
  let tone: DataFreshness["tone"];
  if (stale) tone = "bad";
  else if (status && updatedAt === null) tone = "bad";
  else if (latestEmpty) tone = recent ? "warn" : "bad";
  else tone = overdue ? "warn" : "ok";
  return { updatedAt, stale, staleAfterHours: status?.stale_after_hours ?? null, latest, latestEmpty, running, overdue, tone };
}

/** Tỷ lệ thành công 7 ngày (0..1) thành phần trăm nguyên; null khi chưa có probe. */
export function successPct(s: Pick<DataStatusOut, "success_rate_7d" | "probes_7d">): number | null {
  const r = num(s.success_rate_7d);
  return r === null || s.probes_7d === 0 ? null : Math.round(r * 100);
}

export type FreshnessState = DataFreshness & { loaded: boolean; runs: ScanRunOut[]; status: DataStatusOut | undefined };

/** Tải `/data-status` + lượt quét và tính độ mới. `scanTimes` (lịch tenant) để báo lỡ lịch. */
export function useDataFreshness(scanTimes?: string[]): FreshnessState {
  const status = useApi("freshness:status", () => api.dataStatus());
  const runs = useApi("freshness:runs", () => api.runs(FRESHNESS_RUNS));
  // /data-status lỗi (backend cũ): vẫn hiện theo lượt quét.
  const statusDone = status.data !== undefined || status.error !== undefined;
  return {
    ...dataFreshness(status.data, runs.data, { scanTimes }),
    loaded: runs.data !== undefined && statusDone,
    runs: runs.data ?? [],
    status: status.data,
  };
}
