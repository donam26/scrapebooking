"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type DragEvent } from "react";
import { api, type PmsFileKind, type PreviewOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useErrorMessage } from "@/lib/errors";
import { hotelTitle } from "@/lib/hotels";
import { useFmt, type Fmt } from "@/lib/format";
import { CANONICAL_PMS_COLUMNS, IMPORT_STATUS_TONE, useLabel } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, ROW_CLASS, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconAlert, IconCheck, IconDownload, IconFile, IconUpload } from "@/components/icons";

/**
 * Cài đặt › Dữ liệu PMS (UX Phase 3, C4): một ô thả tệp. Hệ thống tự nhận loại tệp theo tên cột
 * (báo cáo công suất theo ngày / phòng đã đặt theo ngày / danh sách đặt phòng), người dùng đổi được
 * nếu nhận sai. Ánh xạ cột chỉ hiện khi thiếu cột bắt buộc (hoặc khi người dùng muốn sửa). Xem trước
 * rồi nhập; kết quả có link tới Lịch giá & phòng (hàng PMS).
 */

const KINDS: readonly PmsFileKind[] = ["daily", "otb_report", "bookings"];

type RowError = { row?: unknown; column?: unknown; message?: unknown };

function cellText(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function fmtBytes(n: number, fmtNum: Fmt["fmtNum"]): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${fmtNum(n / 1024, 0)} KB`;
  return `${fmtNum(n / (1024 * 1024), 1)} MB`;
}

/** Loại tệp của một lần nhập trong lịch sử (cột `adapter`: "csv" = công suất theo ngày). */
function importKind(adapter: string): PmsFileKind {
  return adapter === "otb_report" || adapter === "bookings" ? adapter : "daily";
}

export function ErrorRows({ errors }: { errors: Record<string, unknown>[] }) {
  const t = useTranslations("settings.pms.errors");
  const label = useLabel();
  const errorText = useErrorMessage();
  if (errors.length === 0) return null;
  return (
    <div className="overflow-hidden rounded-lg border border-line">
      <Table dense>
        <thead>
          <tr>
            <Th right>{t("row")}</Th>
            <Th>{t("column")}</Th>
            <Th>{t("error")}</Th>
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
                <Td className="whitespace-nowrap text-sm">{e.column ? label("pmsColumn", cellText(e.column)) : "—"}</Td>
                <Td className="text-sm text-danger-deep">{errorText(cellText(e.message))}</Td>
              </tr>
            );
          })}
        </tbody>
      </Table>
    </div>
  );
}

export function downloadText(filename: string, text: string) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function Dropzone({ file, busy, onFile }: { file: File | null; busy: boolean; onFile: (f: File | null) => void }) {
  const [over, setOver] = useState(false);
  const t = useTranslations("settings.pms.dropzone");
  const { fmtNum } = useFmt();
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
            {fmtBytes(file.size, fmtNum)} · {busy ? t("reading") : t("change")}
          </span>
        </span>
      ) : (
        <span className="min-w-0 flex-1">
          <span className="block text-base font-semibold text-ink">{over ? t("dropHere") : t("pick")}</span>
          <span className="block text-sm text-muted">{t("hint")}</span>
        </span>
      )}
    </label>
  );
}

type Done = { kind: PmsFileKind; status: string; ok: number; total: number; from: string | null; to: string | null; errors: Record<string, unknown>[] };

/** Kết quả nhập: số dòng, khoảng đêm đã có và link tới Lịch giá & phòng. */
function ImportResult({ done }: { done: Done }) {
  const t = useTranslations("settings.pms.result");
  const label = useLabel();
  const { fmtDateShort } = useFmt();
  const range = done.from && done.to ? (done.from === done.to ? fmtDateShort(done.from) : `${fmtDateShort(done.from)}–${fmtDateShort(done.to)}`) : null;
  const calendar = done.from ? `/calendar?view=rooms&start=${done.from}` : "/calendar?view=rooms";
  return (
    <div role="status" className="space-y-3 rounded-lg bg-subtle p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-base">
        <Badge tone={IMPORT_STATUS_TONE[done.status] ?? "gray"}>{label("importStatus", done.status)}</Badge>
        <span className="text-body">
          {t.rich("imported", {
            ok: done.ok,
            total: done.total,
            strong: (c) => <span className="font-bold text-ink tabular">{c}</span>,
            num: (c) => <span className="tabular">{c}</span>,
          })}
        </span>
        {done.errors.length > 0 && <span className="text-danger tabular">{t("failedRows", { count: done.errors.length })}</span>}
      </div>
      {done.status !== "failed" && range && (
        <p className="flex flex-wrap items-center gap-x-1.5 text-sm text-yours-deep">
          <IconCheck size={15} className="shrink-0" />
          <span>
            {t.rich(done.kind === "daily" ? "onCalendar" : "onCalendarOtb", {
              range,
              view: (c) => (
                <Link href={calendar} className="font-semibold underline hover:no-underline">
                  {c}
                </Link>
              ),
              pace: (c) => (
                <Link href="/reports/pace" className="font-semibold underline hover:no-underline">
                  {c}
                </Link>
              ),
            })}
          </span>
        </p>
      )}
      <ErrorRows errors={done.errors} />
    </div>
  );
}

function ImportCard({ hotels, onImported }: { hotels: Array<{ id: number; name: string }>; onImported: () => void }) {
  const t = useTranslations("settings.pms");
  const label = useLabel();
  const [hotelId, setHotelId] = useState<string>("");
  const effectiveHotelId = hotelId ? Number(hotelId) : (hotels[0]?.id ?? null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewOut | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [editMapping, setEditMapping] = useState(false);
  const [asOf, setAsOf] = useState("");
  const [rooms, setRooms] = useState("");
  const [done, setDone] = useState<Done | null>(null);
  const kind: PmsFileKind = preview?.kind ?? "daily";

  const template = useMutation(async () => {
    if (kind === "daily") downloadText("pms-occupancy-template.csv", await api.pms.template());
    else downloadText(kind === "bookings" ? "pms-bookings-template.csv" : "pms-otb-template.csv", await api.pms.otb.template(kind));
  });
  const doPreview = useMutation(async (f: File, force?: PmsFileKind) => {
    setDone(null);
    const p = await api.pms.preview(f, "csv", force ?? null);
    setPreview(p);
    setMapping(p.suggested_mapping);
  });
  const roomsValue = rooms.trim() === "" ? null : Number(rooms);
  const roomsInvalid = roomsValue !== null && !(Number.isInteger(roomsValue) && roomsValue > 0);
  const doImport = useMutation(async () => {
    if (!file || effectiveHotelId === null || !preview) return;
    if (kind === "daily") {
      // Backend đọc ánh xạ đã lưu khi nhập, nên lưu ánh xạ trước rồi mới nhập.
      const clean = Object.fromEntries(Object.entries(mapping).filter(([, v]) => v));
      await api.pms.putMapping({ adapter: "csv", mapping: clean });
      const r = await api.pms.import(file, effectiveHotelId);
      setDone({ kind, status: r.status, ok: r.ok_count, total: r.row_count, from: r.stay_from ?? null, to: r.stay_to ?? null, errors: r.errors });
    } else {
      const r = await api.pms.otb.import({ file, hotelId: effectiveHotelId, kind, asOfDate: kind === "otb_report" ? asOf || null : null, roomsAvailable: roomsValue });
      setDone({ kind, status: r.status, ok: r.snapshots_written, total: r.rows_read, from: r.stay_from ?? null, to: r.stay_to ?? null, errors: r.errors });
    }
    onImported();
  });

  function onFile(f: File | null) {
    setFile(f);
    setPreview(null);
    setDone(null);
    setEditMapping(false);
    doPreview.clearError();
    doImport.clearError();
    if (f) void doPreview.run(f);
  }

  const missing = preview?.missing ?? [];
  const needsMapping = kind === "daily" && (!mapping.stay_date || editMapping);
  const blocked = !preview || effectiveHotelId === null || (kind === "daily" ? !mapping.stay_date : missing.length > 0) || roomsInvalid;
  const hotelName = hotels.find((h) => h.id === effectiveHotelId)?.name ?? "";

  return (
    <Card
      title={t("import.title")}
      description={t("import.description")}
      actions={
        <Button size="sm" busy={template.busy} icon={<IconDownload size={15} />} onClick={() => void template.run()}>
          {t(`import.template.${kind}`)}
        </Button>
      }
    >
      <ErrorBox error={template.error} className="mb-3" />
      {hotels.length === 0 ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-[#fcd34d] bg-warning-soft px-3.5 py-2.5 text-sm text-warning-deep">
          <IconAlert size={16} className="mt-px shrink-0" />
          <span>
            {t.rich("noSelf", {
              link: (c) => (
                <Link href="/settings?tab=watchlist" className="font-semibold underline">
                  {c}
                </Link>
              ),
            })}
          </span>
        </div>
      ) : (
        <div className="space-y-4">
          <div className={cx("grid gap-4", hotels.length > 1 && "md:grid-cols-[minmax(200px,260px)_minmax(0,1fr)] md:items-start")}>
            {hotels.length > 1 && (
              <Field label={t("hotel")} hint={t("hotelHint")}>
                <Select aria-label={t("hotelAria")} value={effectiveHotelId ?? ""} onChange={(e) => setHotelId(e.target.value)}>
                  {hotels.map((h) => (
                    <option key={h.id} value={h.id}>
                      {h.name}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Dropzone file={file} busy={doPreview.busy} onFile={onFile} />
          </div>
          <ErrorBox error={doPreview.error} title={t("previewError")} />
          {doPreview.busy && !preview && <Skeleton rows={2} />}

          {preview && file && (
            <>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-line px-3.5 py-2.5">
                <span className="text-sm text-muted">{t("detected")}</span>
                <Select
                  aria-label={t("kindAria")}
                  value={kind}
                  disabled={doPreview.busy}
                  onChange={(e) => void doPreview.run(file, e.target.value as PmsFileKind)}
                  className="!w-auto min-w-[240px] font-semibold"
                >
                  {KINDS.map((k) => (
                    <option key={k} value={k}>
                      {t(`kinds.${k}.label`)}
                    </option>
                  ))}
                </Select>
                <span className="text-sm text-muted">{preview.kind === preview.detected_kind ? t("detectedAuto") : t("detectedChanged", { kind: t(`kinds.${preview.detected_kind}.label`) })}</span>
                <p className="basis-full text-sm text-body">{t(`kinds.${kind}.body`)}</p>
              </div>

              {kind !== "daily" && missing.length > 0 && (
                <p role="alert" className="flex items-start gap-1.5 text-sm text-danger-deep">
                  <IconAlert size={15} className="mt-0.5 shrink-0" />
                  {t("missingColumns", { columns: missing.map((c) => t(`column.${c as "stay_date"}`)).join(", ") })}
                </p>
              )}

              {needsMapping && (
                <section aria-label={t("mapping.title")} className="rounded-lg border border-line p-3.5">
                  <h3 className="text-sm font-bold text-ink">{t("mapping.title")}</h3>
                  <p className="mt-0.5 text-sm text-muted">{t("mapping.hint")}</p>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {CANONICAL_PMS_COLUMNS.map((col) => {
                      const required = col === "stay_date";
                      const miss = required && !mapping[col];
                      return (
                        <Field
                          key={col}
                          label={
                            <span className="flex items-center gap-1.5">
                              {label("pmsColumn", col)}
                              {required && <span className="rounded bg-brand-soft px-1.5 text-2xs font-bold text-brand-hover">{t("mapping.required")}</span>}
                            </span>
                          }
                        >
                          <Select value={mapping[col] ?? ""} onChange={(e) => setMapping({ ...mapping, [col]: e.target.value })} aria-invalid={miss || undefined} className={cx(miss && "border-danger", !mapping[col] && "text-faint")}>
                            <option value="">{t("mapping.skip")}</option>
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
                </section>
              )}

              {kind !== "daily" && (
                <div className="grid gap-3 sm:grid-cols-2 lg:max-w-[560px]">
                  {kind === "otb_report" && (
                    <Field label={t("asOf")} hint={t("asOfHint")}>
                      <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="tabular" />
                    </Field>
                  )}
                  <Field label={t("rooms")} hint={roomsInvalid ? <span className="text-danger">{t("invalidRooms")}</span> : t("roomsHint")}>
                    <Input type="number" inputMode="numeric" min={1} value={rooms} onChange={(e) => setRooms(e.target.value)} aria-invalid={roomsInvalid || undefined} className="tabular" />
                  </Field>
                </div>
              )}

              <div>
                <p className="mb-2 text-sm text-muted">
                  {t.rich("previewHint", { count: preview.sample.length, parsed: preview.parsed_ok, b: (c) => <span className="font-semibold text-ink tabular">{c}</span> })}
                </p>
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
              </div>
              {preview.errors.length > 0 && (
                <details className="group rounded-lg border border-line">
                  <summary className="cursor-pointer list-none px-4 py-2.5 text-sm font-semibold text-danger [&::-webkit-details-marker]:hidden">
                    <span className="inline-flex items-center gap-1.5">
                      <IconAlert size={15} /> {t("previewErrors", { count: preview.errors.length })}
                      <span className="font-normal text-muted group-open:hidden">{t("clickToView")}</span>
                    </span>
                  </summary>
                  <div className="border-t border-line p-3">
                    <ErrorRows errors={preview.errors} />
                  </div>
                </details>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="primary" busy={doImport.busy} icon={<IconUpload size={16} />} disabled={blocked || doPreview.busy} onClick={() => void doImport.run()}>
                  {t("submit", { count: preview.parsed_ok })}
                </Button>
                {hotelName && <span className="text-sm text-muted">{t("importInto", { hotel: hotelName })}</span>}
                {kind === "daily" && mapping.stay_date && !editMapping && (
                  <button type="button" onClick={() => setEditMapping(true)} className="text-sm font-semibold text-brand hover:underline">
                    {t("mapping.edit")}
                  </button>
                )}
              </div>
              <ErrorBox error={doImport.error} title={t("importError")} />
              {done && <ImportResult done={done} />}
            </>
          )}
        </div>
      )}
    </Card>
  );
}

export function PmsTab() {
  const { canWrite } = useSession();
  const t = useTranslations("settings.pms");
  const label = useLabel();
  const { fmtDate, fmtDateTime, fmtInt, fmtNum, fmtPct } = useFmt();
  const watchlist = useApi("watchlist:active", () => api.watchlist.list(false));
  const selfHotels = (watchlist.data ?? []).filter((w) => w.role === "self");
  const hotels = selfHotels.map((w) => ({ id: w.hotel.id, name: hotelTitle(w.hotel, w.label) }));
  const [dailyHotel, setDailyHotel] = useState<string>("");
  const effectiveHotelId = dailyHotel ? Number(dailyHotel) : (selfHotels[0]?.hotel.id ?? null);

  const imports = useApi("pms:imports", () => api.pms.imports(20));
  const daily = useApi(effectiveHotelId === null ? null : `pms:daily:${effectiveHotelId}`, () => api.pms.daily(effectiveHotelId, 120));

  const hotelName = (id: number | null) => {
    if (id === null) return "—";
    return hotels.find((h) => h.id === id)?.name ?? `#${id}`;
  };

  return (
    <div className="space-y-5">
      {canWrite && watchlist.data && (
        <ImportCard
          hotels={hotels}
          onImported={() => {
            imports.reload();
            daily.reload();
          }}
        />
      )}
      {canWrite && !watchlist.data && !watchlist.error && <Skeleton rows={4} />}

      <Card padded={false} title={t("history.title")} description={imports.data && imports.data.length > 0 ? t("history.description", { count: imports.data.length }) : undefined}>
        <ErrorBox error={imports.error} className="m-5" />
        {!imports.data ? (
          !imports.error && <Skeleton rows={3} className="p-5" />
        ) : imports.data.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={<IconFile />} title={t("history.emptyTitle")} compact>
              {t("history.emptyBody")}
            </EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="pl-5">{t("history.time")}</Th>
                <Th>{t("history.file")}</Th>
                <Th>{t("history.kind")}</Th>
                <Th>{t("history.hotel")}</Th>
                <Th>{t("history.importedBy")}</Th>
                <Th>{t("history.status")}</Th>
                <Th right>{t("history.okRows")}</Th>
                <Th right className="pr-5">
                  {t("history.errors")}
                </Th>
              </tr>
            </thead>
            <tbody>
              {imports.data.map((im) => (
                <tr key={im.id} className={cx(ROW_CLASS, "align-top")}>
                  <Td className="whitespace-nowrap pl-5 text-muted tabular">{fmtDateTime(im.created_at)}</Td>
                  <Td className="max-w-[240px]">
                    <span className="flex min-w-0 items-center gap-2">
                      <IconFile size={15} className="shrink-0 text-faint" />
                      <span className="truncate font-medium text-ink" title={im.filename}>
                        {im.filename}
                      </span>
                    </span>
                  </Td>
                  <Td className="whitespace-nowrap text-body">{t(`kinds.${importKind(im.adapter)}.short`)}</Td>
                  <Td>{hotelName(im.hotel_id)}</Td>
                  <Td className="max-w-[200px]">
                    <span className="block truncate text-body" title={im.created_by_email ?? undefined}>
                      {im.created_by_email ?? "—"}
                    </span>
                  </Td>
                  <Td>
                    <Badge tone={IMPORT_STATUS_TONE[im.status] ?? "gray"}>{label("importStatus", im.status)}</Badge>
                  </Td>
                  <Td right>
                    {fmtInt(im.ok_count)} / {fmtInt(im.row_count)}
                  </Td>
                  <Td right className="pr-5">
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
        title={t("daily.title")}
        description={daily.data && daily.data.length > 0 ? t("daily.description", { count: daily.data.length }) : undefined}
        actions={
          hotels.length > 1 ? (
            <Select aria-label={t("hotelAria")} value={effectiveHotelId ?? ""} onChange={(e) => setDailyHotel(e.target.value)} className="min-w-[220px]">
              {hotels.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
            </Select>
          ) : undefined
        }
      >
        <ErrorBox error={daily.error} className="m-5" />
        {effectiveHotelId === null ? (
          <div className="p-5">
            <EmptyState icon={<IconFile />} title={t("daily.noSelfTitle")} compact>
              {t("daily.noSelfBody")}
            </EmptyState>
          </div>
        ) : !daily.data ? (
          !daily.error && <Skeleton rows={4} className="p-5" />
        ) : daily.data.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={<IconFile />} title={t("daily.noDataTitle", { hotel: hotelName(effectiveHotelId) })} compact>
              {canWrite ? t("daily.noDataWrite") : t("daily.noDataRead")}
            </EmptyState>
          </div>
        ) : (
          <Table dense>
            <thead>
              <tr>
                <Th className="pl-5">{t("daily.stayDate")}</Th>
                <Th right>{t("daily.roomsTotal")}</Th>
                <Th right>{t("daily.roomsSold")}</Th>
                <Th right>{t("daily.roomsLeft")}</Th>
                <Th right>{t("daily.occupancy")}</Th>
                <Th right>{t("daily.adr")}</Th>
                <Th right>{t("daily.revenue")}</Th>
                <Th className="pr-5">{t("daily.importedAt")}</Th>
              </tr>
            </thead>
            <tbody>
              {daily.data.map((d) => {
                const stay = typeof d.stay_date === "string" ? d.stay_date : String(d.stay_date ?? "");
                const dec = (v: unknown) => (typeof v === "string" || typeof v === "number" ? v : null);
                return (
                  <tr key={`${d.hotel_id}-${stay}`} className={ROW_CLASS}>
                    <Td className="whitespace-nowrap pl-5 font-medium text-ink tabular">{fmtDate(stay)}</Td>
                    <Td right>{fmtInt(d.rooms_total)}</Td>
                    <Td right>{fmtInt(d.rooms_sold)}</Td>
                    <Td right>{fmtInt(d.rooms_available)}</Td>
                    <Td right className="font-semibold text-ink">
                      {fmtPct(dec(d.occupancy_pct))}
                    </Td>
                    <Td right>{fmtNum(dec(d.adr))}</Td>
                    <Td right>{fmtNum(dec(d.revenue))}</Td>
                    <Td className="whitespace-nowrap pr-5 text-muted tabular">{fmtDateTime(d.imported_at)}</Td>
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
