"use client";

import { useState, type DragEvent, type ReactNode } from "react";
import { api, type PmsImportOut, type PreviewOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { translateError } from "@/lib/errors";
import { fmtDate, fmtDateTime, fmtInt, fmtNum, fmtPct } from "@/lib/format";
import { CANONICAL_PMS_COLUMNS, IMPORT_STATUS_LABEL, IMPORT_STATUS_TONE, PMS_COLUMN_LABEL } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, ROW_CLASS, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconAlert, IconCheck, IconDownload, IconFile, IconUpload } from "@/components/icons";

type RowError = { row?: unknown; column?: unknown; message?: unknown };

function cellText(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${fmtNum(n / 1024, 0)} KB`;
  return `${fmtNum(n / (1024 * 1024), 1)} MB`;
}

function ErrorRows({ errors }: { errors: Record<string, unknown>[] }) {
  if (errors.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-lg border border-line">
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
                <Td right className="w-16 text-muted">
                  {cellText(e.row)}
                </Td>
                <Td className="whitespace-nowrap text-sm">{e.column ? (PMS_COLUMN_LABEL[cellText(e.column)] ?? cellText(e.column)) : "—"}</Td>
                <Td className="text-sm text-danger-deep">{translateError(cellText(e.message))}</Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </div>
  );
}

function ImportResult({ result }: { result: PmsImportOut }) {
  return (
    <div className="space-y-3 rounded-lg bg-subtle p-4">
      <div className="flex flex-wrap items-center gap-3 text-base">
        <Badge tone={IMPORT_STATUS_TONE[result.status] ?? "gray"}>{IMPORT_STATUS_LABEL[result.status] ?? result.status}</Badge>
        <span className="text-body">
          <span className="font-bold text-ink tabular">{fmtInt(result.ok_count)}</span> / <span className="tabular">{fmtInt(result.row_count)}</span> dòng nhập thành công
        </span>
        {result.errors.length > 0 && <span className="text-danger tabular">{fmtInt(result.errors.length)} dòng lỗi</span>}
      </div>
      {result.status !== "failed" && <p className="text-sm text-muted">Công suất đã nhập hiện trên Tổng quan, trong dải khách sạn của bạn.</p>}
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

/** Bước trong quy trình nhập: số thứ tự có nghĩa vì phải làm lần lượt. */
function Step({ n, title, hint, active, children }: { n: number; title: string; hint?: ReactNode; active: boolean; children?: ReactNode }) {
  return (
    <section className={cx("border-t border-line px-5 py-5 first:border-t-0", !active && "bg-subtle/60")}>
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className={cx(
            "grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold tabular",
            active ? "bg-brand text-white" : "bg-sunken text-faint",
          )}
        >
          {n}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className={cx("text-base font-bold", active ? "text-ink" : "text-muted")}>
            <span className="sr-only">Bước {n}: </span>
            {title}
          </h3>
          {hint && <div className="mt-0.5 text-sm text-muted">{hint}</div>}
          {active && children && <div className="mt-4">{children}</div>}
        </div>
      </div>
    </section>
  );
}

function Dropzone({ file, busy, onFile }: { file: File | null; busy: boolean; onFile: (f: File | null) => void }) {
  const [over, setOver] = useState(false);
  function onDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setOver(false);
    const f = e.dataTransfer.files?.[0] ?? null;
    if (f) onFile(f);
  }
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={cx(
        "relative flex min-h-[104px] cursor-pointer items-center gap-4 rounded-xl border-[1.5px] border-dashed px-5 py-4 transition-colors duration-150",
        "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand",
        over ? "border-brand bg-brand-softer" : file ? "border-line-strong bg-surface hover:border-brand-light" : "border-line-strong bg-subtle hover:border-brand-light hover:bg-brand-softer/60",
      )}
    >
      <input
        type="file"
        accept=".csv,.xlsx,.xls,text/csv"
        className="sr-only"
        onChange={(e) => {
          onFile(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
      <span className={cx("grid h-11 w-11 shrink-0 place-items-center rounded-full", file ? "bg-brand-soft text-brand" : "bg-surface text-brand shadow-card")}>
        {file ? <IconFile size={20} /> : <IconUpload size={20} />}
      </span>
      {file ? (
        <span className="min-w-0 flex-1">
          <span className="block truncate text-base font-semibold text-ink" title={file.name}>
            {file.name}
          </span>
          <span className="block text-sm text-muted tabular">
            {fmtBytes(file.size)} · {busy ? "Đang đọc tệp…" : "Bấm hoặc kéo tệp khác vào để đổi"}
          </span>
        </span>
      ) : (
        <span className="min-w-0 flex-1">
          <span className="block text-base font-semibold text-ink">{over ? "Thả tệp vào đây" : "Kéo thả hoặc chọn tệp CSV/Excel"}</span>
          <span className="block text-sm text-muted">Tệp xuất công suất theo ngày từ PMS: CSV, XLSX hoặc XLS</span>
        </span>
      )}
    </label>
  );
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

  function onFile(f: File | null) {
    setFile(f);
    setPreview(null);
    setResult(null);
    doPreview.clearError();
    doImport.clearError();
    if (f) void doPreview.run(f);
  }

  const hotelName = (id: number | null) => {
    if (id === null) return "—";
    const w = (watchlist.data ?? []).find((x) => x.hotel.id === id);
    return w ? w.label || w.hotel.name || w.hotel.booking_slug : `#${id}`;
  };

  const hotelSelect = (
    <Select
      aria-label="Khách sạn của bạn"
      value={effectiveHotelId ?? ""}
      onChange={(e) => setHotelId(e.target.value)}
      disabled={selfHotels.length === 0}
      className="min-w-[220px]"
    >
      {selfHotels.length === 0 && <option value="">Chưa có khách sạn của bạn</option>}
      {selfHotels.map((w) => (
        <option key={w.hotel.id} value={w.hotel.id}>
          {w.label || w.hotel.name || w.hotel.booking_slug}
        </option>
      ))}
    </Select>
  );

  const noSelf = watchlist.data && selfHotels.length === 0;
  const mappedCount = CANONICAL_PMS_COLUMNS.filter((c) => mapping[c]).length;

  return (
    <div className="space-y-5">
      {canWrite && (
        <Card
          padded={false}
          title="Nhập công suất từ PMS"
          description="Tải tệp xuất từ PMS (ezCloud, Newway…) để đặt công suất thật của bạn cạnh tình trạng phòng của đối thủ trên Tổng quan."
          actions={
            <Button size="sm" busy={template.busy} icon={<IconDownload size={15} />} onClick={() => void template.run()}>
              Tải template CSV
            </Button>
          }
        >
          {template.error && <ErrorBox error={template.error} className="mx-5 mt-4" />}
          <Step n={1} title="Chọn khách sạn và tệp" active>
            {noSelf ? (
              <div className="flex items-start gap-2.5 rounded-lg border border-[#f3dc9a] bg-warning-soft px-3.5 py-2.5 text-sm text-warning-deep">
                <IconAlert size={16} className="mt-px shrink-0" />
                <span>
                  Cần thêm khách sạn của bạn (vai trò “Khách sạn của bạn”) ở tab{" "}
                  <a href="/settings?tab=watchlist" className="font-semibold underline">
                    Khách sạn
                  </a>{" "}
                  trước khi nhập PMS.
                </span>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-[minmax(220px,280px)_minmax(0,1fr)] md:items-start">
                <Field label="Khách sạn của bạn" hint="Dữ liệu nhập vào gắn với khách sạn này">
                  {hotelSelect}
                </Field>
                <div className="flex min-w-0 flex-col gap-1.5">
                  <span className="text-sm font-semibold text-body">Tệp dữ liệu</span>
                  <Dropzone file={file} busy={doPreview.busy} onFile={onFile} />
                </div>
              </div>
            )}
            <ErrorBox error={doPreview.error} className="mt-3" title="Không đọc được tệp" />
            {doPreview.busy && <Skeleton rows={2} className="mt-4" />}
          </Step>

          <Step
            n={2}
            title="Ánh xạ cột"
            active={!!preview}
            hint={
              preview
                ? `Chọn cột trong tệp tương ứng với từng cột chuẩn (${mappedCount}/${CANONICAL_PMS_COLUMNS.length} đã chọn). Ánh xạ được lưu và dùng lại cho các lần nhập sau.`
                : "Chọn tệp để hệ thống gợi ý cột tương ứng."
            }
          >
            {preview && (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {CANONICAL_PMS_COLUMNS.map((col) => {
                  const required = col === "stay_date";
                  const missing = required && !mapping[col];
                  return (
                    <Field
                      key={col}
                      label={
                        <span className="flex items-center gap-1.5">
                          {PMS_COLUMN_LABEL[col]}
                          {required && <span className="rounded bg-brand-soft px-1.5 text-2xs font-bold text-brand-hover">Bắt buộc</span>}
                        </span>
                      }
                    >
                      <Select
                        value={mapping[col] ?? ""}
                        onChange={(e) => setMapping({ ...mapping, [col]: e.target.value })}
                        aria-invalid={missing || undefined}
                        className={cx(missing && "border-danger", !mapping[col] && "text-faint")}
                      >
                        <option value="">Bỏ qua</option>
                        {preview.columns.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  );
                })}
              </div>
            )}
          </Step>

          <Step
            n={3}
            title="Xem trước và nhập"
            active={!!preview}
            hint={
              preview ? (
                <>
                  {preview.sample.length} dòng đầu của tệp ·{" "}
                  <span className="font-semibold text-ink tabular">{fmtInt(preview.parsed_ok)}</span> dòng đọc được với ánh xạ đang lưu
                </>
              ) : (
                "Kiểm tra vài dòng đầu trước khi nhập."
              )
            }
          >
            {preview && (
              <div className="space-y-4">
                <div className="overflow-hidden rounded-lg border border-line">
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
                            <Td key={c} className="whitespace-nowrap text-sm tabular">
                              {cellText(row[c])}
                            </Td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
                {preview.errors.length > 0 && (
                  <details className="group rounded-lg border border-line">
                    <summary className="cursor-pointer list-none px-4 py-2.5 text-sm font-semibold text-danger [&::-webkit-details-marker]:hidden">
                      <span className="inline-flex items-center gap-1.5">
                        <IconAlert size={15} /> {preview.errors.length} lỗi khi đọc thử theo ánh xạ đang lưu
                        <span className="font-normal text-muted group-open:hidden">· bấm để xem</span>
                      </span>
                    </summary>
                    <div className="border-t border-line p-3">
                      <ErrorRows errors={preview.errors} />
                    </div>
                  </details>
                )}
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    variant="primary"
                    busy={doImport.busy}
                    icon={<IconUpload size={16} />}
                    disabled={!mapping.stay_date || effectiveHotelId === null}
                    onClick={() => void doImport.run()}
                  >
                    Lưu ánh xạ và nhập dữ liệu
                  </Button>
                  {!mapping.stay_date && <span className="text-sm text-danger">Cần chọn cột cho {PMS_COLUMN_LABEL.stay_date}.</span>}
                  {effectiveHotelId !== null && mapping.stay_date && (
                    <span className="text-sm text-muted">Nhập vào {hotelName(effectiveHotelId)}</span>
                  )}
                </div>
                <ErrorBox error={doImport.error} title="Chưa nhập được" />
                {result && <ImportResult result={result} />}
              </div>
            )}
          </Step>
        </Card>
      )}

      <Card padded={false} title="Lịch sử nhập" description={imports.data && imports.data.length > 0 ? `${imports.data.length} lần nhập gần nhất` : undefined}>
        <ErrorBox error={imports.error} className="m-5" />
        {!imports.data ? (
          !imports.error && <Skeleton rows={3} className="p-5" />
        ) : imports.data.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={<IconFile />} title="Chưa nhập tệp nào" compact>
              Nhập công suất từ PMS để Tổng quan hiện công suất thật của bạn ngay dưới dải phòng còn, cạnh các đối thủ.
            </EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Thời điểm</Th>
                <Th>Tệp</Th>
                <Th>Khách sạn</Th>
                <Th>Trạng thái</Th>
                <Th right>Dòng thành công</Th>
                <Th right>Lỗi</Th>
              </tr>
            </thead>
            <tbody>
              {imports.data.map((im) => (
                <tr key={im.id} className={cx(ROW_CLASS, "align-top")}>
                  <Td className="whitespace-nowrap text-muted tabular">{fmtDateTime(im.created_at)}</Td>
                  <Td className="max-w-[260px]">
                    <span className="flex min-w-0 items-center gap-2">
                      <IconFile size={15} className="shrink-0 text-faint" />
                      <span className="truncate font-medium text-ink" title={im.filename}>
                        {im.filename}
                      </span>
                    </span>
                  </Td>
                  <Td>{hotelName(im.hotel_id)}</Td>
                  <Td>
                    <Badge tone={IMPORT_STATUS_TONE[im.status] ?? "gray"}>{IMPORT_STATUS_LABEL[im.status] ?? im.status}</Badge>
                  </Td>
                  <Td right>
                    {fmtInt(im.ok_count)} / {fmtInt(im.row_count)}
                  </Td>
                  <Td right>
                    {im.errors.length > 0 ? (
                      <details className="text-left">
                        <summary className="cursor-pointer text-right font-semibold text-danger tabular">{im.errors.length}</summary>
                        <div className="mt-2 min-w-[320px]">
                          <ErrorRows errors={im.errors} />
                        </div>
                      </details>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-muted">
                        <IconCheck size={14} /> 0
                      </span>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      <Card
        padded={false}
        title="Công suất đã nhập"
        description={daily.data && daily.data.length > 0 ? `${daily.data.length} đêm gần nhất có dữ liệu` : undefined}
        actions={!canWrite && selfHotels.length > 1 ? hotelSelect : undefined}
      >
        <ErrorBox error={daily.error} className="m-5" />
        {effectiveHotelId === null ? (
          <div className="p-5">
            <EmptyState icon={<IconFile />} title="Chưa có khách sạn của bạn" compact>
              Khi có khách sạn vai trò “Khách sạn của bạn” và tệp PMS đã nhập, công suất từng đêm hiện ở đây.
            </EmptyState>
          </div>
        ) : !daily.data ? (
          !daily.error && <Skeleton rows={4} className="p-5" />
        ) : daily.data.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={<IconFile />} title={`Chưa có dữ liệu cho ${hotelName(effectiveHotelId)}`} compact>
              {canWrite ? "Nhập tệp ở trên; mỗi dòng là một đêm với tổng phòng, phòng đã bán và doanh thu." : "Quản trị viên chưa nhập dữ liệu PMS cho khách sạn này."}
            </EmptyState>
          </div>
        ) : (
          <Table dense>
            <thead>
              <tr>
                <Th>Đêm lưu trú</Th>
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
                  <tr key={`${d.hotel_id}-${stay}`} className={ROW_CLASS}>
                    <Td className="whitespace-nowrap font-medium text-ink tabular">{fmtDate(stay)}</Td>
                    <Td right>{fmtInt(d.rooms_total)}</Td>
                    <Td right>{fmtInt(d.rooms_sold)}</Td>
                    <Td right>{fmtInt(d.rooms_available)}</Td>
                    <Td right className="font-semibold text-ink">
                      {fmtPct(dec(d.occupancy_pct))}
                    </Td>
                    <Td right>{fmtNum(dec(d.adr))}</Td>
                    <Td right>{fmtNum(dec(d.revenue))}</Td>
                    <Td className="text-muted">{d.source}</Td>
                    <Td className="whitespace-nowrap text-muted tabular">{fmtDateTime(d.imported_at)}</Td>
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
