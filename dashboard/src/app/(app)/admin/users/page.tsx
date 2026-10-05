"use client";

import { useTranslations } from "next-intl";
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
  const t = useTranslations("admin.users");
  const list = useApi("admin:users", () => api.users.list());
  const [filter, setFilter] = useState<Filter>("");
  const tenantName = (id: number | null) => (id === null ? t("operator") : (tenants.find((x) => x.id === id)?.name ?? t("tenantFallback", { id })));
  const all = list.data ?? [];
  const rows = all.filter((u) => (filter === "" ? true : filter === "op" ? u.tenant_id === null : u.tenant_id === Number(filter)));
  const activeCount = rows.filter((u) => u.active).length;

  return (
    <>
      <PageHeader title={t("title")} subtitle={t("subtitle")} />
      <Card title={t("create.title")} description={t("create.description")} className="mb-6">
        <CreateUserForm roles={ALL_ROLES} tenantId={null} showTenant tenants={tenants} onCreated={list.reload} />
      </Card>
      <ErrorBox error={list.error} className="mb-4" />
      <Card
        padded={false}
        title={t("list.title")}
        description={list.data ? t("list.count", { count: rows.length, active: activeCount }) : undefined}
        actions={
          <label className="flex items-center gap-2 text-sm text-muted">
            <span className="whitespace-nowrap">{t("filter.label")}</span>
            <Select value={filter} onChange={(e) => setFilter(e.target.value as Filter)} className="h-8 w-56 text-sm" aria-label={t("filter.aria")}>
              <option value="">{t("filter.all")}</option>
              <option value="op">{t("operator")}</option>
              {tenants.map((x) => (
                <option key={x.id} value={String(x.id)}>
                  {x.name}
                  {x.active ? "" : ` ${t("filter.inactive")}`}
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
            <EmptyState compact icon={<IconUsers />} title={all.length === 0 ? t("empty.noneTitle") : t("empty.noMatchTitle")}>
              {all.length === 0 ? t("empty.noneBody") : t("empty.noMatchBody")}
            </EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t("table.email")}</Th>
                <Th className="hidden md:table-cell">{t("table.tenant")}</Th>
                <Th>{t("table.role")}</Th>
                <Th className="hidden sm:table-cell">{t("table.status")}</Th>
                <Th className="relative">
                  <span className="sr-only">{t("table.actions")}</span>
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
