"use client";

import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Segmented } from "./ui";

/** Giá đem so: rẻ nhất mọi gói, hoặc rẻ nhất trong các gói có huỷ miễn phí (so cùng điều kiện). */
export type PriceBasis = "any" | "refundable";

/** Đọc `?basis=` từ URL; mặc định mọi giá. */
export function usePriceBasis(): PriceBasis {
  return useSearchParams().get("basis") === "refundable" ? "refundable" : "any";
}

/** `(basis) => tên của giá đang so`, dùng trong nhãn biểu đồ và chú giải. */
export function usePriceNoun(): (basis: PriceBasis) => string {
  const t = useTranslations("components.priceBasis.noun");
  return (basis) => t(basis);
}

/** Nhóm chọn "Mọi giá | Giá hoàn huỷ"; ghi vào URL để chia sẻ và tải lại được. */
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
    <Segmented
      label={t("label")}
      value={basis}
      onChange={update}
      items={[
        { value: "any", label: t("any"), title: t("anyTitle") },
        { value: "refundable", label: t("refundable"), title: t("refundableTitle") },
      ]}
    />
  );
}
