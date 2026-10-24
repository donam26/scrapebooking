import { redirect } from "next/navigation";
import { calendarUrl } from "../calendar/redirect-url";

/** Trang Tổng quan cũ: nay là Lịch giá & phòng (giữ nguyên tham số kỳ xem). */
export default async function OverviewRedirect({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  redirect(calendarUrl(await searchParams));
}
