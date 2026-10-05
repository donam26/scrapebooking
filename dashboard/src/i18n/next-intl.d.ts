import type { Locale } from "./config";
import type { Messages } from "@/messages";

// Khoá bản dịch có kiểu: t("dashboard.title") sai tên là lỗi tsc.
declare module "next-intl" {
  interface AppConfig {
    Locale: Locale;
    Messages: Messages;
  }
}
