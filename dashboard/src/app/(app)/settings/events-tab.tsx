"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { SOURCE_MARKETS, api, type LocalEventIn, type LocalEventOut, type SourceMarket } from "@/lib/api";
import { useApi, useMutation, useTenantToday } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { addDays, useFmt } from "@/lib/format";
import { LOCAL_EVENT_CATEGORIES, fmtUplift, localEventCategory, useLocalEventLabel, type LocalEventCategory } from "@/lib/local-events";
import { Button, Card, EmptyState, ErrorBox, Field, Input, Select, Skeleton, Textarea, cx } from "@/components/ui";
import { IconCalendar, IconCheck, IconPencil, IconPlus, IconTrash } from "@/components/icons";

/**
 * Cài đặt › Sự kiện: sự kiện địa phương ảnh hưởng tới cầu (lễ hội, hội nghị, giải đấu, mùa du lịch)
 * hiện trên lịch Terminal+ cạnh ngày lễ. "% tăng cầu" là mức bạn dự kiến, không phải số đo được.
 */

type Draft = { name: string; category: LocalEventCategory; start_date: string; end_date: string; uplift: string; note: string };

function emptyDraft(today: string): Draft {
  return { name: "", category: "festival", start_date: today, end_date: today, uplift: "", note: "" };
}

function toBody(d: Draft): LocalEventIn {
  const up = d.uplift.trim() === "" ? null : Number(d.uplift);
  return {
    name: d.name.trim(),
    category: d.category,
    start_date: d.start_date,
    end_date: d.end_date,
    expected_uplift_pct: up !== null && Number.isFinite(up) ? Math.round(up) : null,
    note: d.note.trim() || null,
  };
}

function EventForm({ initial, onSaved, onCancel, editId }: { initial: Draft; onSaved: () => void; onCancel?: () => void; editId?: number }) {
  const [d, setD] = useState<Draft>(initial);
  const t = useTranslations("settings.events.form");
  const tc = useTranslations("common.actions");
  const catLabel = useLocalEventLabel();
  const save = useMutation(async () => {
    const body = toBody(d);
    if (editId) await api.market.events.update(editId, body);
    else await api.market.events.create(body);
    onSaved();
    if (!editId) setD(emptyDraft(initial.start_date));
  });
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((prev) => ({ ...prev, [k]: v }));
  return (
    <form
      className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_110px]"
      onSubmit={(e) => {
        e.preventDefault();
        void save.run();
      }}
    >
      <Field label={t("name")} htmlFor={`ev-name-${editId ?? "new"}`}>
        <Input id={`ev-name-${editId ?? "new"}`} required maxLength={200} value={d.name} onChange={(e) => set("name", e.target.value)} placeholder={t("namePlaceholder")} />
      </Field>
      <Field label={t("category")} htmlFor={`ev-cat-${editId ?? "new"}`}>
        <Select id={`ev-cat-${editId ?? "new"}`} value={d.category} onChange={(e) => set("category", e.target.value as LocalEventCategory)}>
          {LOCAL_EVENT_CATEGORIES.map((c) => (
            <option key={c.value} value={c.value}>
              {catLabel(c.value)}
            </option>
          ))}
        </Select>
      </Field>
      <Field label={t("start")} htmlFor={`ev-start-${editId ?? "new"}`}>
        <Input
          id={`ev-start-${editId ?? "new"}`}
          type="date"
          required
          value={d.start_date}
          onChange={(e) => setD((prev) => ({ ...prev, start_date: e.target.value, end_date: prev.end_date < e.target.value ? e.target.value : prev.end_date }))}
        />
      </Field>
      <Field label={t("end")} htmlFor={`ev-end-${editId ?? "new"}`}>
        <Input id={`ev-end-${editId ?? "new"}`} type="date" required min={d.start_date} value={d.end_date} onChange={(e) => set("end_date", e.target.value)} />
      </Field>
      <Field label={t("uplift")} htmlFor={`ev-up-${editId ?? "new"}`} hint={t("upliftHint")}>
        <Input id={`ev-up-${editId ?? "new"}`} type="number" min={-50} max={300} step={5} value={d.uplift} onChange={(e) => set("uplift", e.target.value)} placeholder="+20" />
      </Field>
      <Field label={t("note")} htmlFor={`ev-note-${editId ?? "new"}`} className="sm:col-span-2 lg:col-span-4">
        <Textarea id={`ev-note-${editId ?? "new"}`} rows={2} maxLength={1000} value={d.note} onChange={(e) => set("note", e.target.value)} placeholder={t("notePlaceholder")} />
      </Field>
      <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-1">
        <Button type="submit" variant="primary" busy={save.busy} icon={editId ? undefined : <IconPlus size={16} />} className="w-full">
          {editId ? tc("save") : tc("add")}
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            {tc("cancel")}
          </Button>
        )}
      </div>
      {save.error && <ErrorBox error={save.error} className="sm:col-span-2 lg:col-span-5" />}
    </form>
  );
}

function EventRow({ ev, canWrite, onChanged }: { ev: LocalEventOut; canWrite: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const t = useTranslations("settings.events");
  const tc = useTranslations("common.actions");
  const catLabel = useLocalEventLabel();
  const { fmtDate } = useFmt();
  const del = useMutation(async () => {
    await api.market.events.remove(ev.id);
    onChanged();
  });
  const cat = localEventCategory(ev.category);
  const up = fmtUplift(ev.expected_uplift_pct);
  if (editing) {
    return (
      <li className="py-4">
        <EventForm
          editId={ev.id}
          initial={{ name: ev.name, category: ev.category as LocalEventCategory, start_date: ev.start_date, end_date: ev.end_date, uplift: ev.expected_uplift_pct?.toString() ?? "", note: ev.note ?? "" }}
          onSaved={() => {
            setEditing(false);
            onChanged();
          }}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
      <span aria-hidden className="h-9 w-1.5 shrink-0 rounded-full" style={{ background: cat.bg }} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-ink">{ev.name}</span>
          <span className={cx("rounded-md px-2 py-0.5 text-xs font-semibold", cat.chip)}>{catLabel(ev.category)}</span>
          {up && <span className="rounded-md bg-hot-soft px-2 py-0.5 text-xs font-bold text-hot tabular">{t("uplift", { value: up })}</span>}
        </div>
        <div className="text-sm text-muted tabular">
          {fmtDate(ev.start_date)}
          {ev.end_date !== ev.start_date && ` – ${fmtDate(ev.end_date)}`}
          {ev.note && <span className="ml-2 text-body">· {ev.note}</span>}
        </div>
      </div>
      {canWrite && (
        <div className="flex items-center gap-1">
          <Button size="sm" variant="ghost" icon={<IconPencil size={15} />} onClick={() => setEditing(true)}>
            {tc("edit")}
          </Button>
          <Button size="sm" variant="danger" busy={del.busy} icon={<IconTrash size={15} />} onClick={() => void del.run()} aria-label={t("deleteAria", { name: ev.name })}>
            {tc("delete")}
          </Button>
        </div>
      )}
      {del.error && <ErrorBox error={del.error} className="w-full" />}
    </li>
  );
}

/**
 * Thị trường nguồn khách (roadmap 7.5): kỳ nghỉ của các nước này hiện trên lịch cạnh ngày lễ Việt
 * Nam. Lưu qua PATCH /settings {source_markets}.
 */
function SourceMarkets({ canWrite }: { canWrite: boolean }) {
  const t = useTranslations("settings.events.sourceMarkets");
  const settings = useApi("settings", () => api.settings.get());
  const stored = settings.data?.source_markets ?? null;
  const [draft, setDraft] = useState<string[] | null>(null);
  const [saved, setSaved] = useState(false);
  const selected = draft ?? stored ?? [];
  const dirty = draft !== null && stored !== null && [...draft].sort().join() !== [...stored].sort().join();
  const save = useMutation(async () => {
    await api.settings.update({ source_markets: SOURCE_MARKETS.filter((m) => selected.includes(m)) });
    setDraft(null);
    setSaved(true);
    settings.reload();
  });
  const toggle = (m: SourceMarket) => {
    setSaved(false);
    setDraft(selected.includes(m) ? selected.filter((x) => x !== m) : [...selected, m]);
  };
  return (
    <Card
      title={t("title")}
      description={t("description")}
      info={t("info")}
      actions={
        canWrite &&
        (dirty ? (
          <Button size="sm" variant="primary" busy={save.busy} onClick={() => void save.run()}>
            {t("save")}
          </Button>
        ) : (
          saved && (
            <span role="status" className="inline-flex h-8 items-center gap-1 text-sm text-yours-deep">
              <IconCheck size={15} /> {t("saved")}
            </span>
          )
        ))
      }
    >
      <ErrorBox error={settings.error ?? save.error} className="mb-3" />
      {!settings.data && !settings.error ? (
        <Skeleton rows={2} />
      ) : (
        <>
          <div role="group" aria-label={t("title")} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {SOURCE_MARKETS.map((m) => {
              const on = selected.includes(m);
              return (
                <label
                  key={m}
                  className={cx(
                    "flex min-w-0 items-start gap-2.5 rounded-lg border px-3 py-2.5 transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand",
                    canWrite ? "cursor-pointer" : "cursor-default",
                    on ? "border-brand bg-brand-softer" : "border-line bg-surface hover:border-line-strong",
                  )}
                >
                  <input type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 accent-brand" checked={on} disabled={!canWrite} onChange={() => toggle(m)} />
                  <span className="min-w-0">
                    <span className={cx("block text-sm font-semibold", on ? "text-ink" : "text-body")}>{t(`market.${m}`)}</span>
                    <span className="block text-xs text-muted">{t(`examples.${m}`)}</span>
                  </span>
                </label>
              );
            })}
          </div>
          <p className="mt-3 text-sm text-muted">{selected.length ? t("selected", { count: selected.length }) : t("none")}</p>
          {!canWrite && <p className="mt-1 text-xs text-muted">{t("readOnly")}</p>}
        </>
      )}
    </Card>
  );
}

export function EventsTab() {
  const today = useTenantToday();
  const { canWrite } = useSession();
  const t = useTranslations("settings.events");
  const events = useApi(today && `settings:events:${today}`, () => api.market.events.list({ start: addDays(today!, -30), end: addDays(today!, 365) }));
  if (!today) return <Skeleton />;
  return (
    <div className="space-y-5">
      <SourceMarkets canWrite={canWrite} />
      {canWrite && (
        <Card title={t("addTitle")} icon={<IconCalendar size={16} />} info={t("addInfo")}>
          <EventForm initial={emptyDraft(today)} onSaved={events.reload} />
        </Card>
      )}
      <Card title={t("listTitle")} description={t("listDescription")}>
        <ErrorBox error={events.error} />
        {!events.data && !events.error && <Skeleton rows={3} />}
        {events.data && events.data.length === 0 && (
          <EmptyState icon={<IconCalendar />} title={t("emptyTitle")} compact>
            {t("emptyBody")}
          </EmptyState>
        )}
        {events.data && events.data.length > 0 && (
          <ul className="divide-y divide-line">
            {events.data.map((ev) => (
              <EventRow key={ev.id} ev={ev} canWrite={canWrite} onChanged={events.reload} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
