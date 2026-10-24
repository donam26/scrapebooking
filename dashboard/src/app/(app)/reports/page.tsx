import { redirect } from "next/navigation";

/** Báo cáo mở ở tab con đầu tiên: Bản tin AI. */
export default function ReportsRedirect() {
  redirect("/insights");
}
