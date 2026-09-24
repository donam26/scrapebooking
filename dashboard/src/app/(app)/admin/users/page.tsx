"use client";

import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { Card, EmptyState, ErrorBox, PageHeader, Skeleton, Table, Th } from "@/components/ui";
import { CreateUserForm, UserRow } from "../../settings/users-tab";

const ALL_ROLES = ["operator", "tenant_admin", "viewer"];

export default function AdminUsersPage() {
  const { user: me, tenants } = useSession();
  const list = useApi("admin:users", () => api.users.list());
  const tenantName = (id: number | null) => (id === null ? "— (operator)" : (tenants.find((t) => t.id === id)?.name ?? `#${id}`));
  const rows = list.data ?? [];
  return (
    <>
      <PageHeader title="Người dùng" subtitle="Toàn bộ tài khoản: operator và người dùng của từng tenant" />
      <Card title="Tạo người dùng" className="mb-4">
        <CreateUserForm roles={ALL_ROLES} tenantId={null} showTenant tenants={tenants} onCreated={list.reload} />
      </Card>
      <ErrorBox error={list.error} className="mb-4" />
      <Card padded={false} title={`Tài khoản (${rows.length})`}>
        {!list.data && !list.error ? (
          <Skeleton rows={5} className="p-4" />
        ) : rows.length === 0 ? (
          <div className="p-4">
            <EmptyState>Chưa có người dùng nào.</EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Email</Th>
                <Th>Tenant</Th>
                <Th>Vai trò</Th>
                <Th>Trạng thái</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <UserRow key={u.id} user={u} roles={ALL_ROLES} canWrite isSelf={u.id === me?.id} tenantName={tenantName(u.tenant_id)} onChanged={list.reload} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
