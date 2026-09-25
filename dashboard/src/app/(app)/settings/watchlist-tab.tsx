"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, type ScanRunOut, type WatchItemOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { fmtDateTime, fmtInt } from "@/lib/format";
import { WATCH_ROLE_LABEL } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Note, ROW_CLASS, Segmented, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconBuilding, IconCheck, IconClock, IconExternal, IconLink, IconPause, IconPencil, IconPlay, IconPlus, IconRefresh } from "@/components/icons";

type Role = "self" | "competitor";

const ROLE_ITEMS: Array<{ value: Role; label: string }> = [
  { value: "competitor", label: WATCH_ROLE_LABEL.competitor },
  { value: "self", label: WATCH_ROLE_LABEL.self },
];

/** Kiểm tra sơ bộ phía trình duyệt: đường dẫn trang khách sạn trên booking.com. */
function bookingUrlProblem(raw: string): string | null {
  const v = raw.trim();
  if (!v) return "Dán đường dẫn trang khách sạn trên Booking.com.";
  let u: URL;
  try {
    u = new URL(v);
  } catch {
    return "Đường dẫn chưa đúng dạng. Hãy sao chép nguyên địa chỉ trên thanh trình duyệt, bắt đầu bằng https://";
  }
  const host = u.hostname.toLowerCase();
  if (host !== "booking.com" && !host.endsWith(".booking.com")) return "Đây không phải đường dẫn Booking.com. Hệ thống chỉ theo dõi khách sạn trên Booking.com.";
  if (!/\/hotel\/[a-z]{2}\/[^/]+/i.test(u.pathname)) return "Đường dẫn cần là trang của một khách sạn, dạng booking.com/hotel/vn/ten-khach-san.html";
  return null;
}

function AddForm({ onAdded, hasSelf }: { onAdded: () => void; hasSelf: boolean }) {
  const [url, setUrl] = useState("");
  const [role, setRole] = useState<Role>(hasSelf ? "competitor" : "self");
  const [label, setLabel] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [added, setAdded] = useState<string | null>(null);
  const add = useMutation(async () => {
    const item = await api.watchlist.add({ booking_url: url.trim(), role, label: label.trim() || null });
    setAdded(item.label || item.hotel.name || item.hotel.booking_slug);
    setUrl("");
    setLabel("");
    onAdded();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    const p = bookingUrlProblem(url);
    setProblem(p);
    setAdded(null);
    if (!p) void add.run();
  }
  return (
    <Card title="Thêm khách sạn" description="Dán đường dẫn trang khách sạn trên Booking.com. Lượt quét kế tiếp sẽ bắt đầu đếm phòng và giá.">
      <form onSubmit={submit} noValidate className="space-y-3">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto] lg:grid-cols-[minmax(0,1fr)_auto_200px_auto] lg:items-end">
          <Field label="Đường dẫn Booking.com" htmlFor="wl-url">
            <div className="relative">
              <IconLink size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <Input
                id="wl-url"
                type="url"
                inputMode="url"
                autoComplete="off"
                placeholder="https://www.booking.com/hotel/vn/ten-khach-san.html"
                value={url}
                aria-invalid={problem ? true : undefined}
                aria-describedby={problem ? "wl-url-problem" : undefined}
                onChange={(e) => {
                  setUrl(e.target.value);
                  if (problem) setProblem(null);
                }}
                className={cx("pl-9", problem && "border-danger focus:border-danger focus:ring-danger/15")}
              />
            </div>
          </Field>
          <div className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-semibold text-body">Vai trò</span>
            <Segmented label="Vai trò" value={role} onChange={setRole} items={ROLE_ITEMS} className="self-start" />
          </div>
          <Field label="Nhãn hiển thị (tuỳ chọn)" htmlFor="wl-label">
            <Input id="wl-label" maxLength={120} placeholder="VD: Đối thủ A" value={label} onChange={(e) => setLabel(e.target.value)} />
          </Field>
          <Button type="submit" variant="primary" busy={add.busy} icon={<IconPlus size={16} />} className="md:col-span-2 md:justify-self-start lg:col-span-1">
            Thêm khách sạn
          </Button>
        </div>
        {problem && (
          <p id="wl-url-problem" role="alert" className="text-sm text-danger">
            {problem}
          </p>
        )}
        <ErrorBox error={add.error} title="Chưa thêm được khách sạn" />
        {added && !add.error && (
          <p role="status" className="flex items-center gap-1.5 text-sm text-yours-deep">
            <IconCheck size={16} /> Đã thêm “{added}”. Số liệu xuất hiện sau lượt quét kế tiếp.
          </p>
        )}
      </form>
    </Card>
  );
}

function Row({ item, canWrite, onChanged }: { item: WatchItemOut; canWrite: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [label, setLabel] = useState(item.label ?? "");
  const [role, setRole] = useState<string>(item.role);
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
  const pending = !item.hotel.name;
  const cols = canWrite ? 5 : 4;
  const editFields = (
    <div className="flex min-w-[200px] flex-col gap-2">
      <Input aria-label="Nhãn hiển thị" value={label} maxLength={120} placeholder="Nhãn hiển thị" onChange={(e) => setLabel(e.target.value)} />
      <Select aria-label="Vai trò" value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="competitor">{WATCH_ROLE_LABEL.competitor}</option>
        <option value="self">{WATCH_ROLE_LABEL.self}</option>
      </Select>
    </div>
  );
  return (
    <>
      <tr className={cx(ROW_CLASS, !item.active && "text-faint")}>
        <Td>
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="min-w-0">
              <Link
                href={`/hotels/${item.hotel.id}`}
                className={cx("block max-w-[200px] truncate font-semibold hover:text-brand hover:underline sm:max-w-[340px]", item.active ? "text-ink" : "text-muted")}
                title={item.hotel.name ?? item.hotel.booking_slug}
              >
                {name}
              </Link>
              <div className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted">
                {item.hotel.city && <span>{item.hotel.city} ·</span>}
                <a
                  href={item.hotel.booking_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-w-0 items-center gap-1 rounded-sm hover:text-brand hover:underline"
                  title="Mở trang trên Booking.com"
                >
                  <span className="max-w-[150px] truncate sm:max-w-none">{item.hotel.booking_slug}</span>
                  <IconExternal size={12} />
                </a>
                {item.label && !editing && <span className="basis-full text-body md:hidden">Nhãn: {item.label}</span>}
                {pending && item.active && (
                  <span className="inline-flex items-center gap-1 text-warning-deep">
                    · <IconClock size={12} /> Chờ lượt quét đầu tiên
                  </span>
                )}
              </div>
              <div className="mt-1 sm:hidden">
                <Badge tone={item.active ? "green" : "gray"}>{item.active ? "Đang quét" : "Ngừng"}</Badge>
              </div>
              {editing && <div className="mt-2 md:hidden">{editFields}</div>}
            </div>
          </div>
        </Td>
        <Td className="hidden whitespace-nowrap md:table-cell">
          {editing ? (
            editFields
          ) : (
            item.label || <span className="text-faint">Chưa đặt</span>
          )}
        </Td>
        <Td className="hidden sm:table-cell">
          <Badge tone={item.active ? "green" : "gray"}>{item.active ? "Đang quét" : "Ngừng"}</Badge>
        </Td>
        <Td className="hidden whitespace-nowrap text-muted tabular md:table-cell">{fmtDateTime(item.added_at)}</Td>
        {canWrite && (
          <Td className="w-0 whitespace-nowrap">
            <div className="flex justify-end gap-1">
              {editing ? (
                <>
                  <Button size="sm" variant="primary" busy={save.busy} onClick={() => void save.run()}>
                    Lưu
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setEditing(false);
                      setLabel(item.label ?? "");
                      setRole(item.role);
                      save.clearError();
                    }}
                  >
                    Huỷ
                  </Button>
                </>
              ) : (
                <>
                  <Button size="sm" variant="ghost" icon={<IconPencil size={15} />} onClick={() => setEditing(true)} aria-label={`Sửa ${name}`}>
                    <span className="hidden sm:inline">Sửa</span>
                  </Button>
                  <Button
                    size="sm"
                    variant={item.active ? "ghost" : "quiet"}
                    busy={toggle.busy}
                    icon={item.active ? <IconPause size={15} /> : <IconPlay size={15} />}
                    onClick={() => void toggle.run()}
                    title={item.active ? "Ngừng quét khách sạn này (có thể bật lại bất cứ lúc nào)" : "Bật quét lại khách sạn này"}
                    aria-label={`${item.active ? "Ngừng quét" : "Quét lại"} ${name}`}
                  >
                    <span className="hidden sm:inline">{item.active ? "Ngừng quét" : "Quét lại"}</span>
                  </Button>
                </>
              )}
            </div>
          </Td>
        )}
      </tr>
      {(save.error || toggle.error) && (
        <tr>
          <td colSpan={cols} className="border-b border-line px-4 pb-3">
            <ErrorBox error={save.error ?? toggle.error} />
          </td>
        </tr>
      )}
    </>
  );
}

function Group({
  title,
  items,
  canWrite,
  onChanged,
  empty,
  self,
}: {
  title: string;
  items: WatchItemOut[];
  canWrite: boolean;
  onChanged: () => void;
  empty: string;
  self?: boolean;
}) {
  return (
    <section>
      <h3 className="flex items-center gap-2 px-5 pb-2 pt-4 text-base font-bold text-ink">
        {self && <span aria-hidden className="h-2 w-2 rounded-full bg-yours" />}
        {title}
        <span className="rounded-full bg-sunken px-1.5 text-xs font-semibold text-muted tabular">{items.length}</span>
      </h3>
      {items.length === 0 ? (
        <p className="mx-5 mb-4 rounded-lg bg-subtle px-4 py-3 text-sm text-muted">{empty}</p>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Khách sạn</Th>
              <Th className="hidden w-[180px] md:table-cell">Nhãn</Th>
              <Th className="hidden w-[130px] sm:table-cell">Trạng thái</Th>
              <Th className="hidden w-[170px] md:table-cell">Thêm lúc</Th>
              {canWrite && (
                <Th right className="sm:w-[210px]">
                  <span className="relative">
                    <span className="sr-only">Thao tác</span>
                  </span>
                </Th>
              )}
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <Row key={it.hotel.id} item={it} canWrite={canWrite} onChanged={onChanged} />
            ))}
          </tbody>
        </Table>
      )}
    </section>
  );
}

export function WatchlistTab() {
  const { canWrite } = useSession();
  const list = useApi("watchlist:inactive", () => api.watchlist.list(true));
  const items = list.data ?? [];
  const selfItems = items.filter((it) => it.role === "self");
  const compItems = items.filter((it) => it.role !== "self");
  const activeCount = items.filter((it) => it.active).length;
  const [run, setRun] = useState<ScanRunOut | null>(null);
  const scan = useMutation(async () => setRun(await api.watchlist.scanNow()));

  return (
    <div className="space-y-5">
      {canWrite && list.data && <AddForm onAdded={list.reload} hasSelf={selfItems.length > 0} />}
      <ErrorBox error={list.error} />
      {!list.data && !list.error ? (
        <Card>
          <Skeleton rows={5} />
        </Card>
      ) : list.data && items.length === 0 ? (
        <EmptyState icon={<IconBuilding />} title="Chưa theo dõi khách sạn nào" className="border border-line bg-surface">
          {canWrite
            ? "Thêm khách sạn của bạn trước (vai trò “Khách sạn của bạn”), sau đó thêm các đối thủ trong cùng phân khúc. Mỗi khách sạn được đếm phòng và giá ba lần mỗi ngày."
            : "Quản trị viên chưa thêm khách sạn nào để theo dõi."}
        </EmptyState>
      ) : (
        list.data && (
          <Card
            padded={false}
            title="Danh sách theo dõi"
            description={`${fmtInt(items.length)} khách sạn, ${fmtInt(activeCount)} đang được quét`}
            actions={
              canWrite ? (
                <Button
                  size="sm"
                  busy={scan.busy}
                  disabled={activeCount === 0}
                  icon={<IconRefresh size={15} />}
                  onClick={() => void scan.run()}
                  title="Quét toàn bộ khách sạn đang theo dõi ngay, không chờ mốc giờ"
                >
                  Quét ngay
                </Button>
              ) : undefined
            }
          >
            {(run || scan.error) && (
              <div className="px-5 pt-4">
                {run && (
                  <Note tone="info" icon={<IconCheck size={16} />}>
                    Đã tạo lượt quét #{run.id} cho {fmtInt(run.total_jobs)} khách sạn. Kết quả xuất hiện ở Tổng quan sau vài phút.
                  </Note>
                )}
                <ErrorBox error={scan.error} title="Chưa quét được" />
              </div>
            )}
            <Group
              self
              title="Khách sạn của bạn"
              items={selfItems}
              canWrite={canWrite}
              onChanged={list.reload}
              empty="Chưa có khách sạn của bạn. Thêm với vai trò “Khách sạn của bạn” để so giá với đối thủ và nhập dữ liệu PMS."
            />
            <div className="border-t border-line">
              <Group
                title="Đối thủ"
                items={compItems}
                canWrite={canWrite}
                onChanged={list.reload}
                empty="Chưa có đối thủ nào. Thêm các khách sạn cùng phân khúc mà bạn hay so giá."
              />
            </div>
          </Card>
        )
      )}
    </div>
  );
}
