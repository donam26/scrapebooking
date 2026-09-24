"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";
import { useSession } from "./session";

export type ApiState<T> = {
  data: T | undefined;
  error: ApiError | Error | undefined;
  /** true khi đang tải lần đầu hoặc key đổi (dữ liệu cũ vẫn được giữ để tránh nháy). */
  loading: boolean;
  reload: () => void;
};

/**
 * Tải dữ liệu client-side. `key` mô tả tham số; đổi key (hoặc đổi tenant) sẽ tải lại.
 * `key === null` tắt việc tải. Fetcher mới nhất luôn được dùng mà không cần memo.
 */
export function useApi<T>(key: string | null, fetcher: () => Promise<T>): ApiState<T> {
  // tenantId nằm trong key để operator đổi tenant là tải lại; AppShell đã chặn các trang
  // theo tenant khi operator chưa chọn tenant, nên không cần chặn thêm ở đây.
  const { tenantId } = useSession();
  const [tick, setTick] = useState(0);
  const fullKey = key === null ? null : `${key}#${tenantId}#${tick}`;

  const [state, setState] = useState<{ key: string | null; data?: T; error?: ApiError | Error }>({ key: null });
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    if (fullKey === null) return;
    let cancelled = false;
    fetcherRef.current().then(
      (data) => {
        if (!cancelled) setState({ key: fullKey, data });
      },
      (err: unknown) => {
        if (!cancelled) setState({ key: fullKey, error: err instanceof Error ? err : new Error(String(err)) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [fullKey]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const current = state.key === fullKey;
  return {
    data: state.data,
    error: current ? state.error : undefined,
    loading: fullKey !== null && !current,
    reload,
  };
}

/** Gọi `fn` lặp lại mỗi `ms` (0 = tắt). Lần đầu chạy ngay. */
export function useInterval(fn: () => void, ms: number): void {
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  useEffect(() => {
    if (ms <= 0) return;
    const id = window.setInterval(() => fnRef.current(), ms);
    return () => window.clearInterval(id);
  }, [ms]);
}

/** Trạng thái cho một thao tác ghi (submit form). */
export function useMutation<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });
  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fnRef.current(...args);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { run, busy, error, clearError: () => setError(null) };
}
