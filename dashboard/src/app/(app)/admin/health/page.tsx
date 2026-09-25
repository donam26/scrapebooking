"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi, useInterval, useMutation } from "@/lib/hooks";
import { fmtDateTime, fmtDayTime, fmtDuration, fmtInt, fmtPct, fmtTime } from "@/lib/format";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE, SESSION_STATUS_TONE } from "@/lib/labels";
import { Badge, Button, ButtonLink, Card, EmptyState, ErrorBox, Note, PageHeader, ROW_CLASS, SkeletonBlock, Skeleton, StatStrip, Table, Td, Th, cx } from "@/components/ui";
import { RunSummary } from "@/components/run-summary";
import { IconCheck, IconExternal, IconHeartbeat, IconRefresh } from "@/components/icons";

const REFRESH_MS = 30_000;

const SESSION_STATUS_LABEL: Record<string, string> = {
  active: "Hoạt động",
  retired: "Đã thu hồi",
  blocked: "Bị chặn",
  expired: "Hết hạn",
};

/** "retired:expired" -> trạng thái chính + lý do. */
function splitStatus(raw: string): { status: string; reason: string | null } {
  const [status, ...rest] = raw.split(":");
  return { status, reason: rest.length ? rest.join(":") : null };
}

function blockTone(rate: number): "good" | "warn" | "bad" {
  if (rate >= 0.2) return "bad";
  if (rate >= 0.1) return "warn";
  return "good";
}

/** Thanh tỷ lệ probe thành công, kèm số đếm thẳng cột. */
function ProbeBar({ ok, total }: { ok: number; total: number }) {
  const share = total > 0 ? ok / total : 0;
  const tone = total === 0 ? "bg-line" : share >= 0.95 ? "bg-yours" : share >= 0.8 ? "bg-[#e0a100]" : "bg-danger";
  return (
    <div className="flex min-w-[140px] items-center justify-end gap-2.5">
      <span className="whitespace-nowrap text-sm text-body tabular">
        {fmtInt(ok)}/{fmtInt(total)}
      </span>
      <span className="h-1.5 w-16 shrink-0 overflow-hidden rounded-full bg-sunken" aria-hidden>
        <span className={cx("block h-full rounded-full", tone)} style={{ width: `${Math.round(share * 100)}%` }} />
      </span>
    </div>
  );
}

function RefreshMeta({ at }: { at: Date | null }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-yours/50" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-yours" />
      </span>
      Tự làm mới mỗi 30 giây{at ? ` · cập nhật lúc ${fmtTime(at.toISOString())}` : ""}
    </span>
  );
}

export default function AdminHealthPage() {
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const summary = useApi("health:summary", async () => {
    const out = await api.health.summary();
    setRefreshedAt(new Date());
    return out;
  });
  const runs = useApi("health:runs", () => api.health.runs(20));
  const sessions = useApi("health:sessions", () => api.health.sessions(50));
  const reloadAll = () => {
    summary.reload();
    runs.reload();
    sessions.reload();
  };
  useInterval(reloadAll, REFRESH_MS);
  const [created, setCreated] = useState<number | null>(null);
  const scanAll = useMutation(async () => {
    setCreated(null);
    const run = await api.health.scanNow();
    setCreated(run.id);
    reloadAll();
    return run;
  });

  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Sức khoẻ scraper"
        subtitle={<RefreshMeta at={refreshedAt} />}
        actions={
          <>
            {s?.grafana_url && (
              <ButtonLink href={s.grafana_url} external icon={<IconExternal size={16} />}>
                Mở Grafana
              </ButtonLink>
            )}
            <Button
              busy={scanAll.busy}
              icon={<IconRefresh size={16} />}
              onClick={() => void scanAll.run()}
              title="Tạo lượt quét thủ công cho mọi tenant đang hoạt động"
            >
              Quét tất cả ngay
            </Button>
          </>
        }
      />
      <ErrorBox error={scanAll.error} className="mb-4" />
      {created !== null && (
        <Note tone="info" icon={<IconCheck size={16} />} className="mb-4">
          Đã tạo lượt quét #{created}. Tiến độ hiện trong bảng “Các lượt quét” ở lần làm mới tới.
        </Note>
      )}
      <ErrorBox error={summary.error} className="mb-4" />

      {!s && !summary.error && (
        <div className="mb-6 space-y-4" aria-busy aria-label="Đang tải">
          <SkeletonBlock className="h-[92px] w-full rounded-xl" />
          <SkeletonBlock className="h-[104px] w-full rounded-xl" />
        </div>
      )}
      {s && (
        <>
          <StatStrip
            className="mb-6"
            items={[
              { label: "Probe 15 phút qua", value: fmtInt(s.probes_15m), hint: "Số lần tải trang ngày lưu trú" },
              {
                label: "Bị chặn 15 phút qua",
                value: fmtInt(s.blocked_15m),
                tone: s.blocked_15m > 0 ? "warn" : "default",
                hint: s.blocked_15m > 0 ? "Có probe bị chặn" : "Không có probe bị chặn",
              },
              {
                label: "Tỷ lệ chặn 15 phút",
                value: fmtPct(s.block_rate_15m * 100),
                tone: s.probes_15m === 0 ? "default" : blockTone(s.block_rate_15m),
                hint: s.block_rate_15m >= 0.2 ? "Vượt ngưỡng cảnh báo 20%" : "Ngưỡng cảnh báo 20%",
              },
              { label: "Session đang hoạt động", value: fmtInt(s.active_sessions), hint: "Phiên trình duyệt qua proxy" },
            ]}
          />
          <Card
            className="mb-6"
            title="Lượt quét gần nhất"
            actions={
              s.pending_analytics_runs.length > 0 ? (
                <Badge tone="amber">Chờ phân tích: {s.pending_analytics_runs.map((id) => `#${id}`).join(", ")}</Badge>
              ) : undefined
            }
          >
            <RunSummary run={s.last_run} />
          </Card>
        </>
      )}

      <Card
        className="mb-6"
        title="Các lượt quét"
        description="20 lượt gần nhất của mọi tenant"
        padded={false}
      >
        <ErrorBox error={runs.error} className="m-4" />
        {!runs.data ? (
          !runs.error && <Skeleton rows={5} className="p-5" />
        ) : runs.data.length === 0 ? (
          <div className="p-5">
            <EmptyState compact icon={<IconHeartbeat />} title="Chưa có lượt quét">
              Lượt quét theo lịch hoặc bấm “Quét tất cả ngay” sẽ hiện ở đây.
            </EmptyState>
          </div>
        ) : (
          <Table dense>
            <thead>
              <tr>
                <Th>Lượt</Th>
                <Th>Mốc</Th>
                <Th>Trạng thái</Th>
                <Th>Bắt đầu</Th>
                <Th>Thời lượng</Th>
                <Th right>Job</Th>
                <Th right>Probe thành công</Th>
                <Th right>Hết</Th>
                <Th right>Chặn</Th>
                <Th right>Lỗi</Th>
              </tr>
            </thead>
            <tbody>
              {runs.data.map((r) => (
                <tr key={r.id} className={ROW_CLASS}>
                  <Td className="whitespace-nowrap font-semibold text-ink tabular">#{r.id}</Td>
                  <Td className="max-w-[220px]">
                    <span className="block truncate font-mono text-xs text-muted" title={r.trigger_key}>
                      {r.trigger_key}
                    </span>
                  </Td>
                  <Td>
                    <Badge tone={RUN_STATUS_TONE[r.status] ?? "gray"}>{RUN_STATUS_LABEL[r.status] ?? r.status}</Badge>
                  </Td>
                  <Td className="whitespace-nowrap tabular">{fmtDayTime(r.started_at ?? r.scheduled_at)}</Td>
                  <Td className="whitespace-nowrap tabular">{fmtDuration(r.started_at, r.finished_at)}</Td>
                  <Td right>{fmtInt(r.total_jobs)}</Td>
                  <Td right>
                    <ProbeBar ok={r.ok_count} total={r.total_probes} />
                  </Td>
                  <Td right>{fmtInt(r.sold_out_count)}</Td>
                  <Td right className={cx(r.blocked_count > 0 && "font-semibold text-danger")}>{fmtInt(r.blocked_count)}</Td>
                  <Td right className={cx(r.error_count > 0 && "font-semibold text-warning-deep")}>{fmtInt(r.error_count)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card title="Session scrape" description="50 phiên gần nhất" padded={false}>
        <ErrorBox error={sessions.error} className="m-4" />
        {!sessions.data ? (
          !sessions.error && <Skeleton rows={5} className="p-5" />
        ) : sessions.data.length === 0 ? (
          <div className="p-5">
            <EmptyState compact title="Chưa có session">
              Worker tạo session khi bắt đầu quét.
            </EmptyState>
          </div>
        ) : (
          <Table dense>
            <thead>
              <tr>
                <Th>Session</Th>
                <Th>Worker</Th>
                <Th>Proxy</Th>
                <Th>Nước</Th>
                <Th>Trạng thái</Th>
                <Th>Tạo lúc</Th>
                <Th>Hết hạn</Th>
                <Th right>Request</Th>
                <Th right>Chặn</Th>
              </tr>
            </thead>
            <tbody>
              {sessions.data.map((x) => {
                const st = splitStatus(x.status);
                return (
                  <tr key={x.id} className={ROW_CLASS}>
                    <Td mono title={x.id} className="text-ink">
                      {x.id.slice(0, 8)}
                    </Td>
                    <Td mono className="text-muted">
                      {x.worker_id}
                    </Td>
                    <Td mono className="text-muted">
                      {x.proxy_id}
                    </Td>
                    <Td>
                      <span className="rounded bg-sunken px-1.5 py-0.5 text-xs font-semibold uppercase text-body">{x.proxy_country}</span>
                    </Td>
                    <Td>
                      <div className="flex flex-col items-start gap-0.5">
                        <Badge tone={SESSION_STATUS_TONE[st.status] ?? "gray"}>{SESSION_STATUS_LABEL[st.status] ?? st.status}</Badge>
                        {(st.reason || x.retired_at) && (
                          <span className="text-xs text-muted">
                            {st.reason ? `${SESSION_STATUS_LABEL[st.reason] ?? st.reason}` : ""}
                            {st.reason && x.retired_at ? " · " : ""}
                            {x.retired_at ? `thu hồi ${fmtDayTime(x.retired_at)}` : ""}
                          </span>
                        )}
                      </div>
                    </Td>
                    <Td className="whitespace-nowrap tabular" title={fmtDateTime(x.created_at)}>
                      {fmtDayTime(x.created_at)}
                    </Td>
                    <Td className="whitespace-nowrap tabular" title={fmtDateTime(x.expires_at)}>
                      {fmtDayTime(x.expires_at)}
                    </Td>
                    <Td right>{fmtInt(x.request_count)}</Td>
                    <Td right className={cx(x.block_count > 0 && "font-semibold text-danger")}>{fmtInt(x.block_count)}</Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
