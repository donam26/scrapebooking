import { getTranslations } from "next-intl/server";
import { ButtonLink } from "@/components/ui";
import { BrandMark } from "@/components/icons";

/** 404 theo ngôn ngữ đang chọn (thay trang mặc định chỉ có tiếng Anh của Next.js). */
export default async function NotFound() {
  const t = await getTranslations("common.notFound");
  return (
    <main className="grid min-h-screen place-items-center bg-canvas px-4">
      <div className="max-w-md text-center">
        <BrandMark size={40} />
        <h1 className="mt-5 text-2xl font-bold text-ink">{t("title")}</h1>
        <p className="mt-2 text-base text-muted">{t("body")}</p>
        <div className="mt-6 flex justify-center gap-3">
          <ButtonLink href="/dashboard" variant="primary">
            {t("toDashboard")}
          </ButtonLink>
          <ButtonLink href="/">{t("toHome")}</ButtonLink>
        </div>
      </div>
    </main>
  );
}
