/**
 * Tên quận/thành phố từ Booking.com (luôn tiếng Anh: "Ho Chi Minh Municipality", "District 1") thành tên
 * theo ngôn ngữ giao diện ("TP. Hồ Chí Minh", "Quận 1"). Tên lạ giữ nguyên.
 */
import { useTranslations } from "next-intl";
import { useMemo } from "react";

type PlaceTranslator = ReturnType<typeof useTranslations<"labels.place">>;

const CITY: Record<string, "hcmc" | "hanoi" | "danang"> = {
  "ho chi minh city": "hcmc",
  "ho chi minh municipality": "hcmc",
  "ho chi minh": "hcmc",
  saigon: "hcmc",
  hanoi: "hanoi",
  "ha noi": "hanoi",
  "da nang": "danang",
  danang: "danang",
};

const DISTRICT_RE = /^district\s+(\d{1,2})$/i;

export function createPlaceName(t: PlaceTranslator) {
  return (raw: string | null | undefined): string | null => {
    const v = raw?.trim();
    if (!v) return null;
    const city = CITY[v.toLowerCase()];
    if (city) return t(city);
    const d = DISTRICT_RE.exec(v);
    if (d) return t("district", { n: d[1] });
    return v;
  };
}

/** `place("District 1")` -> "Quận 1"; `place(null)` -> null. */
export function usePlaceName() {
  const t = useTranslations("labels.place");
  return useMemo(() => createPlaceName(t), [t]);
}
