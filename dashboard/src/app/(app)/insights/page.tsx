"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtDate, fmtDateTime, fmtInt, fmtNum } from "@/lib/format";
import { INSIGHT_STATUS_LABEL, INSIGHT_STATUS_TONE, INSIGHT_TRIGGER_LABEL } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, PageHeader, Skeleton, Table, Td, Th } from "@/components/ui";

const POLL_MS = 5000;

export default function InsightsPage() {
  const { canWrite } = useSession();
  const list = useApi("insights", () => api.insights.list(50));
  const [pollingId, setPollingId] = useState<number | null>(null);
  const generate = useMutation(async () => {
    const created = await api.insights.generate();
    setPollingId(created.id);
    list.reload();
    return created;
  });

  // Poll GET /insights/{id} mỗi 5s tới khi status != pending, rồi tải lại danh sách.
  const reload = list.reload;
  useEffect(() => {
    if (pollingId === null) return;
    const id = window.setInterval(async () => {
      try {
        const row = await api.insights.get(pollingId);
        if (row.status !== "pending") {
          setPollingId(null);
          reload();
        }
      } catch {
        setPollingId(null);
      }
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [pollingId, reload]);

  const rows = list.data ?? [];
  return (
    <>
      <PageHeader
        title="Bản tin AI"
        subtitle="Bản tin hằng ngày và theo yêu cầu, mọi điểm nổi bật đều dẫn tới số liệu gốc"
        actions={
          canWrite && (
            <Button variant="primary" busy={generate.busy || pollingId !== null} onClick={() => void generate.run()}>
              {pollingId !== null ? "Đang tạo…" : "Tạo bản tin ngay"}
            </Button>
          )
        }
      />
      <ErrorBox error={generate.error} className="mb-4" />
      <ErrorBox error={list.error} className="mb-4" />
      <Card padded={false}>
        {!list.data && !list.error ? (
          <Skeleton rows={6} className="p-4" />
        ) : rows.length === 0 ? (
          <div className="p-4">
            <EmptyState>Chưa có bản tin nào. {canWrite ? "Bấm “Tạo bản tin ngay” để tạo bản đầu tiên." : ""}</EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Tạo lúc</Th>
                <Th>Kỳ dữ liệu</Th>
                <Th>Nguồn</Th>
                <Th>Trạng thái</Th>
                <Th>Mô hình</Th>
                <Th right>Token vào/ra</Th>
                <Th right>Chi phí (USD)</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <Td className="whitespace-nowrap">
                    <Link href={`/insights/${r.id}`} className="font-medium text-sky-700 hover:underline">
                      {fmtDateTime(r.generated_at)}
                    </Link>
                    <span className="ml-1 text-xs text-slate-400">#{r.id}</span>
                  </Td>
                  <Td className="whitespace-nowrap">
                    {fmtDate(r.period_start)} – {fmtDate(r.period_end)}
                  </Td>
                  <Td>{INSIGHT_TRIGGER_LABEL[r.trigger] ?? r.trigger}</Td>
                  <Td>
                    <Badge tone={INSIGHT_STATUS_TONE[r.status] ?? "gray"}>{INSIGHT_STATUS_LABEL[r.status] ?? r.status}</Badge>
                    {r.status === "failed" && r.error && <div className="mt-0.5 max-w-xs truncate text-xs text-rose-700" title={r.error}>{r.error}</div>}
                  </Td>
                  <Td className="text-xs text-slate-600">
                    {r.model} · {r.prompt_version}
                  </Td>
                  <Td right>
                    {fmtInt(r.tokens_in)} / {fmtInt(r.tokens_out)}
                  </Td>
                  <Td right>{fmtNum(r.cost_usd, 4)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
