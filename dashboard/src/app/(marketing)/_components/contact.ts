/**
 * Kênh liên hệ cho khách vãng lai, đọc từ env lúc chạy (giống API_INTERNAL_URL) nên đổi
 * số điện thoại hay email không cần build lại. Kênh nào chưa đặt thì không hiện.
 *
 *   CONTACT_PHONE  số gọi điện, ví dụ "0901 234 567"
 *   CONTACT_ZALO   số Zalo (chỉ chữ số) hoặc link zalo.me đầy đủ
 *   CONTACT_EMAIL  email nhận yêu cầu tư vấn
 */

/** Chữ của các kênh, lấy từ landing.contact (server component truyền translator vào). */
type ContactKey = "zalo" | "zaloLink" | "phone" | "email" | "emailSubject";

export type ContactChannel = {
  kind: "zalo" | "phone" | "email";
  label: string;
  value: string;
  href: string;
};

function clean(v: string | undefined): string {
  return (v ?? "").trim();
}

/** "0901234567" -> "0901 234 567"; giữ nguyên chuỗi đã có khoảng trắng hoặc không đủ 10 số. */
function formatPhone(v: string): string {
  const digits = v.replace(/\D/g, "");
  if (/\s/.test(v) || digits.length !== 10) return v;
  return `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
}

export function contactChannels(t: (key: ContactKey) => string): ContactChannel[] {
  const phone = clean(process.env.CONTACT_PHONE);
  const zalo = clean(process.env.CONTACT_ZALO);
  const email = clean(process.env.CONTACT_EMAIL);
  const channels: ContactChannel[] = [];

  if (zalo) {
    const href = /^https?:\/\//.test(zalo) ? zalo : `https://zalo.me/${zalo.replace(/\D/g, "")}`;
    const value = /^https?:\/\//.test(zalo) ? t("zaloLink") : formatPhone(zalo);
    channels.push({ kind: "zalo", label: t("zalo"), value, href });
  }
  if (phone) {
    channels.push({ kind: "phone", label: t("phone"), value: formatPhone(phone), href: `tel:${phone.replace(/[^\d+]/g, "")}` });
  }
  if (email) {
    const subject = encodeURIComponent(t("emailSubject"));
    channels.push({ kind: "email", label: t("email"), value: email, href: `mailto:${email}?subject=${subject}` });
  }
  return channels;
}
