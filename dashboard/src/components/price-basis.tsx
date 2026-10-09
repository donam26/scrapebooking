"use client";

import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { PriceBasis as ApiPriceBasis } from "@/lib/api";
import { Segmented } from "./ui";

/**
 * Giá đem so (cùng điều kiện, roadmap 2.4): rẻ nhất mọi gói; rẻ nhất trong các gói huỷ miễn phí
 * (gần BAR nhất); có bữa sáng; chỉ phòng. Đối thủ bán gói không hoàn huỷ rẻ hơn 10–20%, giá gồm
 * bữa sáng phổ biến ở Việt Nam: so lệch điều kiện làm trung vị sai.
 */
export type PriceBasis = ApiPriceBasis;

const BASES: readonly PriceBasis[] = ["any", "refundable", "breakfast", "room_only"];

/** Đọc `?basis=` từ URL; mặc định mọi giá. */
export function usePriceBasis(): PriceBasis {
  const raw = useSearchParams().get("basis");
  return BASES.find((b) => b === raw) ?? "any";
}

/** `(basis) => tên của giá đang so`, dùng trong nhãn biểu đồ và chú giải. */
export function usePriceNoun(): (basis: PriceBasis) => string {
  const t = useTranslations("components.priceBasis.noun");
  return (basis) => t(basis);
}

/** Nhóm chọn "Mọi giá | Hoàn huỷ | Có bữa sáng | Chỉ phòng"; ghi vào URL để chia sẻ và tải lại được. */
export function PriceBasisPicker() {
  const t = useTranslations("components.priceBasis");
  const basis = usePriceBasis();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  function update(next: PriceBasis) {
    const q = new URLSearchParams(params.toString());
    if (next === "any") q.delete("basis");
    else q.set("basis", next);
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  return (
    <div className="sb-scroll max-w-full overflow-x-auto">
      <Segmented
        label={t("label")}
        value={basis}
        onChange={update}
        items={[
          { value: "any", label: t("any"), title: t("anyTitle") },
          { value: "refundable", label: t("refundable"), title: t("refundableTitle") },
          { value: "breakfast", label: t("breakfast"), title: t("breakfastTitle") },
          { value: "room_only", label: t("room_only"), title: t("room_onlyTitle") },
        ]}
      />
    </div>
  );
}
