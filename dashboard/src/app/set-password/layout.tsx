import type { Metadata } from "next";
import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("auth.setPassword");
  // Trang có token trong URL: không cho máy tìm kiếm lưu.
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default function SetPasswordLayout({ children }: { children: ReactNode }) {
  return children;
}
