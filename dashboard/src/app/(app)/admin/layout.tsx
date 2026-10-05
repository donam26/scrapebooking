"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useSession } from "@/lib/session";
import { Skeleton } from "@/components/ui";

/** Chỉ operator được vào /admin/*; người dùng tenant bị đưa về /dashboard. */
export default function AdminLayout({ children }: { children: ReactNode }) {
  const { loading, user, isOperator } = useSession();
  const router = useRouter();
  const denied = !loading && !!user && !isOperator;

  useEffect(() => {
    if (denied) router.replace("/dashboard");
  }, [denied, router]);

  if (loading) return <Skeleton rows={6} className="max-w-xl" />;
  if (denied) return null;
  return <>{children}</>;
}
