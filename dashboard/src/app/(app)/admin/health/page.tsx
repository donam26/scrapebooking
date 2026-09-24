"use client";

import { api } from "@/lib/api";
import { useApi, useInterval, useMutation } from "@/lib/hooks";
import { fmtDateTime, fmtDuration, fmtInt, fmtPct } from "@/lib/format";
import { RUN_STATUS_LABEL, RUN_STATUS_TONE, SESSION_STATUS_TONE } from "@/lib/labels";
import type { Tone } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, PageHeader, Skeleton, StatTile, Table, Td, Th } from "@/components/ui";
import { RunSummary } from "@/components/run-summary";

const REFRESH_MS = 30_000;

function blockTone(rate: number): Tone {
  if (rate >= 0.2) return "red";
  if (rate >= 0.1) return "amber";
  return "green";
}

export default function AdminHealthPage() {
  const summary = useApi("health:summary", () => api.health.summary());
  const runs = useApi("health:runs", () => api.health.runs(20));
  const sessions = useApi("health:sessions", () => api.health.sessions(50));
  const reloadAll = () => {
    summary.reload();
    runs.reload();
    sessions.reload();
  };
  useInterval(reloadAll, REFRESH_MS);
  const scanAll = useMutation(async () => {
    const run = await api.health.scanNow();
    reloadAll();
    return run;
  });

  const s = summary.data;
  return (
    <>
      <PageHeader
        title="Sức khoẻ scraper"
        subtitle="Tự làm mới mỗi 30 giây"
        actions={
          <div className="flex items-center gap-3">
            {s?.grafana_url && (
              <a href={s.grafana_url} target="_blank" rel="noreferrer" className="text-sm text-sky-700 hover:underline">
                Mở Grafana ↗
              </a>
            )}
            <Button size="sm" busy={scanAll.busy} onClick={() => void scanAll.run()} title="Tạo đợt quét thủ công cho mọi tenant đang hoạt động">
              Quét tất cả ngay
            </Button>
          </div>
        }
      />
      <ErrorBox error={scanAll.error} className="mb-4" />
      <ErrorBox error={summary.error} className="mb-4" />
      {!s && !summary.error && <Skeleton rows={3} className="mb-4" />}
      {s && (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Probe 15 phút qua" value={fmtInt(s.probes_15m)} />
            <StatTile label="Bị chặn 15 phút qua" value={fmtInt(s.blocked_15m)} tone={s.blocked_15m > 0 ? "amber" : "gray"} />
            <StatTile label="Tỷ lệ chặn 15 phút" value={fmtPct(s.block_rate_15m * 100)} tone={blockTone(s.block_rate_15m)} hint={s.block_rate_15m >= 0.2 ? "Vượt ngưỡng cảnh báo 20%" : "Ngưỡng cảnh báo 20%"} />
            <StatTile label="Session đang hoạt động" value={fmtInt(s.active_sessions)} />
          </div>
          <Card className="mb-4" title="Đợt quét gần nhất" actions={s.pending_analytics_runs.length > 0 && <Badge tone="amber">Chờ analytics: {s.pending_analytics_runs.map((id) => `#${id}`).join(", ")}</Badge>}>
            <RunSummary run={s.last_run} />
          </Card>
        </>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Các đợt quét" padded={false}>
          <ErrorBox error={runs.error} className="m-4" />
          {!runs.data ? (
            !runs.error && <Skeleton rows={5} className="p-4" />
          ) : runs.data.length === 0 ? (
            <div className="p-4">
              <EmptyState>Chưa có đợt quét.</EmptyState>
            </div>
          ) : (
            <Table dense>
              <thead>
                <tr>
                  <Th>ID</Th>
                  <Th>Mốc</Th>
                  <Th>Trạng thái</Th>
                  <Th>Bắt đầu</Th>
                  <Th>Thời lượng</Th>
                  <Th right>Job</Th>
                  <Th right>OK / probe</Th>
                  <Th right>Hết</Th>
                  <Th right>Chặn</Th>
                  <Th right>Lỗi</Th>
                </tr>
              </thead>
              <tbody>
                {runs.data.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <Td className="text-slate-500">#{r.id}</Td>
                    <Td className="font-mono text-xs">{r.trigger_key}</Td>
                    <Td>
                      <Badge tone={RUN_STATUS_TONE[r.status] ?? "gray"}>{RUN_STATUS_LABEL[r.status] ?? r.status}</Badge>
                    </Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(r.started_at ?? r.scheduled_at)}</Td>
                    <Td>{fmtDuration(r.started_at, r.finished_at)}</Td>
                    <Td right>{fmtInt(r.total_jobs)}</Td>
                    <Td right>
                      {fmtInt(r.ok_count)} / {fmtInt(r.total_probes)}
                    </Td>
                    <Td right>{fmtInt(r.sold_out_count)}</Td>
                    <Td right className={r.blocked_count > 0 ? "text-rose-700" : undefined}>
                      {fmtInt(r.blocked_count)}
                    </Td>
                    <Td right className={r.error_count > 0 ? "text-amber-700" : undefined}>
                      {fmtInt(r.error_count)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>

        <Card title="Session scrape" padded={false}>
          <ErrorBox error={sessions.error} className="m-4" />
          {!sessions.data ? (
            !sessions.error && <Skeleton rows={5} className="p-4" />
          ) : sessions.data.length === 0 ? (
            <div className="p-4">
              <EmptyState>Chưa có session.</EmptyState>
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
                {sessions.data.map((x) => (
                  <tr key={x.id} className="hover:bg-slate-50">
                    <Td className="font-mono text-xs" title={x.id}>
                      {x.id.slice(0, 8)}
                    </Td>
                    <Td className="font-mono text-xs">{x.worker_id}</Td>
                    <Td className="font-mono text-xs">{x.proxy_id}</Td>
                    <Td className="uppercase">{x.proxy_country}</Td>
                    <Td>
                      <Badge tone={SESSION_STATUS_TONE[x.status] ?? "gray"}>{x.status}</Badge>
                      {x.retired_at && <div className="text-[11px] text-slate-500">thu hồi {fmtDateTime(x.retired_at)}</div>}
                    </Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(x.created_at)}</Td>
                    <Td className="whitespace-nowrap">{fmtDateTime(x.expires_at)}</Td>
                    <Td right>{fmtInt(x.request_count)}</Td>
                    <Td right className={x.block_count > 0 ? "text-rose-700" : undefined}>
                      {fmtInt(x.block_count)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}
