"use client";

import { useState, type FormEvent } from "react";
import { api, type UserOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { USER_ROLE_LABEL } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";

export function CreateUserForm({ roles, tenantId, showTenant, tenants, onCreated }: { roles: string[]; tenantId: number | null; showTenant?: boolean; tenants?: Array<{ id: number; name: string }>; onCreated: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(roles[0]);
  const [tenant, setTenant] = useState<string>(tenantId === null ? "" : String(tenantId));
  const create = useMutation(async () => {
    const tid = role === "operator" ? null : tenant ? Number(tenant) : tenantId;
    await api.users.create({ email: email.trim(), password, role, tenant_id: tid });
    setEmail("");
    setPassword("");
    onCreated();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    void create.run();
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Email" className="min-w-[220px]">
          <Input type="email" required autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Mật khẩu" hint="Tối thiểu 8 ký tự">
          <Input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label="Vai trò">
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map((r) => (
              <option key={r} value={r}>
                {USER_ROLE_LABEL[r] ?? r}
              </option>
            ))}
          </Select>
        </Field>
        {showTenant && role !== "operator" && (
          <Field label="Tenant">
            <Select required value={tenant} onChange={(e) => setTenant(e.target.value)}>
              <option value="">— Chọn —</option>
              {(tenants ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Button type="submit" variant="primary" busy={create.busy}>
          Tạo người dùng
        </Button>
      </div>
      <ErrorBox error={create.error} />
    </form>
  );
}

export function UserRow({ user, roles, canWrite, isSelf, tenantName, onChanged }: { user: UserOut; roles: string[]; canWrite: boolean; isSelf: boolean; tenantName?: string; onChanged: () => void }) {
  const [resetting, setResetting] = useState(false);
  const [password, setPassword] = useState("");
  const update = useMutation(async (body: Parameters<typeof api.users.update>[1]) => {
    await api.users.update(user.id, body);
    setResetting(false);
    setPassword("");
    onChanged();
  });
  return (
    <>
      <tr className={cx("hover:bg-slate-50", !user.active && "text-slate-400")}>
        <Td className="font-medium">
          {user.email}
          {isSelf && <span className="ml-1 text-xs font-normal text-slate-500">(bạn)</span>}
        </Td>
        {tenantName !== undefined && <Td>{tenantName}</Td>}
        <Td>
          {canWrite && !isSelf ? (
            <Select value={user.role} onChange={(e) => void update.run({ role: e.target.value })} disabled={update.busy}>
              {roles.map((r) => (
                <option key={r} value={r}>
                  {USER_ROLE_LABEL[r] ?? r}
                </option>
              ))}
            </Select>
          ) : (
            USER_ROLE_LABEL[user.role] ?? user.role
          )}
        </Td>
        <Td>
          <Badge tone={user.active ? "green" : "gray"}>{user.active ? "Hoạt động" : "Đã khoá"}</Badge>
        </Td>
        {canWrite && (
          <Td>
            <div className="flex flex-wrap items-center gap-1.5">
              {resetting ? (
                <form
                  className="flex items-center gap-1.5"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void update.run({ password });
                  }}
                >
                  <Input type="password" minLength={8} required placeholder="Mật khẩu mới" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
                  <Button size="sm" type="submit" variant="primary" busy={update.busy}>
                    Đặt
                  </Button>
                  <Button size="sm" onClick={() => setResetting(false)}>
                    Huỷ
                  </Button>
                </form>
              ) : (
                <>
                  <Button size="sm" onClick={() => setResetting(true)}>
                    Đặt lại mật khẩu
                  </Button>
                  {!isSelf && (
                    <Button size="sm" variant={user.active ? "danger" : "secondary"} busy={update.busy} onClick={() => void update.run({ active: !user.active })}>
                      {user.active ? "Khoá" : "Mở khoá"}
                    </Button>
                  )}
                </>
              )}
            </div>
          </Td>
        )}
      </tr>
      {update.error && (
        <tr>
          <td colSpan={tenantName !== undefined ? 5 : 4} className="px-3 pb-2">
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
  return (
    <div className="space-y-4">
      {canWrite && (
        <Card title="Thêm người dùng cho tenant">
          <CreateUserForm roles={TENANT_ROLES} tenantId={tenantId} onCreated={list.reload} />
        </Card>
      )}
      <ErrorBox error={list.error} />
      <Card title={`Người dùng (${users.length})`} padded={false}>
        {!list.data && !list.error ? (
          <Skeleton rows={4} className="p-4" />
        ) : users.length === 0 ? (
          <div className="p-4">
            <EmptyState>Chưa có người dùng nào.</EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Email</Th>
                <Th>Vai trò</Th>
                <Th>Trạng thái</Th>
                {canWrite && <Th />}
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
