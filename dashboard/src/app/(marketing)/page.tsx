import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { cookies } from "next/headers";
import Link from "next/link";
import type { ReactNode } from "react";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { INTL_LOCALE } from "@/i18n/config";
import { getFmt } from "@/i18n/server";
import { BriefSheet } from "./_components/brief";
import { contactChannels, type ContactChannel } from "./_components/contact";
import { todayInVietnam } from "./_components/demo-data";
import { HeroVisual } from "./_components/hero-visual";
import { MarketBoard } from "./_components/market-board";
import { NavMenu } from "./_components/nav-menu";
import {
  ConfidenceSwatch,
  IconArchive,
  IconArrow,
  IconChat,
  IconChevron,
  IconClock,
  IconEye,
  IconGlobe,
  IconInfo,
  IconMail,
  IconPhone,
  IconShield,
  IconTick,
  IconUser,
  Wordmark,
} from "./_components/marks";
import { PhotoFrame } from "./_components/photo";
import { PHOTOS } from "./_components/photos";
import { PmsChart } from "./_components/pms-chart";

export async function generateMetadata(): Promise<Metadata> {
  const [t, locale] = await Promise.all([getTranslations("landing.meta"), getLocale()]);
  return {
    title: { absolute: t("title") },
    description: t("description"),
    openGraph: {
      title: t("ogTitle"),
      description: t("ogDescription"),
      locale: INTL_LOCALE[locale].replace("-", "_"),
      type: "website",
    },
  };
}

const NAV = [
  { href: "#vi-sao", key: "why" },
  { href: "#cach-hoat-dong", key: "how" },
  { href: "#bang-30-dem", key: "board" },
  { href: "#ban-tin", key: "brief" },
  { href: "#hoi-dap", key: "faq" },
] as const;

const STEPS = ["calendar", "nights", "compare", "brief", "rescan"] as const;

const CONFIDENCE = ["exact", "capped", "hidden", "sold_out"] as const;

const PRINCIPLES = [
  { icon: <IconEye />, key: "public" },
  { icon: <IconClock />, key: "pace" },
  { icon: <IconGlobe />, key: "market" },
  { icon: <IconArchive />, key: "archive" },
  { icon: <IconInfo />, key: "limits" },
] as const;

const FAQ = ["account", "accuracy", "hotels", "channels", "timing", "pms", "team", "pricing"] as const;

const COMPARE = [
  { key: "calm", left: 14 },
  { key: "hot", left: 2 },
] as const;

function ChannelIcon({ kind }: { kind: ContactChannel["kind"] }) {
  if (kind === "phone") return <IconPhone />;
  if (kind === "email") return <IconMail />;
  return <IconChat />;
}

function Ticks({ items }: { items: string[] }) {
  return (
    <ul className="lp-ticks">
      {items.map((t) => (
        <li key={t}>
          <IconTick /> {t}
        </li>
      ))}
    </ul>
  );
}

const b = (c: ReactNode) => <b>{c}</b>;

export default async function LandingPage() {
  const [t, tc, fmt, cookieStore] = await Promise.all([getTranslations("landing"), getTranslations("landing.contact"), getFmt(), cookies()]);
  const signedIn = cookieStore.has("sb_session");
  const startISO = todayInVietnam();
  const channels = contactChannels(tc);
  const loginHref = signedIn ? "/dashboard" : "/login";
  const loginLabel = signedIn ? t("toDashboard") : t("login");
  const nav = NAV.map((n) => ({ href: n.href, label: t(`nav.${n.key}`) }));

  return (
    <>
      <a className="lp-skip" href="#noi-dung">
        {t("skip")}
      </a>

      <header className="lp-nav">
        <div className="lp-nav-inner">
          <Link href="/" aria-label={t("homeLink")} className="lp-nav-logo">
            <Wordmark />
          </Link>
          <nav aria-label={t("sectionsNav")} className="lp-nav-links">
            {nav.map((n) => (
              <a key={n.href} href={n.href}>
                {n.label}
              </a>
            ))}
          </nav>
          <div className="lp-nav-actions">
            <LocaleSwitcher variant="onDark" className="lp-locale" />
            <NavMenu items={[...nav, { href: "#lien-he", label: t("contactUs") }, { href: loginHref, label: loginLabel }]} />
            <a href="#lien-he" className="lp-btn-outline">
              <IconChat /> {t("contactUs")}
            </a>
            <Link href={loginHref} className="lp-nav-login">
              <IconUser />
              <span>{loginLabel}</span>
            </Link>
          </div>
        </div>
      </header>

      <main id="noi-dung">
        <section className="lp-hero" aria-labelledby="hero-title">
          <div className="lp-hero-inner">
            <div className="lp-hero-copy">
              <p className="lp-eyebrow">{t("hero.eyebrow")}</p>
              <h1 id="hero-title" className="lp-h1">
                {t("hero.title")}
              </h1>
              <Ticks items={[t("hero.ticks.rates"), t("hero.ticks.events"), t("hero.ticks.brief")]} />
              <p className="lp-price">
                {t.rich("hero.price", { strong: (c) => <strong>{c}</strong>, span: (c) => <span>{c}</span> })}
              </p>
              <div className="lp-hero-actions">
                <a href="#lien-he" className="lp-btn lp-btn-lg">
                  {t("contactUs")}
                </a>
                <a href="#bang-30-dem" className="lp-btn-ghost">
                  {t("hero.sample")} <IconArrow />
                </a>
              </div>
              <p className="lp-assure">
                <IconShield /> {t("hero.assure")}
              </p>
            </div>
            <div className="lp-hero-art">
              <HeroVisual startISO={startISO} />
            </div>
          </div>

          <ul className="lp-trust" aria-label={t("hero.trustLabel")}>
            <li>{t.rich("hero.trust.scans", { b })}</li>
            <li>{t.rich("hero.trust.nights", { b })}</li>
            <li>{t.rich("hero.trust.events", { b })}</li>
            <li>{t.rich("hero.trust.channels", { b })}</li>
          </ul>
        </section>

        <section id="vi-sao" className="lp-section lp-soft" aria-labelledby="why-title">
          <div className="lp-wrap">
            <header className="lp-head">
              <h2 id="why-title" className="lp-h2">
                {t("why.title")}
              </h2>
              <p>{t("why.lead")}</p>
            </header>

            <div className="lp-compare">
              {COMPARE.map((c) => (
                <article key={c.key} className="lp-card lp-compare-card" data-tone={c.key}>
                  <div className="lp-compare-top">
                    <span className="lp-compare-name">{t(`why.${c.key}.name`)}</span>
                    <span className="lp-compare-badge">{t(`why.${c.key}.badge`)}</span>
                  </div>
                  <p className="lp-compare-price">
                    {fmt.fmtMoney(1_200_000, "VND")} <span>{t("why.perNight")}</span>
                  </p>
                  <div className="lp-compare-rooms" aria-label={t("why.roomsLabel", { left: c.left, total: 16 })}>
                    {Array.from({ length: 16 }, (_, i) => (
                      <i key={i} data-open={i < c.left} />
                    ))}
                  </div>
                  <p className="lp-compare-note">{t.rich(`why.${c.key}.note`, { count: c.left, b })}</p>
                </article>
              ))}
            </div>

            <div className="lp-conf-block">
              <h3 className="lp-h3">{t("why.confidenceTitle")}</h3>
              <ul className="lp-card lp-legend-band">
                {CONFIDENCE.map((kind) => (
                  <li key={kind}>
                    <ConfidenceSwatch kind={kind} className="lp-swatch-lg" />
                    <div>
                      <h4>{t(`why.confidence.${kind}.name`)}</h4>
                      <p>{t(`why.confidence.${kind}.text`)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section id="cach-hoat-dong" className="lp-section lp-white" aria-labelledby="steps-title">
          <div className="lp-wrap">
            <header className="lp-head">
              <h2 id="steps-title" className="lp-h2">
                {t("steps.title")}
              </h2>
              <p>{t("steps.lead")}</p>
            </header>
            <ol className="lp-rail">
              {STEPS.map((st, i) => (
                <li key={st}>
                  <span className="lp-rail-time">{t(`steps.${st}.time`)}</span>
                  <span className="lp-rail-stop">{i + 1}</span>
                  <div className="lp-rail-body">
                    <h3>{t(`steps.${st}.title`)}</h3>
                    <p>{t(`steps.${st}.text`)}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="bang-30-dem" className="lp-section lp-soft" aria-labelledby="board-title">
          <div className="lp-wrap">
            <header className="lp-head">
              <h2 id="board-title" className="lp-h2">
                {t("boardSection.title")}
              </h2>
              <p>{t("boardSection.lead")}</p>
            </header>
            <MarketBoard startISO={startISO} />
            <p className="lp-note lp-center">{t("boardSection.note")}</p>
          </div>
        </section>

        <section id="ban-tin" className="lp-section lp-dark" aria-labelledby="brief-title">
          <div className="lp-wrap lp-split">
            <div className="lp-split-copy">
              <h2 id="brief-title" className="lp-h2">
                {t("briefSection.title")}
              </h2>
              <p>{t("briefSection.lead")}</p>
              <Ticks
                items={[t("briefSection.ticks.cite"), t("briefSection.ticks.dropped"), t("briefSection.ticks.onDemand")]}
              />
            </div>
            <div className="lp-brief-stage">
              <PhotoFrame photo={PHOTOS.coffee} sizes="(min-width: 1000px) 360px, 60vw" className="lp-brief-photo" />
              <BriefSheet startISO={startISO} />
              <p className="lp-note">{t("briefSection.note")}</p>
            </div>
          </div>
        </section>

        <section className="lp-section lp-white" aria-labelledby="pms-title">
          <div className="lp-wrap lp-split lp-split-pms">
            <div className="lp-split-copy">
              <h2 id="pms-title" className="lp-h2">
                {t("pms.title")}
              </h2>
              <p>{t("pms.lead")}</p>
              <Ticks items={[t("pms.ticks.mapping"), t("pms.ticks.errors"), t("pms.ticks.reimport")]} />
              <PhotoFrame
                photo={PHOTOS.desk}
                sizes="(min-width: 1000px) 480px, 100vw"
                className="lp-pms-photo"
                position="50% 32%"
              />
            </div>
            <div className="lp-pms-figure">
              <div className="lp-card lp-chart-card">
                <PmsChart startISO={startISO} />
              </div>
              <div className="lp-card lp-import" aria-label={t("pms.importLabel")}>
                <p className="lp-import-head">
                  <span>{t("pms.importTitle")}</span>
                  <span>{t("pms.importFile")}</span>
                </p>
                <p className="lp-import-sum">{t.rich("pms.importSummary", { b })}</p>
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{t("pms.colRow")}</th>
                      <th scope="col">{t("pms.colDate")}</th>
                      <th scope="col">{t("pms.colError")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>14</td>
                      <td>08/10</td>
                      <td>{t("pms.rowError")}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section lp-soft" aria-labelledby="principles-title">
          <div className="lp-wrap">
            <div className="lp-banner">
              <PhotoFrame photo={PHOTOS.windows} sizes="(min-width: 1240px) 1240px, 100vw" className="lp-banner-photo" />
              <p className="lp-banner-text">
                {t("principles.bannerLine1")}
                <br />
                {t("principles.bannerLine2")}
              </p>
            </div>

            <header className="lp-head">
              <h2 id="principles-title" className="lp-h2">
                {t("principles.title")}
              </h2>
              <p>{t("principles.lead")}</p>
            </header>
            <div className="lp-principles">
              <PhotoFrame
                photo={PHOTOS.key}
                sizes="(min-width: 1000px) 440px, 100vw"
                className="lp-principles-photo"
                position="50% 40%"
              />
              <ul className="lp-principles-list">
                {PRINCIPLES.map((p) => (
                  <li key={p.key}>
                    <h3>
                      <span className="lp-feature-icon">{p.icon}</span>
                      {t(`principles.${p.key}.title`)}
                    </h3>
                    <p>{t(`principles.${p.key}.text`)}</p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section id="hoi-dap" className="lp-section lp-white" aria-labelledby="faq-title">
          <div className="lp-wrap lp-faq">
            <header className="lp-head">
              <h2 id="faq-title" className="lp-h2">
                {t("faq.title")}
              </h2>
            </header>
            <div className="lp-faq-list">
              {FAQ.map((f) => (
                <details key={f}>
                  <summary>
                    <span>{t(`faq.${f}.q`)}</span>
                    <IconChevron />
                  </summary>
                  <p>{t(`faq.${f}.a`)}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section id="lien-he" className="lp-section lp-soft lp-cta-section" aria-labelledby="cta-title">
          <div className="lp-wrap">
            <div className="lp-cta">
              <div className="lp-cta-copy">
                <h2 id="cta-title" className="lp-h2">
                  {t("cta.title")}
                </h2>
                <p>{t("cta.lead")}</p>
                <ol className="lp-cta-steps">
                  <li>{t.rich("cta.steps.send", { b })}</li>
                  <li>{t.rich("cta.steps.setup", { b })}</li>
                  <li>{t.rich("cta.steps.read", { b })}</li>
                </ol>
              </div>
              <div className="lp-cta-side">
                {channels.length > 0 ? (
                  <ul className="lp-channels">
                    {channels.map((c) => (
                      <li key={c.kind}>
                        <a
                          href={c.href}
                          className="lp-channel"
                          target={c.kind === "zalo" ? "_blank" : undefined}
                          rel="noreferrer"
                        >
                          <span className="lp-channel-icon">
                            <ChannelIcon kind={c.kind} />
                          </span>
                          <span className="lp-channel-text">
                            <span className="lp-channel-label">{c.label}</span>
                            <span className="lp-channel-value">
                              {c.kind === "email" && c.value.includes("@") ? (
                                <>
                                  {c.value.split("@")[0]}@<wbr />
                                  {c.value.split("@")[1]}
                                </>
                              ) : (
                                c.value
                              )}
                            </span>
                          </span>
                          <IconArrow className="lp-channel-arrow" />
                        </a>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="lp-channels-empty">{t("cta.empty")}</p>
                )}
              </div>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-wrap">
          <div className="lp-footer-top">
            <div className="lp-footer-brand">
              <Wordmark />
              <p>{t("footer.tagline")}</p>
            </div>
            <nav aria-label={t("footer.linksLabel")} className="lp-footer-links">
              {nav.map((n) => (
                <a key={n.href} href={n.href}>
                  {n.label}
                </a>
              ))}
              <a href="#lien-he">{t("footer.contact")}</a>
              <Link href={loginHref}>{loginLabel}</Link>
            </nav>
          </div>
          <div className="lp-footer-fine">
            <p>{t("footer.disclaimer")}</p>
            <p>
              {t.rich("footer.credits", {
                list: () =>
                  Object.values(PHOTOS).map((p, i, all) => (
                    <span key={p.src}>
                      <a href={p.creditUrl} rel="noreferrer" target="_blank">
                        {p.credit}
                      </a>
                      {i < all.length - 1 ? ", " : ""}
                    </span>
                  )),
              })}
            </p>
          </div>
        </div>
      </footer>
    </>
  );
}
