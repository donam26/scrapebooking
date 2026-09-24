"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { api, type TenantOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtDateTime } from "@/lib/format";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, PageHeader, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";

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

function TenantForm({ initial, submitLabel, showActive, onSubmit, onCancel }: { initial: Draft; submitLabel: string; showActive?: boolean; onSubmit: (d: Draft) => Promise<unknown>; onCancel?: () => void }) {
  const [d, setD] = useState<Draft>(initial);
  const save = useMutation(onSubmit);
  function submit(e: FormEvent) {
    e.preventDefault();
    void save.run(d);
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Tên tenant">
          <Input required maxLength={200} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} />
        </Field>
        <Field label="Múi giờ">
          <Input required value={d.timezone} onChange={(e) => setD({ ...d, timezone: e.target.value })} />
        </Field>
        <Field label="Giờ quét (HH:MM, phẩy)">
          <Input required value={d.scan_times} onChange={(e) => setD({ ...d, scan_times: e.target.value })} />
        </Field>
        <Field label="Horizon (ngày)">
          <Input type="number" min={1} max={90} required value={d.horizon_days} onChange={(e) => setD({ ...d, horizon_days: Number(e.target.value) })} />
        </Field>
        <Field label="Giờ tạo bản tin">
          <Input type="time" required value={d.insight_hour} onChange={(e) => setD({ ...d, insight_hour: e.target.value })} />
        </Field>
        <Field label="Ngôn ngữ bản tin">
          <Select value={d.insight_language} onChange={(e) => setD({ ...d, insight_language: e.target.value })}>
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
          </Select>
        </Field>
        <Field label="Mã nước (2 ký tự)">
          <Input required minLength={2} maxLength={2} value={d.country_code} onChange={(e) => setD({ ...d, country_code: e.target.value.toLowerCase() })} />
        </Field>
        {showActive && (
          <Field label="Trạng thái">
            <Select value={d.active ? "1" : "0"} onChange={(e) => setD({ ...d, active: e.target.value === "1" })}>
              <option value="1">Hoạt động</option>
              <option value="0">Tắt</option>
            </Select>
          </Field>
        )}
      </div>
      <ErrorBox error={save.error} />
      <div className="flex gap-2">
        <Button type="submit" variant="primary" busy={save.busy}>
          {submitLabel}
        </Button>
        {onCancel && <Button onClick={onCancel}>Huỷ</Button>}
      </div>
    </form>
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
  return (
    <>
      <PageHeader title="Tenant" subtitle="Mỗi tenant là một khách hàng với watchlist, lịch quét và người dùng riêng" actions={<Button variant="primary" onClick={() => setShowCreate((v) => !v)}>{showCreate ? "Đóng" : "+ Tạo tenant"}</Button>} />
      {showCreate && (
        <Card title="Tạo tenant mới" className="mb-4">
          <TenantForm
            initial={DEFAULT_DRAFT}
            submitLabel="Tạo"
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
      <Card padded={false}>
        {!list.data && !list.error ? (
          <Skeleton rows={5} className="p-4" />
        ) : rows.length === 0 ? (
          <div className="p-4">
            <EmptyState>Chưa có tenant nào.</EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>ID</Th>
                <Th>Tên</Th>
                <Th>Múi giờ</Th>
                <Th>Giờ quét</Th>
                <Th right>Horizon</Th>
                <Th>Bản tin</Th>
                <Th>Nước</Th>
                <Th>Trạng thái</Th>
                <Th>Tạo lúc</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <TenantRows key={t.id} t={t} editing={editing === t.id} selected={t.id === tenantId} onEdit={() => setEditing(editing === t.id ? null : t.id)} onView={() => { setTenantId(t.id); router.push("/overview"); }} onSaved={async () => { setEditing(null); await afterChange(); }} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function TenantRows({ t, editing, selected, onEdit, onView, onSaved }: { t: TenantOut; editing: boolean; selected: boolean; onEdit: () => void; onView: () => void; onSaved: () => Promise<void> }) {
  return (
    <>
      <tr className={cx("hover:bg-slate-50", selected && "bg-sky-50")}>
        <Td className="text-slate-500">{t.id}</Td>
        <Td className="font-medium">{t.name}</Td>
        <Td>{t.timezone}</Td>
        <Td className="tabular">{t.scan_times.join(", ")}</Td>
        <Td right>{t.horizon_days}</Td>
        <Td>
          {t.insight_hour} · {t.insight_language}
        </Td>
        <Td className="uppercase">{t.country_code}</Td>
        <Td>
          <Badge tone={t.active ? "green" : "gray"}>{t.active ? "Hoạt động" : "Tắt"}</Badge>
        </Td>
        <Td className="whitespace-nowrap text-slate-600">{fmtDateTime(t.created_at)}</Td>
        <Td>
          <div className="flex gap-1.5">
            <Button size="sm" variant="primary" onClick={onView} disabled={selected}>
              {selected ? "Đang xem" : "Xem dashboard"}
            </Button>
            <Button size="sm" onClick={onEdit}>
              {editing ? "Đóng" : "Sửa"}
            </Button>
          </div>
        </Td>
      </tr>
      {editing && (
        <tr>
          <td colSpan={10} className="border-b border-line bg-slate-50 px-4 py-3">
            <TenantForm
              initial={toDraft(t)}
              submitLabel="Lưu"
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
    </>
  );
}
