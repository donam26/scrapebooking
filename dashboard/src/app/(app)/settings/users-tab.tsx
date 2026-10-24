"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type InviteOut, type UserOut } from "@/lib/api";
import { useFmt } from "@/lib/format";
import { useApi, useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { useLabel } from "@/lib/labels";
import { Badge, Button, Card, EmptyState, ErrorBox, Field, Input, Note, ROW_CLASS, Segmented, Select, Skeleton, Table, Td, Th, cx } from "@/components/ui";
import { IconCheck, IconKey, IconLink, IconLock, IconMail, IconPlus, IconUsers } from "@/components/icons";

const ROLE_HINT_KEYS = ["operator", "tenant_admin", "viewer"] as const;

function isRoleHintKey(role: string): role is (typeof ROLE_HINT_KEYS)[number] {
  return (ROLE_HINT_KEYS as readonly string[]).includes(role);
}

type DoneKey = "roleChanged" | "passwordSet" | "locked" | "unlocked";

/** Cách thêm người: gửi link tự đặt mật khẩu (mặc định) hoặc quản trị đặt mật khẩu ngay. */
type AddMode = "invite" | "password";

/** Bộ ký tự mật khẩu sinh sẵn: bỏ ký tự dễ nhầm (0/O, 1/l/I) để đọc qua điện thoại. */
const PASSWORD_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
const PASSWORD_LENGTH = 12;

/** Mật khẩu ngẫu nhiên 12 ký tự (crypto.getRandomValues). */
export function generatePassword(): string {
  const bytes = new Uint32Array(PASSWORD_LENGTH);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => PASSWORD_CHARS[b % PASSWORD_CHARS.length]).join("");
}

/**
 * Kết quả mời / gửi lại lời mời: đã gửi email, hoặc đường dẫn để quản trị tự sao chép và gửi
 * (khi đơn vị vận hành chưa bật email hoặc email gửi lỗi).
 */
export function InviteResult({ result, resent }: { result: InviteOut; resent?: boolean }) {
  const t = useTranslations("settings.users.invite");
  const { fmtDateTime } = useFmt();
  const [copied, setCopied] = useState(false);
  const email = result.user.email;
  if (result.email_status === "sent") {
    return (
      <p role="status" className="flex items-start gap-1.5 text-sm text-yours-deep">
        <IconCheck size={16} className="mt-0.5 shrink-0" /> {t(resent ? "resent" : "sent", { email })}
      </p>
    );
  }
  return (
    <Note tone="warn" icon={<IconMail size={16} />} className="max-w-2xl">
      <p role="status">{result.email_status === "failed" ? t("failed", { email }) : t("notConfigured")}</p>
      <div className="mt-2 flex min-w-0 flex-wrap gap-1.5">
        <Input
          readOnly
          value={result.invite_url}
          aria-label={t("linkAria", { email })}
          onFocus={(e) => e.currentTarget.select()}
          className="h-8 min-w-0 flex-1 basis-56 bg-surface text-sm text-ink"
        />
        <Button
          size="sm"
          variant="secondary"
          icon={copied ? <IconCheck size={14} /> : <IconLink size={14} />}
          className="h-8 shrink-0"
          onClick={() =>
            navigator.clipboard?.writeText(result.invite_url).then(
              () => setCopied(true),
              () => setCopied(false),
            )
          }
        >
          {copied ? t("copied") : t("copy")}
        </Button>
      </div>
      <p className="mt-1.5 text-xs">{t("expires", { when: fmtDateTime(result.expires_at) })}</p>
    </Note>
  );
}

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
  const [mode, setMode] = useState<AddMode>("invite");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // Mặc định "Chỉ xem": quyền quản trị phải chọn có chủ ý (C5).
  const [role, setRole] = useState(roles.includes("viewer") ? "viewer" : roles[0]);
  const [shown, setShown] = useState(false);
  const [copied, setCopied] = useState(false);
  const [tenant, setTenant] = useState<string>(tenantId === null ? "" : String(tenantId));
  const [created, setCreated] = useState<string | null>(null);
  const [invited, setInvited] = useState<InviteOut | null>(null);
  const t = useTranslations("settings.users");
  const label = useLabel();
  const create = useMutation(async () => {
    const tid = role === "operator" ? null : tenant ? Number(tenant) : tenantId;
    if (mode === "invite") {
      setInvited(await api.users.invite({ email: email.trim(), role, tenant_id: tid }));
    } else {
      await api.users.create({ email: email.trim(), password, role, tenant_id: tid });
      setCreated(email.trim());
    }
    setEmail("");
    setPassword("");
    setShown(false);
    setCopied(false);
    onCreated();
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    setCreated(null);
    setInvited(null);
    void create.run();
  }
  const withTenant = showTenant && role !== "operator";
  const invite = mode === "invite";
  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <Segmented
          label={t("form.mode")}
          size="sm"
          value={mode}
          onChange={(m) => {
            setMode(m);
            setCreated(null);
            setInvited(null);
            create.clearError();
          }}
          items={[
            { value: "invite", label: t("form.modeInvite") },
            { value: "password", label: t("form.modePassword") },
          ]}
        />
        {invite && <span className="text-xs text-muted">{t("form.inviteHint")}</span>}
      </div>
      <div
        className={cx(
          "grid gap-3 sm:grid-cols-2 lg:items-start",
          invite
            ? withTenant
              ? "lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
              : "lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto]"
            : withTenant
              ? "lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]"
              : "lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1.3fr)_minmax(0,0.9fr)_auto]",
        )}
      >
        <Field label={t("form.email")}>
          <Input type="email" required autoComplete="off" placeholder={t("form.emailPlaceholder")} value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        {!invite && (
          <Field label={t("form.password")} hint={copied ? <span className="text-yours-deep">{t("form.passwordCopied")}</span> : t("form.passwordHint")}>
            <div className="flex min-w-0 gap-1.5">
              <Input
                type={shown ? "text" : "password"}
                required
                minLength={8}
                autoComplete="new-password"
                aria-label={t("form.passwordAria")}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setCopied(false);
                }}
                className="min-w-0 flex-1 tabular"
              />
              <Button
                size="sm"
                variant="quiet"
                icon={<IconKey size={14} />}
                className="h-9 shrink-0"
                title={t("form.generateTitle")}
                onClick={() => {
                  const next = generatePassword();
                  setPassword(next);
                  setShown(true);
                  navigator.clipboard?.writeText(next).then(
                    () => setCopied(true),
                    () => setCopied(false),
                  );
                }}
              >
                {t("form.generate")}
              </Button>
            </div>
          </Field>
        )}
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
        <Button
          type="submit"
          variant="primary"
          busy={create.busy}
          icon={invite ? <IconMail size={16} /> : <IconPlus size={16} />}
          className="sm:col-span-2 sm:justify-self-start lg:col-span-1 lg:mt-[26px]"
        >
          {invite ? t("form.submitInvite") : t("form.submit")}
        </Button>
      </div>
      <ErrorBox error={create.error} title={t("form.errorTitle")} />
      {created && !create.error && (
        <p role="status" className="flex items-center gap-1.5 text-sm text-yours-deep">
          <IconCheck size={16} /> {t("form.created", { email: created })}
        </p>
      )}
      {invited && !create.error && <InviteResult key={invited.invite_url} result={invited} />}
    </form>
  );
}

export function UserRow({
  user,
  roles,
  canWrite,
  isSelf,
  tenantName,
  showLastLogin,
  onInvited,
  onChanged,
}: {
  user: UserOut;
  roles: string[];
  canWrite: boolean;
  isSelf: boolean;
  tenantName?: string;
  /** Cột "Lần đăng nhập cuối" (bảng Cài đặt › Người dùng). */
  showLastLogin?: boolean;
  /** Kết quả "Gửi lại lời mời" hiện ngoài bảng (bảng cuộn ngang trên điện thoại); không có thì hiện ngay dưới hàng. */
  onInvited?: (result: InviteOut) => void;
  onChanged: () => void;
}) {
  const [resetting, setResetting] = useState(false);
  const [password, setPassword] = useState("");
  const [done, setDone] = useState<DoneKey | null>(null);
  const [resent, setResent] = useState<InviteOut | null>(null);
  const t = useTranslations("settings.users");
  const tc = useTranslations("common.actions");
  const label = useLabel();
  const { fmtAgo, fmtDateTime } = useFmt();
  const update = useMutation(async (body: Parameters<typeof api.users.update>[1], message?: DoneKey) => {
    await api.users.update(user.id, body);
    setResetting(false);
    setPassword("");
    setDone(message ?? null);
    setResent(null);
    onChanged();
  });
  const resend = useMutation(async () => {
    const res = await api.users.resendInvite(user.id);
    setDone(null);
    if (onInvited) onInvited(res);
    else setResent(res);
    onChanged();
  });
  const pending = user.active && user.invite_pending;
  const inviteExpired = pending && user.invite_expires_at !== null && new Date(user.invite_expires_at) <= new Date();
  const status = !user.active ? (
    <Badge tone="gray">{t("row.locked")}</Badge>
  ) : pending ? (
    <Badge tone="amber" title={inviteExpired ? t("row.pendingExpired") : t("row.pendingTitle", { when: fmtDateTime(user.invite_expires_at) })}>
      {t("row.pending")}
    </Badge>
  ) : (
    <Badge tone="green">{t("row.active")}</Badge>
  );
  const lastLogin = user.last_login_at ? fmtAgo(user.last_login_at) : null;
  const cols = 3 + (tenantName !== undefined ? 1 : 0) + (showLastLogin ? 1 : 0) + (canWrite ? 1 : 0);
  const error = update.error ?? resend.error;
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
              <div className="mt-1 sm:hidden">{status}</div>
              {showLastLogin && (
                <div className="mt-0.5 text-xs text-muted md:hidden">{lastLogin ? t("row.lastLogin", { when: lastLogin }) : t("row.neverLoggedIn")}</div>
              )}
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
          <div className="flex flex-col items-start gap-1">
            {status}
            {canWrite && pending && (
              <button
                type="button"
                disabled={resend.busy}
                onClick={() => void resend.run()}
                className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline disabled:opacity-60"
              >
                <IconMail size={13} /> {t("row.resendInvite")}
              </button>
            )}
          </div>
        </Td>
        {showLastLogin && (
          <Td className="hidden whitespace-nowrap text-muted md:table-cell" title={user.last_login_at ? fmtDateTime(user.last_login_at) : undefined}>
            {lastLogin ?? t("row.neverLoggedIn")}
          </Td>
        )}
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
                {pending && (
                  <Button
                    size="sm"
                    variant="ghost"
                    busy={resend.busy}
                    icon={<IconMail size={15} />}
                    onClick={() => void resend.run()}
                    aria-label={t("row.resendInvite")}
                    title={t("row.resendInvite")}
                    className="sm:hidden"
                  />
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  icon={<IconKey size={15} />}
                  onClick={() => {
                    setDone(null);
                    setResent(null);
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
      {(error || resent) && (
        <tr>
          <td colSpan={cols} className="border-b border-line px-4 pb-3">
            {error ? <ErrorBox error={error} /> : resent && <InviteResult key={resent.invite_url} result={resent} resent />}
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
  const [resent, setResent] = useState<InviteOut | null>(null);
  const resentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (resent) resentRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [resent]);
  return (
    <div className="space-y-5">
      {canWrite && (
        <Card title={t("addTitle")} description={t("addDescription")}>
          <CreateUserForm roles={TENANT_ROLES} tenantId={tenantId} onCreated={list.reload} />
        </Card>
      )}
      <ErrorBox error={list.error} />
      <Card padded={false} title={t("listTitle")} description={list.data ? t("listSummary", { count: users.length, active: activeCount }) : undefined}>
        {resent && (
          <div ref={resentRef} className="scroll-mt-20 px-5 pb-4">
            <InviteResult key={resent.invite_url} result={resent} resent />
          </div>
        )}
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
                <Th className="hidden md:table-cell">{t("colLastLogin")}</Th>
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
                <UserRow key={u.id} user={u} roles={TENANT_ROLES} canWrite={canWrite} isSelf={u.id === me?.id} showLastLogin onInvited={setResent} onChanged={list.reload} />
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
