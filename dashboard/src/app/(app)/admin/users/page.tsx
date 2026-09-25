"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { Card, EmptyState, ErrorBox, PageHeader, Select, Skeleton, Table, Th } from "@/components/ui";
import { IconUsers } from "@/components/icons";
import { CreateUserForm, UserRow } from "../../settings/users-tab";

const ALL_ROLES = ["operator", "tenant_admin", "viewer"];

/** Bộ lọc: "" = tất cả, "op" = tài khoản vận hành, số = id tenant. */
type Filter = "" | "op" | `${number}`;

export default function AdminUsersPage() {
  const { user: me, tenants } = useSession();
  const list = useApi("admin:users", () => api.users.list());
  const [filter, setFilter] = useState<Filter>("");
  const tenantName = (id: number | null) => (id === null ? "Vận hành" : (tenants.find((t) => t.id === id)?.name ?? `Tenant #${id}`));
  const all = list.data ?? [];
  const rows = all.filter((u) => (filter === "" ? true : filter === "op" ? u.tenant_id === null : u.tenant_id === Number(filter)));
  const activeCount = rows.filter((u) => u.active).length;

  return (
    <>
      <PageHeader title="Tài khoản" subtitle="Toàn bộ tài khoản: đơn vị vận hành và người dùng của từng tenant" />
      <Card title="Tạo tài khoản" description="Mật khẩu tối thiểu 8 ký tự; gửi cho người dùng qua kênh riêng" className="mb-6">
        <CreateUserForm roles={ALL_ROLES} tenantId={null} showTenant tenants={tenants} onCreated={list.reload} />
      </Card>
      <ErrorBox error={list.error} className="mb-4" />
      <Card
        padded={false}
        title="Danh sách tài khoản"
        description={list.data ? `${rows.length} tài khoản · ${activeCount} đang hoạt động` : undefined}
        actions={
          <label className="flex items-center gap-2 text-sm text-muted">
            <span className="whitespace-nowrap">Lọc theo</span>
            <Select value={filter} onChange={(e) => setFilter(e.target.value as Filter)} className="h-8 w-56 text-sm" aria-label="Lọc theo tenant">
              <option value="">Tất cả tenant</option>
              <option value="op">Vận hành</option>
              {tenants.map((t) => (
                <option key={t.id} value={String(t.id)}>
                  {t.name}
                  {t.active ? "" : " (tắt)"}
                </option>
              ))}
            </Select>
          </label>
        }
      >
        {!list.data && !list.error ? (
          <Skeleton rows={5} className="p-5" />
        ) : rows.length === 0 ? (
          <div className="p-5">
            <EmptyState compact icon={<IconUsers />} title={all.length === 0 ? "Chưa có tài khoản nào" : "Không có tài khoản khớp bộ lọc"}>
              {all.length === 0 ? "Tạo tài khoản đầu tiên ở khung phía trên." : "Chọn “Tất cả tenant” để xem mọi tài khoản."}
            </EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Email</Th>
                <Th className="hidden md:table-cell">Tenant</Th>
                <Th>Vai trò</Th>
                <Th className="hidden sm:table-cell">Trạng thái</Th>
                <Th className="relative">
                  <span className="sr-only">Thao tác</span>
                </Th>
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
