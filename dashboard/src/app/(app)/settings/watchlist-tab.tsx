"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, type WatchItemOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtDateTime } from "@/lib/format";
import { WATCH_ROLE_LABEL } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";

function AddForm({ onAdded }: { onAdded: () => void }) {
  const [url, setUrl] = useState("");
  const [role, setRole] = useState<"self" | "competitor">("competitor");
  const [label, setLabel] = useState("");
  const add = useMutation(async () => {
    await api.watchlist.add({ booking_url: url.trim(), role, label: label.trim() || null });
    setUrl("");
    setLabel("");
    onAdded();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    void add.run();
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="URL Booking.com" className="min-w-[280px] flex-1">
          <Input type="url" required placeholder="https://www.booking.com/hotel/vn/ten-khach-san.html" value={url} onChange={(e) => setUrl(e.target.value)} />
        </Field>
        <Field label="Vai trò">
          <Select value={role} onChange={(e) => setRole(e.target.value as "self" | "competitor")}>
            <option value="competitor">{WATCH_ROLE_LABEL.competitor}</option>
            <option value="self">{WATCH_ROLE_LABEL.self}</option>
          </Select>
        </Field>
        <Field label="Nhãn (tuỳ chọn)">
          <Input maxLength={120} placeholder="VD: Đối thủ A" value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
        <Button type="submit" variant="primary" busy={add.busy}>
          Thêm khách sạn
        </Button>
      </div>
      <ErrorBox error={add.error} />
    </form>
  );
}

function Row({ item, canWrite, onChanged }: { item: WatchItemOut; canWrite: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(item.label ?? "");
  const [role, setRole] = useState(item.role);
  const save = useMutation(async () => {
    await api.watchlist.update(item.hotel.id, { label: label.trim() || null, role });
    setEditing(false);
    onChanged();
  });
  const toggle = useMutation(async () => {
    if (item.active) await api.watchlist.remove(item.hotel.id);
    else await api.watchlist.update(item.hotel.id, { active: true });
    onChanged();
  });
  const name = item.hotel.name || item.hotel.booking_slug;
  return (
    <>
      <tr className={cx("hover:bg-slate-50", !item.active && "text-slate-400")}>
        <Td>
          <Link href={`/hotels/${item.hotel.id}`} className={cx("font-medium hover:underline", item.active ? "text-sky-700" : "text-slate-500")}>
            {name}
          </Link>
          <div className="text-xs text-slate-500">
            {item.hotel.city ? `${item.hotel.city} · ` : ""}
            <a href={item.hotel.booking_url} target="_blank" rel="noreferrer" className="hover:underline">
              {item.hotel.booking_slug}
            </a>
          </div>
        </Td>
        <Td>{editing ? <Input value={label} maxLength={120} onChange={(e) => setLabel(e.target.value)} /> : item.label || <span className="text-slate-400">—</span>}</Td>
        <Td>
          {editing ? (
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="competitor">{WATCH_ROLE_LABEL.competitor}</option>
              <option value="self">{WATCH_ROLE_LABEL.self}</option>
            </Select>
          ) : (
            <Badge tone={item.role === "self" ? "blue" : "gray"}>{WATCH_ROLE_LABEL[item.role] ?? item.role}</Badge>
          )}
        </Td>
        <Td>
          <Badge tone={item.active ? "green" : "gray"}>{item.active ? "Đang quét" : "Ngừng"}</Badge>
        </Td>
        <Td className="whitespace-nowrap text-slate-600">{fmtDateTime(item.added_at)}</Td>
        {canWrite && (
          <Td>
            <div className="flex flex-wrap gap-1.5">
              {editing ? (
                <>
                  <Button size="sm" variant="primary" busy={save.busy} onClick={() => void save.run()}>
                    Lưu
                  </Button>
                  <Button size="sm" onClick={() => setEditing(false)}>
                    Huỷ
                  </Button>
                </>
              ) : (
                <>
                  <Button size="sm" onClick={() => setEditing(true)}>
                    Sửa
                  </Button>
                  <Button size="sm" variant={item.active ? "danger" : "secondary"} busy={toggle.busy} onClick={() => void toggle.run()}>
                    {item.active ? "Ngừng quét" : "Quét lại"}
                  </Button>
                </>
              )}
            </div>
          </Td>
        )}
      </tr>
      {(save.error || toggle.error) && (
        <tr>
          <td colSpan={canWrite ? 6 : 5} className="px-3 pb-2">
            <ErrorBox error={save.error ?? toggle.error} />
          </td>
        </tr>
      )}
    </>
  );
}

export function WatchlistTab() {
  const { canWrite } = useSession();
  const list = useApi("watchlist:inactive", () => api.watchlist.list(true));
  const items = list.data ?? [];
  return (
    <div className="space-y-4">
      {canWrite && (
        <Card title="Thêm khách sạn theo URL Booking.com">
          <AddForm onAdded={list.reload} />
        </Card>
      )}
      <ErrorBox error={list.error} />
      <Card title={`Danh sách theo dõi (${items.length})`} padded={false}>
        {!list.data && !list.error ? (
          <Skeleton rows={5} className="p-4" />
        ) : items.length === 0 ? (
          <div className="p-4">
            <EmptyState>Chưa có khách sạn nào. Thêm khách sạn của bạn (vai trò “Khách sạn của bạn”) và các đối thủ.</EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Khách sạn</Th>
                <Th>Nhãn</Th>
                <Th>Vai trò</Th>
                <Th>Trạng thái</Th>
                <Th>Thêm lúc</Th>
                {canWrite && <Th />}
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <Row key={it.hotel.id} item={it} canWrite={canWrite} onChanged={list.reload} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
