"use client";

import { useTranslations } from "next-intl";
import type { ReactNode } from "react";
import { IconCalendar, IconClock, IconPin } from "@/components/icons";
import { ScheduleTab } from "./schedule-tab";
import { MarketTab } from "./market-tab";
import { EventsTab } from "./events-tab";

export type AdvancedSection = "schedule" | "market" | "events";

/**
 * Cài đặt › Nâng cao: những thứ ít khi đổi. Mỗi mục có id `settings-<mục>` để link cũ
 * (`?tab=schedule|market|events`) cuộn tới đúng chỗ.
 */
export function AdvancedTab() {
  const t = useTranslations("settings.advanced");
  return (
    <div className="space-y-10">
      <Section id="schedule" icon={<IconClock size={17} />} title={t("schedule")} hint={t("scheduleHint")}>
        <ScheduleTab />
      </Section>
      <Section id="market" icon={<IconPin size={17} />} title={t("market")} hint={t("marketHint")}>
        <MarketTab />
      </Section>
      <Section id="events" icon={<IconCalendar size={17} />} title={t("events")} hint={t("eventsHint")}>
        <EventsTab />
      </Section>
    </div>
  );
}

function Section({ id, icon, title, hint, children }: { id: AdvancedSection; icon: ReactNode; title: string; hint: string; children: ReactNode }) {
  return (
    <section id={`settings-${id}`} aria-labelledby={`settings-${id}-title`} className="scroll-mt-20">
      <div className="mb-3">
        <h2 id={`settings-${id}-title`} className="flex items-center gap-2 text-lg font-bold text-ink">
          <span aria-hidden className="text-brand">
            {icon}
          </span>
          {title}
        </h2>
        <p className="mt-0.5 text-sm text-muted">{hint}</p>
      </div>
      {children}
    </section>
  );
}
