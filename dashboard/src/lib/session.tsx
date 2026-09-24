"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, setApiTenantScope, type TenantOut, type UserOut } from "./api";

const TENANT_KEY = "sb.tenant_id";

type SessionState = {
  loading: boolean;
  user: UserOut | null;
  tenants: TenantOut[];
  tenantId: number | null;
  error: string | null;
};

export type SessionValue = SessionState & {
  isOperator: boolean;
  /** tenant_admin hoặc operator: được ghi. */
  canWrite: boolean;
  tenant: TenantOut | null;
  setTenantId: (id: number | null) => void;
  /** Tải lại danh sách tenant (sau khi operator tạo/sửa). */
  refreshTenants: () => Promise<void>;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

function readStoredTenant(): number | null {
  try {
    const raw = window.localStorage.getItem(TENANT_KEY);
    const n = raw === null ? NaN : Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

function storeTenant(id: number | null): void {
  try {
    if (id === null) window.localStorage.removeItem(TENANT_KEY);
    else window.localStorage.setItem(TENANT_KEY, String(id));
  } catch {
    // localStorage có thể bị chặn; bỏ qua.
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({
    loading: true,
    user: null,
    tenants: [],
    tenantId: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const user = await api.auth.me();
        let tenants: TenantOut[] = [];
        let tenantId: number | null = user.tenant_id;
        const isOperator = user.role === "operator";
        if (isOperator) {
          tenants = await api.tenants.list();
          const stored = readStoredTenant();
          tenantId =
            stored !== null && tenants.some((t) => t.id === stored) ? stored : (tenants[0]?.id ?? null);
          storeTenant(tenantId);
        }
        setApiTenantScope({ isOperator, tenantId });
        if (!cancelled) setState({ loading: false, user, tenants, tenantId, error: null });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) return; // client đang chuyển về /login
        setState((s) => ({ ...s, loading: false, error: err instanceof Error ? err.message : String(err) }));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setTenantId = useCallback((id: number | null) => {
    setApiTenantScope({ isOperator: true, tenantId: id });
    storeTenant(id);
    setState((s) => ({ ...s, tenantId: id }));
  }, []);

  const refreshTenants = useCallback(async () => {
    const tenants = await api.tenants.list();
    setState((s) => ({ ...s, tenants }));
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } finally {
      storeTenant(null);
      // Tải lại toàn trang để xoá mọi state client (không dùng router.push).
      window.location.assign(new URL("/login", window.location.origin).toString());
    }
  }, []);

  const value = useMemo<SessionValue>(() => {
    const isOperator = state.user?.role === "operator";
    return {
      ...state,
      isOperator,
      canWrite: isOperator || state.user?.role === "tenant_admin",
      tenant: state.tenants.find((t) => t.id === state.tenantId) ?? null,
      setTenantId,
      refreshTenants,
      logout,
    };
  }, [state, setTenantId, refreshTenants, logout]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession phải dùng bên trong SessionProvider");
  return ctx;
}
