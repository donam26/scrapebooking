"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { api } from "@/lib/api";
import { useMutation } from "@/lib/hooks";
import { useSession } from "@/lib/session";
import { IconRefresh } from "./icons";
import { Button, cx } from "./ui";

/**
 * "Quét ngay" một khách sạn (chỉ quản trị): đưa khách sạn vào hàng đợi quét Booking.com,
 * không đợi mốc giờ. Trong 10 phút bấm lại trả về lượt đang chạy.
 */
export function ScanHotelButton({ hotelId, className }: { hotelId: number; className?: string }) {
  const t = useTranslations("components.scanHotel");
  const { canWrite } = useSession();
  const [queued, setQueued] = useState(false);
  const scan = useMutation(async () => {
    await api.watchlist.scanHotel(hotelId);
    setQueued(true);
  });
  if (!canWrite) return null;
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <Button size="sm" variant="quiet" busy={scan.busy} disabled={queued} icon={<IconRefresh size={15} />} onClick={() => void scan.run()}>
        {queued ? t("queued") : t("scanNow")}
      </Button>
      {scan.error && <span className="text-xs text-danger">{scan.error}</span>}
    </span>
  );
}
