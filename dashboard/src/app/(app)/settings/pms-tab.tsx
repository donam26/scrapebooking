"use client";

import { useState, type ChangeEvent } from "react";
import { api, type PmsImportOut, type PreviewOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtDate, fmtDateTime, fmtInt, fmtNum, fmtPct } from "@/lib/format";
import { CANONICAL_PMS_COLUMNS, IMPORT_STATUS_LABEL, IMPORT_STATUS_TONE, PMS_COLUMN_LABEL } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Select, Skeleton, Table, Td, Th } from "@/components/ui";

type RowError = { row?: unknown; column?: unknown; message?: unknown };

function cellText(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function ErrorRows({ errors }: { errors: Record<string, unknown>[] }) {
  if (errors.length === 0) return null;
  return (
    <Table dense>
      <thead>
        <tr>
          <Th right>Dòng</Th>
          <Th>Cột</Th>
          <Th>Lỗi</Th>
        </tr>
      </thead>
      <tbody>
        {errors.map((raw, i) => {
          const e = raw as RowError;
          return (
            <tr key={i}>
              <Td right>{cellText(e.row)}</Td>
              <Td className="font-mono text-xs">{cellText(e.column) || "—"}</Td>
              <Td className="text-rose-700">{cellText(e.message)}</Td>
            </tr>
          );
        })}
      </tbody>
    </Table>
  );
}

function ImportResult({ result }: { result: PmsImportOut }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Badge tone={IMPORT_STATUS_TONE[result.status] ?? "gray"}>{IMPORT_STATUS_LABEL[result.status] ?? result.status}</Badge>
        <span>
          <span className="font-medium">{fmtInt(result.ok_count)}</span> / {fmtInt(result.row_count)} dòng nhập thành công
        </span>
        {result.errors.length > 0 && <span className="text-rose-700">{fmtInt(result.errors.length)} dòng lỗi</span>}
      </div>
      <ErrorRows errors={result.errors} />
    </div>
  );
}

function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function PmsTab() {
  const { canWrite } = useSession();
  const watchlist = useApi("watchlist:active", () => api.watchlist.list(false));
  const selfHotels = (watchlist.data ?? []).filter((w) => w.role === "self");
  const [hotelId, setHotelId] = useState<string>("");
  const effectiveHotelId = hotelId ? Number(hotelId) : (selfHotels[0]?.hotel.id ?? null);

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewOut | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<PmsImportOut | null>(null);

  const imports = useApi("pms:imports", () => api.pms.imports(20));
  const daily = useApi(effectiveHotelId === null ? null : `pms:daily:${effectiveHotelId}`, () => api.pms.daily(effectiveHotelId, 120));

  const template = useMutation(async () => downloadText("pms-template.csv", await api.pms.template()));
  const doPreview = useMutation(async (f: File) => {
    setResult(null);
    const p = await api.pms.preview(f);
    setPreview(p);
    setMapping(p.suggested_mapping);
  });
  const doImport = useMutation(async () => {
    if (!file || effectiveHotelId === null) return;
    // Backend đọc ánh xạ đã lưu khi import, nên lưu ánh xạ trước rồi mới nhập.
    const clean = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v));
    await api.pms.putMapping({ adapter: "csv", mapping: clean });
    const r = await api.pms.import(file, effectiveHotelId);
    setResult(r);
    imports.reload();
    daily.reload();
  });

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setPreview(null);
    setResult(null);
    if (f) void doPreview.run(f);
  }

  const hotelSelect = (
    <Field label="Khách sạn của bạn">
      <Select value={effectiveHotelId ?? ""} onChange={(e) => setHotelId(e.target.value)} disabled={selfHotels.length === 0}>
        {selfHotels.length === 0 && <option value="">Chưa có khách sạn vai trò “Khách sạn của bạn”</option>}
        {selfHotels.map((w) => (
          <option key={w.hotel.id} value={w.hotel.id}>
            {w.label || w.hotel.name || w.hotel.booking_slug}
          </option>
        ))}
      </Select>
    </Field>
  );

  return (
    <div className="space-y-4">
      {canWrite && (
        <Card
          title="Nhập dữ liệu occupancy từ PMS (CSV/Excel)"
          actions={
            <Button size="sm" busy={template.busy} onClick={() => void template.run()}>
              Tải template CSV
            </Button>
          }
        >
          <ErrorBox error={template.error} className="mb-3" />
          <div className="flex flex-wrap items-end gap-3">
            {hotelSelect}
            <Field label="Tệp CSV / Excel">
              <input type="file" accept=".csv,.xlsx,.xls,text/csv" onChange={onFile} className="text-sm file:mr-2 file:rounded file:border file:border-slate-300 file:bg-white file:px-2 file:py-1 file:text-xs" />
            </Field>
          </div>
          {selfHotels.length === 0 && watchlist.data && <p className="mt-2 text-xs text-amber-700">Cần thêm khách sạn của bạn (vai trò “Khách sạn của bạn”) ở tab Watchlist trước khi nhập PMS.</p>}
          <ErrorBox error={doPreview.error} className="mt-3" />
          {doPreview.busy && <Skeleton rows={3} className="mt-3" />}

          {preview && (
            <div className="mt-4 space-y-4">
              <div>
                <h3 className="mb-1 text-sm font-semibold">Ánh xạ cột</h3>
                <p className="mb-2 text-xs text-slate-500">
                  Chọn cột trong tệp tương ứng với từng cột chuẩn. Ánh xạ được lưu theo tenant và dùng cho các lần nhập sau. Bắt buộc: {PMS_COLUMN_LABEL.stay_date}.
                </p>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {CANONICAL_PMS_COLUMNS.map((col) => (
                    <Field key={col} label={PMS_COLUMN_LABEL[col]}>
                      <Select value={mapping[col] ?? ""} onChange={(e) => setMapping({ ...mapping, [col]: e.target.value })}>
                        <option value="">— Bỏ qua —</option>
                        {preview.columns.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="mb-1 text-sm font-semibold">
                  Xem trước ({preview.sample.length} dòng đầu) · {fmtInt(preview.parsed_ok)} dòng đọc được với ánh xạ hiện lưu
                </h3>
                <Table dense>
                  <thead>
                    <tr>
                      {preview.columns.map((c) => (
                        <Th key={c}>{c}</Th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample.map((row, i) => (
                      <tr key={i}>
                        {preview.columns.map((c) => (
                          <Td key={c} className="whitespace-nowrap">
                            {cellText(row[c])}
                          </Td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </Table>
                {preview.errors.length > 0 && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs text-rose-700">{preview.errors.length} lỗi khi đọc thử (theo ánh xạ đang lưu)</summary>
                    <ErrorRows errors={preview.errors} />
                  </details>
                )}
              </div>
              <div className="flex items-center gap-3">
                <Button variant="primary" busy={doImport.busy} disabled={!mapping.stay_date || effectiveHotelId === null} onClick={() => void doImport.run()}>
                  Lưu ánh xạ và nhập dữ liệu
                </Button>
                {!mapping.stay_date && <span className="text-xs text-amber-700">Cần chọn cột cho {PMS_COLUMN_LABEL.stay_date}.</span>}
              </div>
              <ErrorBox error={doImport.error} />
              {result && <ImportResult result={result} />}
            </div>
          )}
        </Card>
      )}

      <Card title="Lịch sử nhập" padded={false}>
        <ErrorBox error={imports.error} className="m-4" />
        {!imports.data ? (
          !imports.error && <Skeleton rows={3} className="p-4" />
        ) : imports.data.length === 0 ? (
          <div className="p-4">
            <EmptyState>Chưa nhập tệp nào.</EmptyState>
          </div>
        ) : (
          <Table dense>
            <thead>
              <tr>
                <Th>Thời điểm</Th>
                <Th>Tệp</Th>
                <Th>Khách sạn</Th>
                <Th>Trạng thái</Th>
                <Th right>OK / tổng</Th>
                <Th right>Lỗi</Th>
              </tr>
            </thead>
            <tbody>
              {imports.data.map((im) => (
                <tr key={im.id} className="hover:bg-slate-50">
                  <Td className="whitespace-nowrap">{fmtDateTime(im.created_at)}</Td>
                  <Td className="max-w-[240px] truncate" title={im.filename}>
                    {im.filename}
                  </Td>
                  <Td>{(watchlist.data ?? []).find((w) => w.hotel.id === im.hotel_id)?.label ?? (im.hotel_id === null ? "—" : `#${im.hotel_id}`)}</Td>
                  <Td>
                    <Badge tone={IMPORT_STATUS_TONE[im.status] ?? "gray"}>{IMPORT_STATUS_LABEL[im.status] ?? im.status}</Badge>
                  </Td>
                  <Td right>
                    {fmtInt(im.ok_count)} / {fmtInt(im.row_count)}
                  </Td>
                  <Td right>
                    {im.errors.length > 0 ? (
                      <details>
                        <summary className="cursor-pointer text-rose-700">{im.errors.length}</summary>
                        <div className="mt-1 text-left">
                          <ErrorRows errors={im.errors} />
                        </div>
                      </details>
                    ) : (
                      "0"
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card title="Dữ liệu occupancy đã nhập" padded={false} actions={!canWrite ? hotelSelect : undefined}>
        <ErrorBox error={daily.error} className="m-4" />
        {effectiveHotelId === null ? (
          <div className="p-4">
            <EmptyState>Chưa có khách sạn của bạn trong watchlist.</EmptyState>
          </div>
        ) : !daily.data ? (
          !daily.error && <Skeleton rows={4} className="p-4" />
        ) : daily.data.length === 0 ? (
          <div className="p-4">
            <EmptyState>Chưa có dữ liệu cho khách sạn này.</EmptyState>
          </div>
        ) : (
          <Table dense>
            <thead>
              <tr>
                <Th>Ngày lưu trú</Th>
                <Th right>Tổng phòng</Th>
                <Th right>Đã bán</Th>
                <Th right>Còn</Th>
                <Th right>Công suất</Th>
                <Th right>ADR</Th>
                <Th right>Doanh thu</Th>
                <Th>Nguồn</Th>
                <Th>Nhập lúc</Th>
              </tr>
            </thead>
            <tbody>
              {daily.data.map((d) => {
                const stay = typeof d.stay_date === "string" ? d.stay_date : String(d.stay_date ?? "");
                const dec = (v: unknown) => (typeof v === "string" || typeof v === "number" ? v : null);
                return (
                  <tr key={`${d.hotel_id}-${stay}`} className="hover:bg-slate-50">
                    <Td className="whitespace-nowrap">{fmtDate(stay)}</Td>
                    <Td right>{fmtInt(d.rooms_total)}</Td>
                    <Td right>{fmtInt(d.rooms_sold)}</Td>
                    <Td right>{fmtInt(d.rooms_available)}</Td>
                    <Td right>{fmtPct(dec(d.occupancy_pct))}</Td>
                    <Td right>{fmtNum(dec(d.adr))}</Td>
                    <Td right>{fmtNum(dec(d.revenue))}</Td>
                    <Td>{d.source}</Td>
                    <Td className="whitespace-nowrap text-slate-600">{fmtDateTime(d.imported_at)}</Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
