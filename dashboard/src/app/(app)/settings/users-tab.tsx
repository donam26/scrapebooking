"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { api, type UserOut } from "@/lib/api";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useLabel } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, ROW_CLASS, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconCheck, IconKey, IconLock, IconPlus, IconUsers } from "@/components/icons";

const ROLE_HINT_KEYS = ["operator", "tenant_admin", "viewer"] as const;

function isRoleHintKey(role: string): role is (typeof ROLE_HINT_KEYS)[number] {
  return (ROLE_HINT_KEYS as readonly string[]).includes(role);
}

type DoneKey = "roleChanged" | "passwordSet" | "locked" | "unlocked";

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
  const t = useTranslations("settings.users");
  const label = useLabel();
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
        <Field label={t("form.email")}>
          <Input type="email" required autoComplete="off" placeholder={t("form.emailPlaceholder")} value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label={t("form.password")} hint={t("form.passwordHint")}>
          <Input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label={t("form.role")} hint={isRoleHintKey(role) ? t(`roleHint.${role}`) : undefined}>
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map((r) => (
              <option key={r} value={r}>
                {label("userRole", r)}
              </option>
            ))}
          </Select>
        </Field>
        {withTenant && (
          <Field label={t("form.tenant")}>
            <Select required value={tenant} onChange={(e) => setTenant(e.target.value)}>
              <option value="">{t("form.pickTenant")}</option>
              {(tenants ?? []).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Button type="submit" variant="primary" busy={create.busy} icon={<IconPlus size={16} />} className="sm:col-span-2 sm:justify-self-start lg:col-span-1 lg:mt-[26px]">
          {t("form.submit")}
        </Button>
      </div>
      <ErrorBox error={create.error} title={t("form.errorTitle")} />
      {created && !create.error && (
        <p role="status" className="flex items-center gap-1.5 text-sm text-yours-deep">
          <IconCheck size={16} /> {t("form.created", { email: created })}
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
  const [done, setDone] = useState<DoneKey | null>(null);
  const t = useTranslations("settings.users");
  const tc = useTranslations("common.actions");
  const label = useLabel();
  const update = useMutation(async (body: Parameters<typeof api.users.update>[1], message?: DoneKey) => {
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
                {isSelf && <span className="ml-1.5 text-xs font-normal text-muted">{t("row.you")}</span>}
              </div>
              {tenantName !== undefined && <div className="truncate text-xs text-muted md:hidden">{tenantName}</div>}
              <div className="mt-1 sm:hidden">
                <Badge tone={user.active ? "green" : "gray"}>{user.active ? t("row.active") : t("row.locked")}</Badge>
              </div>
              {done && <div className="text-xs text-yours-deep">{t(`done.${done}`)}</div>}
            </div>
          </div>
        </Td>
        {tenantName !== undefined && <Td className="hidden whitespace-nowrap text-body md:table-cell">{tenantName}</Td>}
        <Td>
          {canWrite && !isSelf ? (
            <Select
              aria-label={t("row.roleAria", { email: user.email })}
              value={user.role}
              onChange={(e) => void update.run({ role: e.target.value }, "roleChanged")}
              disabled={update.busy}
              className="h-8 !w-[124px] shrink-0 text-sm sm:!w-[150px]"
            >
              {roles.map((r) => (
                <option key={r} value={r}>
                  {label("userRole", r)}
                </option>
              ))}
            </Select>
          ) : (
            <span className="text-body">{label("userRole", user.role)}</span>
          )}
        </Td>
        <Td className="hidden sm:table-cell">
          <Badge tone={user.active ? "green" : "gray"}>{user.active ? t("row.active") : t("row.locked")}</Badge>
        </Td>
        {canWrite && (
          <Td className="w-0 whitespace-nowrap">
            {resetting ? (
              <form
                className="flex items-center justify-end gap-1.5"
                onSubmit={(e) => {
                  e.preventDefault();
                  void update.run({ password }, "passwordSet");
                }}
              >
                <Input
                  type="password"
                  minLength={8}
                  required
                  autoFocus
                  aria-label={t("row.newPasswordAria", { email: user.email })}
                  placeholder={t("row.newPasswordPlaceholder")}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-8 w-52 text-sm"
                />
                <Button size="sm" type="submit" variant="primary" busy={update.busy}>
                  {t("row.setPassword")}
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
                  {tc("cancel")}
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
                  aria-label={t("row.resetPassword")}
                  title={t("row.resetPassword")}
                >
                  <span className="hidden sm:inline">{t("row.resetPassword")}</span>
                </Button>
                {!isSelf && (
                  <Button
                    size="sm"
                    variant="ghost"
                    busy={update.busy}
                    icon={<IconLock size={15} />}
                    onClick={() => void update.run({ active: !user.active }, user.active ? "locked" : "unlocked")}
                    className={user.active ? "hover:!bg-danger-soft hover:!text-danger" : undefined}
                    aria-label={user.active ? t("row.lockAccount") : t("row.unlockAccount")}
                    title={user.active ? t("row.lockAccount") : t("row.unlockAccount")}
                  >
                    <span className="hidden sm:inline">{user.active ? t("row.lock") : t("row.unlock")}</span>
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
  const t = useTranslations("settings.users");
  return (
    <div className="space-y-5">
      {canWrite && (
        <Card title={t("addTitle")} description={t("addDescription")}>
          <CreateUserForm roles={TENANT_ROLES} tenantId={tenantId} onCreated={list.reload} />
        </Card>
      )}
      <ErrorBox error={list.error} />
      <Card padded={false} title={t("listTitle")} description={list.data ? t("listSummary", { count: users.length, active: activeCount }) : undefined}>
        {!list.data && !list.error ? (
          <Skeleton rows={4} className="p-5" />
        ) : users.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={<IconUsers />} title={t("emptyTitle")} compact>
              {canWrite ? t("emptyWrite") : t("emptyRead")}
            </EmptyState>
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t("colEmail")}</Th>
                <Th>{t("colRole")}</Th>
                <Th className="hidden sm:table-cell">{t("colStatus")}</Th>
                {canWrite && (
                  <Th right>
                    <span className="relative">
                      <span className="sr-only">{t("colActions")}</span>
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
