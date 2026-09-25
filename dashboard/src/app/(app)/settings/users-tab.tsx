"use client";

import { useState, type FormEvent } from "react";
import { api, type UserOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { USER_ROLE_LABEL } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, ROW_CLASS, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconCheck, IconKey, IconLock, IconPlus, IconUsers } from "@/components/icons";

const ROLE_HINT: Record<string, string> = {
  operator: "Vận hành mọi tenant",
  tenant_admin: "Sửa watchlist, lịch quét, người dùng, nhập PMS",
  viewer: "Chỉ xem số liệu và bản tin",
};

export function CreateUserForm({
  roles,
  tenantId,
  showTenant,
  tenants,
  onCreated,
}: {
  roles: string[];
  tenantId: number | null;
  showTenant?: boolean;
  tenants?: Array<{ id: number; name: string }>;
  onCreated: () => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(roles[0]);
  const [tenant, setTenant] = useState<string>(tenantId === null ? "" : String(tenantId));
  const [created, setCreated] = useState<string | null>(null);
  const create = useMutation(async () => {
    const tid = role === "operator" ? null : tenant ? Number(tenant) : tenantId;
    await api.users.create({ email: email.trim(), password, role, tenant_id: tid });
    setCreated(email.trim());
    setEmail("");
    setPassword("");
    onCreated();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    setCreated(null);
    void create.run();
  }
  const withTenant = showTenant && role !== "operator";
  return (
    <form onSubmit={submit} className="space-y-3">
      <div
        className={cx(
          "grid gap-3 sm:grid-cols-2 lg:items-start",
          withTenant ? "lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]" : "lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_auto]",
        )}
      >
        <Field label="Email đăng nhập">
          <Input type="email" required autoComplete="off" placeholder="ten@khachsan.vn" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Mật khẩu" hint="Tối thiểu 8 ký tự">
          <Input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label="Vai trò" hint={ROLE_HINT[role]}>
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map((r) => (
              <option key={r} value={r}>
                {USER_ROLE_LABEL[r] ?? r}
              </option>
            ))}
          </Select>
        </Field>
        {withTenant && (
          <Field label="Tenant">
            <Select required value={tenant} onChange={(e) => setTenant(e.target.value)}>
              <option value="">Chọn tenant…</option>
              {(tenants ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Button type="submit" variant="primary" busy={create.busy} icon={<IconPlus size={16} />} className="sm:col-span-2 sm:justify-self-start lg:col-span-1 lg:mt-[26px]">
          Tạo người dùng
        </Button>
      </div>
      <ErrorBox error={create.error} title="Chưa tạo được người dùng" />
      {created && !create.error && (
        <p role="status" className="flex items-center gap-1.5 text-sm text-yours-deep">
          <IconCheck size={16} /> Đã tạo tài khoản {created}. Gửi mật khẩu cho người dùng qua kênh riêng.
        </p>
      )}
    </form>
  );
}

export function UserRow({
  user,
  roles,
  canWrite,
  isSelf,
  tenantName,
  onChanged,
}: {
  user: UserOut;
  roles: string[];
  canWrite: boolean;
  isSelf: boolean;
  tenantName?: string;
  onChanged: () => void;
}) {
  const [resetting, setResetting] = useState(false);
  const [password, setPassword] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const update = useMutation(async (body: Parameters<typeof api.users.update>[1], message?: string) => {
    await api.users.update(user.id, body);
    setResetting(false);
    setPassword("");
    setDone(message ?? null);
    onChanged();
  });
  const cols = 3 + (tenantName !== undefined ? 1 : 0) + (canWrite ? 1 : 0);
  return (
    <>
      <tr className={cx(ROW_CLASS, !user.active && "text-faint")}>
        <Td>
          <div className="flex min-w-0 items-center gap-3">
            <span
              aria-hidden
              className={cx(
                "grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm font-bold",
                user.active ? "bg-brand-soft text-brand-hover" : "bg-sunken text-faint",
              )}
            >
              {user.email.slice(0, 1).toUpperCase()}
            </span>
            <div className="min-w-0">
              <div className={cx("truncate font-semibold", user.active ? "text-ink" : "text-muted")} title={user.email}>
                {user.email}
                {isSelf && <span className="ml-1.5 text-xs font-normal text-muted">(bạn)</span>}
              </div>
              {tenantName !== undefined && <div className="truncate text-xs text-muted md:hidden">{tenantName}</div>}
              <div className="mt-1 sm:hidden">
                <Badge tone={user.active ? "green" : "gray"}>{user.active ? "Hoạt động" : "Đã khoá"}</Badge>
              </div>
              {done && <div className="text-xs text-yours-deep">{done}</div>}
            </div>
          </div>
        </Td>
        {tenantName !== undefined && <Td className="hidden whitespace-nowrap text-body md:table-cell">{tenantName}</Td>}
        <Td>
          {canWrite && !isSelf ? (
            <Select
              aria-label={`Vai trò của ${user.email}`}
              value={user.role}
              onChange={(e) => void update.run({ role: e.target.value }, "Đã đổi vai trò")}
              disabled={update.busy}
              className="h-8 !w-[124px] shrink-0 text-sm sm:!w-[150px]"
            >
              {roles.map((r) => (
                <option key={r} value={r}>
                  {USER_ROLE_LABEL[r] ?? r}
                </option>
              ))}
            </Select>
          ) : (
            <span className="text-body">{USER_ROLE_LABEL[user.role] ?? user.role}</span>
          )}
        </Td>
        <Td className="hidden sm:table-cell">
          <Badge tone={user.active ? "green" : "gray"}>{user.active ? "Hoạt động" : "Đã khoá"}</Badge>
        </Td>
        {canWrite && (
          <Td className="w-0 whitespace-nowrap">
            {resetting ? (
              <form
                className="flex items-center justify-end gap-1.5"
                onSubmit={(e) => {
                  e.preventDefault();
                  void update.run({ password }, "Đã đặt mật khẩu mới");
                }}
              >
                <Input
                  type="password"
                  minLength={8}
                  required
                  autoFocus
                  aria-label={`Mật khẩu mới cho ${user.email}`}
                  placeholder="Mật khẩu mới, ≥ 8 ký tự"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-8 w-52 text-sm"
                />
                <Button size="sm" type="submit" variant="primary" busy={update.busy}>
                  Đặt
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setResetting(false);
                    setPassword("");
                    update.clearError();
                  }}
                >
                  Huỷ
                </Button>
              </form>
            ) : (
              <div className="flex justify-end gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<IconKey size={15} />}
                  onClick={() => {
                    setDone(null);
                    setResetting(true);
                  }}
                  aria-label="Đặt lại mật khẩu"
                  title="Đặt lại mật khẩu"
                >
                  <span className="hidden sm:inline">Đặt lại mật khẩu</span>
                </Button>
                {!isSelf && (
                  <Button
                    size="sm"
                    variant="ghost"
                    busy={update.busy}
                    icon={<IconLock size={15} />}
                    onClick={() => void update.run({ active: !user.active }, user.active ? "Đã khoá tài khoản" : "Đã mở khoá")}
                    className={user.active ? "hover:!bg-danger-soft hover:!text-danger" : undefined}
                    aria-label={user.active ? "Khoá tài khoản" : "Mở khoá tài khoản"}
                    title={user.active ? "Khoá tài khoản" : "Mở khoá tài khoản"}
                  >
                    <span className="hidden sm:inline">{user.active ? "Khoá" : "Mở khoá"}</span>
                  </Button>
                )}
              </div>
            )}
          </Td>
        )}
      </tr>
      {update.error && (
        <tr>
          <td colSpan={cols} className="border-b border-line px-4 pb-3">
            <ErrorBox error={update.error} />
          </td>
        </tr>
      )}
    </>
  );
}

const TENANT_ROLES = ["tenant_admin", "viewer"];

export function UsersTab() {
  const { user: me, canWrite, isOperator, tenantId } = useSession();
  const list = useApi("users", () => api.users.list());
  // Operator xem toàn bộ /users; lọc theo tenant đang chọn.
  const users = (list.data ?? []).filter((u) => !isOperator || u.tenant_id === tenantId);
  const activeCount = users.filter((u) => u.active).length;
  return (
    <div className="space-y-5">
      {canWrite && (
        <Card title="Thêm người dùng" description="Quản trị sửa được cài đặt; chỉ xem thì đọc số liệu và bản tin.">
          <CreateUserForm roles={TENANT_ROLES} tenantId={tenantId} onCreated={list.reload} />
        </Card>
      )}
      <ErrorBox error={list.error} />
      <Card padded={false} title="Người dùng" description={list.data ? `${users.length} tài khoản, ${activeCount} đang hoạt động` : undefined}>
        {!list.data && !list.error ? (
          <Skeleton rows={4} className="p-5" />
        ) : users.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={<IconUsers />} title="Chưa có người dùng nào" compact>
              {canWrite ? "Tạo tài khoản cho đồng nghiệp ở trên để họ xem bảng giá mỗi sáng." : "Quản trị viên chưa thêm người dùng nào."}
            </EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Email</Th>
                <Th>Vai trò</Th>
                <Th className="hidden sm:table-cell">Trạng thái</Th>
                {canWrite && (
                  <Th right>
                    <span className="relative">
                      <span className="sr-only">Thao tác</span>
                    </span>
                  </Th>
                )}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <UserRow key={u.id} user={u} roles={TENANT_ROLES} canWrite={canWrite} isSelf={u.id === me?.id} onChanged={list.reload} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
