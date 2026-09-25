"use client";

import { useRouter } from "next/navigation";
import { Fragment, useState, type FormEvent } from "react";
import { api, type TenantOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, PageHeader, ROW_CLASS, Segmented, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconArrowRight, IconBuilding, IconClose, IconPencil, IconPlus } from "@/components/icons";

type Draft = {
  name: string;
  timezone: string;
  scan_times: string;
  horizon_days: number;
  insight_hour: string;
  insight_language: string;
  country_code: string;
  active: boolean;
};

const DEFAULT_DRAFT: Draft = {
  name: "",
  timezone: "Asia/Ho_Chi_Minh",
  scan_times: "06:00, 14:00, 22:00",
  horizon_days: 30,
  insight_hour: "07:30",
  insight_language: "vi",
  country_code: "vn",
  active: true,
};

const TIMEZONES = ["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore", "Asia/Jakarta", "Asia/Manila", "Asia/Kuala_Lumpur", "Asia/Tokyo", "Europe/London", "UTC"];

const LANGUAGE_LABEL: Record<string, string> = { vi: "Tiếng Việt", en: "English" };

function toDraft(t: TenantOut): Draft {
  return {
    name: t.name,
    timezone: t.timezone,
    scan_times: t.scan_times.join(", "),
    horizon_days: t.horizon_days,
    insight_hour: t.insight_hour,
    insight_language: t.insight_language,
    country_code: t.country_code,
    active: t.active,
  };
}

function parseTimes(s: string): string[] {
  return s
    .split(/[,\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function TenantForm({
  initial,
  submitLabel,
  showActive,
  onSubmit,
  onCancel,
}: {
  initial: Draft;
  submitLabel: string;
  showActive?: boolean;
  onSubmit: (d: Draft) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const [d, setD] = useState<Draft>(initial);
  const save = useMutation(onSubmit);
  const zones = TIMEZONES.includes(d.timezone) ? TIMEZONES : [d.timezone, ...TIMEZONES];
  function submit(e: FormEvent) {
    e.preventDefault();
    void save.run(d);
  }
  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
        <Field label="Tên tenant" hint="Thường là tên khách sạn hoặc tập đoàn khách hàng">
          <Input required maxLength={200} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="VD: Rex Hotel Saigon" />
        </Field>
        <Field label="Múi giờ" hint="Giờ quét và giờ bản tin tính theo múi giờ này">
          <Select required value={d.timezone} onChange={(e) => setD({ ...d, timezone: e.target.value })}>
            {zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Giờ quét trong ngày" hint="HH:MM, cách nhau bằng dấu phẩy. VD: 06:00, 14:00, 22:00">
          <Input required value={d.scan_times} onChange={(e) => setD({ ...d, scan_times: e.target.value })} className="tabular" />
        </Field>
        <Field label="Số đêm quét tới" hint="1–90 đêm kể từ hôm nay">
          <Input type="number" min={1} max={90} required value={d.horizon_days} onChange={(e) => setD({ ...d, horizon_days: Number(e.target.value) })} className="tabular" />
        </Field>
        <Field label="Giờ tạo bản tin AI">
          <Input type="time" required value={d.insight_hour} onChange={(e) => setD({ ...d, insight_hour: e.target.value })} className="tabular" />
        </Field>
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-semibold text-body">Ngôn ngữ bản tin</span>
          <Segmented
            label="Ngôn ngữ bản tin"
            value={d.insight_language}
            onChange={(v) => setD({ ...d, insight_language: v })}
            items={[
              { value: "vi", label: "Tiếng Việt" },
              { value: "en", label: "English" },
            ]}
            className="self-start"
          />
        </div>
        <Field label="Mã nước" hint="2 ký tự, dùng chọn proxy và trang Booking (VD: vn)">
          <Input
            required
            minLength={2}
            maxLength={2}
            value={d.country_code}
            onChange={(e) => setD({ ...d, country_code: e.target.value.toLowerCase() })}
            className="w-24 uppercase"
          />
        </Field>
        {showActive && (
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">Trạng thái</span>
            <Segmented
              label="Trạng thái tenant"
              value={d.active ? "1" : "0"}
              onChange={(v) => setD({ ...d, active: v === "1" })}
              items={[
                { value: "1", label: "Hoạt động" },
                { value: "0", label: "Tắt (không quét)" },
              ]}
              className="self-start"
            />
          </div>
        )}
      </div>
      <ErrorBox error={save.error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={save.busy}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            Huỷ
          </Button>
        )}
      </div>
    </form>
  );
}

function TimeChips({ times }: { times: string[] }) {
  return (
    <div className="flex flex-nowrap gap-1">
      {times.map((t) => (
        <span key={t} className="rounded-md bg-sunken px-1.5 py-0.5 text-xs font-semibold text-body tabular">
          {t}
        </span>
      ))}
    </div>
  );
}

export default function AdminTenantsPage() {
  const router = useRouter();
  const { tenantId, setTenantId, refreshTenants } = useSession();
  const list = useApi("admin:tenants", () => api.tenants.list());
  const [editing, setEditing] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  async function afterChange() {
    list.reload();
    await refreshTenants();
  }

  const rows = list.data ?? [];
  const activeCount = rows.filter((t) => t.active).length;
  return (
    <>
      <PageHeader
        title="Tenant"
        subtitle="Mỗi tenant là một khách hàng với watchlist, lịch quét và người dùng riêng"
        actions={
          <Button
            variant={showCreate ? "secondary" : "primary"}
            icon={showCreate ? <IconClose size={16} /> : <IconPlus size={16} />}
            onClick={() => setShowCreate((v) => !v)}
            aria-expanded={showCreate}
          >
            {showCreate ? "Đóng" : "Tạo tenant"}
          </Button>
        }
      />
      {showCreate && (
        <Card title="Tạo tenant mới" description="Có thể đổi mọi giá trị sau khi tạo" className="mb-6">
          <TenantForm
            initial={DEFAULT_DRAFT}
            submitLabel="Tạo tenant"
            onSubmit={async (d) => {
              await api.tenants.create({
                name: d.name.trim(),
                timezone: d.timezone.trim(),
                scan_times: parseTimes(d.scan_times),
                horizon_days: d.horizon_days,
                insight_hour: d.insight_hour,
                insight_language: d.insight_language,
                country_code: d.country_code,
              });
              setShowCreate(false);
              await afterChange();
            }}
            onCancel={() => setShowCreate(false)}
          />
        </Card>
      )}
      <ErrorBox error={list.error} className="mb-4" />
      <Card
        padded={false}
        title="Danh sách tenant"
        description={list.data ? `${rows.length} tenant · ${activeCount} đang hoạt động` : undefined}
      >
        {!list.data && !list.error ? (
          <Skeleton rows={5} className="p-5" />
        ) : rows.length === 0 ? (
          <div className="p-5">
            <EmptyState
              icon={<IconBuilding />}
              title="Chưa có tenant nào"
              action={
                <Button variant="primary" icon={<IconPlus size={16} />} onClick={() => setShowCreate(true)}>
                  Tạo tenant
                </Button>
              }
            >
              Tạo tenant cho khách hàng đầu tiên, rồi thêm người dùng và watchlist cho họ.
            </EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Tenant</Th>
                <Th>Trạng thái</Th>
                <Th>Giờ quét</Th>
                <Th right>Số đêm</Th>
                <Th>Bản tin</Th>
                <Th className="relative">
                  <span className="sr-only">Thao tác</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <TenantRows
                  key={t.id}
                  t={t}
                  editing={editing === t.id}
                  selected={t.id === tenantId}
                  onEdit={() => setEditing(editing === t.id ? null : t.id)}
                  onView={() => {
                    setTenantId(t.id);
                    router.push("/overview");
                  }}
                  onSaved={async () => {
                    setEditing(null);
                    await afterChange();
                  }}
                />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function TenantRows({
  t,
  editing,
  selected,
  onEdit,
  onView,
  onSaved,
}: {
  t: TenantOut;
  editing: boolean;
  selected: boolean;
  onEdit: () => void;
  onView: () => void;
  onSaved: () => Promise<void>;
}) {
  return (
    <Fragment>
      <tr className={cx(ROW_CLASS, selected && "bg-brand-softer hover:bg-brand-softer", !t.active && "text-muted")}>
        <Td>
          <div className="flex min-w-0 items-center gap-2">
            <span className={cx("truncate font-bold", t.active ? "text-ink" : "text-muted")}>{t.name}</span>
            <span className="shrink-0 rounded bg-sunken px-1.5 py-px text-2xs font-bold uppercase tracking-[0.04em] text-muted">{t.country_code}</span>
          </div>
          <div className="text-xs text-muted tabular" title={`Tạo lúc ${fmtDateTime(t.created_at)}`}>
            #{t.id} · {t.timezone} · tạo {fmtDate(t.created_at.slice(0, 10))}
          </div>
        </Td>
        <Td>
          <Badge tone={t.active ? "green" : "gray"}>{t.active ? "Hoạt động" : "Tắt"}</Badge>
        </Td>
        <Td>
          <TimeChips times={t.scan_times} />
        </Td>
        <Td right className="whitespace-nowrap">
          {t.horizon_days} đêm
        </Td>
        <Td className="whitespace-nowrap">
          <span className="tabular">{t.insight_hour}</span>
          <span className="text-muted"> · {LANGUAGE_LABEL[t.insight_language] ?? t.insight_language}</span>
        </Td>
        <Td>
          <div className="flex justify-end gap-1">
            <Button size="sm" variant="quiet" onClick={onView} disabled={selected} icon={selected ? undefined : <IconArrowRight size={14} />} title="Chuyển sang xem dữ liệu của tenant này">
              {selected ? "Đang xem" : "Xem dashboard"}
            </Button>
            <Button size="sm" variant="ghost" onClick={onEdit} aria-expanded={editing} icon={editing ? <IconClose size={14} /> : <IconPencil size={14} />}>
              {editing ? "Đóng" : "Sửa"}
            </Button>
          </div>
        </Td>
      </tr>
      {editing && (
        <tr>
          <td colSpan={6} className="border-b border-line bg-subtle px-5 py-5">
            <div className="mb-4 text-md font-bold text-ink">Sửa “{t.name}”</div>
            <TenantForm
              initial={toDraft(t)}
              submitLabel="Lưu thay đổi"
              showActive
              onSubmit={async (d) => {
                await api.tenants.update(t.id, {
                  name: d.name.trim(),
                  timezone: d.timezone.trim(),
                  scan_times: parseTimes(d.scan_times),
                  horizon_days: d.horizon_days,
                  insight_hour: d.insight_hour,
                  insight_language: d.insight_language,
                  country_code: d.country_code,
                  active: d.active,
                });
                await onSaved();
              }}
              onCancel={onEdit}
            />
          </td>
        </tr>
      )}
    </Fragment>
  );
}
