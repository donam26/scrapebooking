import type { ReactNode, SVGProps } from "react";
import type { Confidence } from "./demo-data";

/** Logo: mặt tiền 3×2 ô cửa, hai ô sáng, cạnh chữ SCRAPEBOOKING. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={`lp-logo ${className ?? ""}`}>
      <svg viewBox="0 0 28 28" aria-hidden="true" className="lp-logo-mark">
        <rect x="1" y="1" width="26" height="26" rx="7" className="lp-logo-bg" />
        {[0, 1, 2].map((c) =>
          [0, 1].map((r) => (
            <rect
              key={`${c}${r}`}
              x={6.5 + c * 5.5}
              y={8 + r * 6.5}
              width="4"
              height="4.5"
              rx="1"
              className={(c === 1 && r === 0) || (c === 2 && r === 1) ? "lp-logo-lit" : "lp-logo-dark"}
            />
          )),
        )}
      </svg>
      <span>SCRAPEBOOKING</span>
    </span>
  );
}

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const IconTick = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4.5 12.5l4.5 4.5L19.5 6.5" />
  </Icon>
);
export const IconPhone = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 4.5h3.2l1.6 4-2 1.3a10.5 10.5 0 0 0 6.4 6.4l1.3-2 4 1.6V19a1.5 1.5 0 0 1-1.6 1.5A16 16 0 0 1 3.5 6.1 1.5 1.5 0 0 1 5 4.5z" />
  </Icon>
);
export const IconChat = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4A1.5 1.5 0 0 1 4 14.5z" />
    <path d="M8.5 10h7" />
  </Icon>
);
export const IconMail = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="5.5" width="17" height="13" rx="2" />
    <path d="M4 7l8 6 8-6" />
  </Icon>
);
export const IconArrow = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
);
export const IconChevron = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 9l6 6 6-6" />
  </Icon>
);
export const IconShield = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.5l7 2.8v5.2c0 4.3-2.9 7.6-7 9-4.1-1.4-7-4.7-7-9V6.3z" />
    <path d="M9 12l2.2 2.2L15.5 10" />
  </Icon>
);
export const IconUser = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="8.5" r="3.5" />
    <path d="M5 20c1.2-3.4 4-5 7-5s5.8 1.6 7 5" />
  </Icon>
);
export const IconSpark = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.5l1.8 5 5 1.8-5 1.8-1.8 5-1.8-5-5-1.8 5-1.8z" />
    <path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" />
  </Icon>
);
export const IconChart = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 20V5M4 20h16" />
    <path d="M8 16v-4M12 16V8M16 16v-6" />
  </Icon>
);
export const IconBell = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 1.5H5z" />
    <path d="M10 20.5a2 2 0 0 0 4 0" />
  </Icon>
);
export const IconSearch = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="6" />
    <path d="M20 20l-4.5-4.5" />
  </Icon>
);
export const IconCalendar = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="5" width="17" height="15" rx="2.5" />
    <path d="M3.5 10h17M8 3v4M16 3v4" />
  </Icon>
);
export const IconEye = (p: IconProps) => (
  <Icon {...p}>
    <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
    <circle cx="12" cy="12" r="2.8" />
  </Icon>
);
export const IconClock = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Icon>
);
export const IconGlobe = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M3.5 12h17M12 3.5c2.4 2.4 3.5 5.2 3.5 8.5s-1.1 6.1-3.5 8.5c-2.4-2.4-3.5-5.2-3.5-8.5s1.1-6.1 3.5-8.5z" />
  </Icon>
);
export const IconArchive = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="4.5" width="17" height="5" rx="1.5" />
    <path d="M5 9.5V18a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9.5M10 13.5h4" />
  </Icon>
);
export const IconInfo = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5.5M12 7.8v.2" />
  </Icon>
);
export const IconFile = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 3.5h7l4.5 4.5v11a1.5 1.5 0 0 1-1.5 1.5H7A1.5 1.5 0 0 1 5.5 19V5A1.5 1.5 0 0 1 7 3.5z" />
    <path d="M13.5 3.5V8.5h5M9 13h6M9 16.5h4" />
  </Icon>
);

/** Mẫu ô mức tin cậy, dùng chung cho chú giải và bảng. */
export function ConfidenceSwatch({ kind, className }: { kind: Confidence | "unknown"; className?: string }) {
  return <span className={`lp-swatch lp-swatch-${kind} ${className ?? ""}`} aria-hidden="true" />;
}
