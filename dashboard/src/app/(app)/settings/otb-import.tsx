"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, type OtbImportKind, type OtbImportOut } from "@/lib/api";
import { useMutation } from "@/lib/hooks";
import { IMPORT_STATUS_TONE, useLabel } from "@/lib/labels";
import { Badge, Button, Card, ErrorBox, Field, Input, Select, cx } from "@/components/ui";
import { IconAlert, IconCheck, IconDownload, IconUpload } from "@/components/icons";
import { Dropzone, ErrorRows, downloadText } from "./pms-tab";

const KINDS: readonly OtbImportKind[] = ["otb_report", "bookings"];

/**
 * Cài đặt › Nhập PMS › OTB theo ngày (roadmap 5.1–5.2): báo cáo phòng đã đặt theo ngày (nhập mỗi
 * ngày, các ngày không ghi đè nhau) hoặc file đặt phòng chi tiết (dựng lại OTB cho cả quá khứ, có
 * pickup/pace/STLY ngay). Chỉ người được ghi thấy khối này.
 */
export function OtbImport({ hotels }: { hotels: Array<{ id: number; name: string }> }) {
  const t = useTranslations("otb.import");
  const label = useLabel();
  const [kind, setKind] = useState<OtbImportKind>("otb_report");
  const [hotelId, setHotelId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [asOf, setAsOf] = useState("");
  const [rooms, setRooms] = useState("");
  const [roomsInvalid, setRoomsInvalid] = useState(false);
  const [result, setResult] = useState<OtbImportOut | null>(null);
  const effectiveHotelId = hotelId ? Number(hotelId) : (hotels[0]?.id ?? null);

  const template = useMutation(async () => downloadText(kind === "bookings" ? "otb-bookings-template.csv" : "otb-report-template.csv", await api.pms.otb.template(kind)));
  const doImport = useMutation(async (roomsAvailable: number | null) => {
    if (!file || effectiveHotelId === null) return;
    setResult(await api.pms.otb.import({ file, hotelId: effectiveHotelId, kind, asOfDate: kind === "otb_report" ? asOf || null : null, roomsAvailable }));
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const raw = rooms.trim();
    const n = raw === "" ? null : Number(raw);
    if (n !== null && !(Number.isInteger(n) && n > 0)) return setRoomsInvalid(true);
    setRoomsInvalid(false);
    void doImport.run(n);
  }

  return (
    <Card
      id="otb"
      title={t("title")}
      description={t("description")}
      actions={
        <Button size="sm" busy={template.busy} icon={<IconDownload size={15} />} onClick={() => void template.run()}>
          {t("template")}
        </Button>
      }
      className="scroll-mt-4"
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
        <form onSubmit={submit} noValidate className="space-y-4">
          <fieldset>
            <legend className="text-sm font-semibold text-body">{t("kindLabel")}</legend>
            <div className="mt-1.5 grid gap-2 md:grid-cols-2">
              {KINDS.map((k) => {
                const on = kind === k;
                return (
                  <label
                    key={k}
                    className={cx(
                      "flex cursor-pointer items-start gap-2.5 rounded-lg border px-3.5 py-3 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand",
                      on ? "border-brand bg-brand-softer" : "border-line hover:border-line-strong",
                    )}
                  >
                    <input
                      type="radio"
                      name="otb-kind"
                      value={k}
                      checked={on}
                      onChange={() => {
                        setKind(k);
                        setResult(null);
                        doImport.clearError();
                      }}
                      className="mt-1 h-4 w-4 shrink-0 accent-brand"
                    />
                    <span className="min-w-0">
                      <span className="block text-base font-semibold text-ink">{t(`kind.${k}.label`)}</span>
                      <span className="mt-0.5 block text-sm text-muted">{t(`kind.${k}.body`)}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div className="grid gap-4 md:grid-cols-[minmax(200px,260px)_minmax(0,1fr)] md:items-start">
            <div className="space-y-3">
              {hotels.length > 1 && (
                <Field label={t("hotel")}>
                  <Select value={effectiveHotelId ?? ""} onChange={(e) => setHotelId(e.target.value)}>
                    {hotels.map((h) => (
                      <option key={h.id} value={h.id}>
                        {h.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {kind === "otb_report" && (
                <Field label={t("asOf")} hint={t("asOfHint")}>
                  <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="tabular" />
                </Field>
              )}
              <Field label={t("rooms")} hint={roomsInvalid ? <span className="text-danger">{t("invalidRooms")}</span> : t("roomsHint")}>
                <Input type="number" inputMode="numeric" min={1} value={rooms} onChange={(e) => setRooms(e.target.value)} aria-invalid={roomsInvalid || undefined} className="tabular" />
              </Field>
            </div>
            <div className="flex min-w-0 flex-col gap-1.5">
              <span className="text-sm font-semibold text-body">{t("file")}</span>
              <Dropzone
                file={file}
                busy={false}
                onFile={(f) => {
                  setFile(f);
                  setResult(null);
                  doImport.clearError();
                }}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" busy={doImport.busy} disabled={!file || effectiveHotelId === null} icon={<IconUpload size={16} />}>
              {t("submit")}
            </Button>
          </div>
          <ErrorBox error={doImport.error} title={t("importError")} />
          {result && (
            <div className="space-y-3 rounded-lg bg-subtle p-4">
              <div className="flex flex-wrap items-center gap-3 text-base">
                <Badge tone={IMPORT_STATUS_TONE[result.status] ?? "gray"}>{label("importStatus", result.status)}</Badge>
                <span className="text-body tabular">
                  {t.rich("result.summary", {
                    rows: result.rows_read,
                    snapshots: result.snapshots_written,
                    asOf: result.as_of_dates,
                    stays: result.stay_dates,
                    b: (c) => <span className="font-bold text-ink">{c}</span>,
                  })}
                </span>
                {result.errors.length > 0 && <span className="text-danger tabular">{t("result.failedRows", { count: result.errors.length })}</span>}
              </div>
              {result.status !== "failed" && result.snapshots_written > 0 && (
                <p className="flex items-center gap-1.5 text-sm text-yours-deep">
                  <IconCheck size={15} className="shrink-0" />
                  <span>
                    {t.rich("result.done", {
                      pace: (c) => (
                        <Link href="/pace" className="font-semibold underline">
                          {c}
                        </Link>
                      ),
                      today: (c) => (
                        <Link href="/today" className="font-semibold underline">
                          {c}
                        </Link>
                      ),
                    })}
                  </span>
                </p>
              )}
              <ErrorRows errors={result.errors} />
            </div>
          )}
        </form>
      )}
    </Card>
  );
}
