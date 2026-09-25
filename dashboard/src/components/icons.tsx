import type { ReactNode, SVGProps } from "react";

/** Bộ icon nét 1.75 trên lưới 24, vẽ riêng cho dashboard (cùng ngữ pháp với icon trang giới thiệu). */
type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 18, children, ...props }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

/** Bảng ô: tổng quan khách sạn × đêm */
export const IconBoard = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="4" width="17" height="16" rx="2.5" />
    <path d="M3.5 9.5h17M9 9.5V20M14.5 9.5V20" />
  </Icon>
);
/** Tia: sự kiện biến động */
export const IconPulse = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 12h3.5l2.5-6 4 12 2.5-6H21" />
  </Icon>
);
/** Bản tin */
export const IconBrief = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 3.5h9l3.5 3.5v13.5H6z" />
    <path d="M14.5 3.5V7.5h4M9 11.5h6.5M9 15h6.5M9 18h4" />
  </Icon>
);
export const IconSliders = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
    <circle cx="15" cy="7" r="2" />
    <circle cx="9" cy="17" r="2" />
  </Icon>
);
export const IconBuilding = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 20.5V5a1.5 1.5 0 0 1 1.5-1.5h7A1.5 1.5 0 0 1 15 5v15.5M15 10h3.5a1.5 1.5 0 0 1 1.5 1.5v9M3 20.5h18" />
    <path d="M8.5 7.5h3M8.5 11h3M8.5 14.5h3" />
  </Icon>
);
export const IconUsers = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="9" cy="8.5" r="3.5" />
    <path d="M3 19.5c.8-3.2 3.2-5 6-5s5.2 1.8 6 5" />
    <path d="M15.5 5.2a3.5 3.5 0 0 1 0 6.6M17.5 14.8c1.8.6 3 2.2 3.5 4.7" />
  </Icon>
);
export const IconHeartbeat = (p: IconProps) => (
  <Icon {...p}>
    <path d="M20 9.5c0 5-8 10-8 10s-8-5-8-10a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 9.5z" />
    <path d="M7 12.5h2.5l1.5-2.5 2 4 1.5-1.5H17" />
  </Icon>
);
export const IconLogout = (p: IconProps) => (
  <Icon {...p}>
    <path d="M14 4.5H6.5A1.5 1.5 0 0 0 5 6v12a1.5 1.5 0 0 0 1.5 1.5H14" />
    <path d="M10 12h10M16.5 8.5 20 12l-3.5 3.5" />
  </Icon>
);
export const IconChevronDown = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 9l6 6 6-6" />
  </Icon>
);
export const IconChevronRight = (p: IconProps) => (
  <Icon {...p}>
    <path d="M9 6l6 6-6 6" />
  </Icon>
);
export const IconChevronLeft = (p: IconProps) => (
  <Icon {...p}>
    <path d="M15 6l-6 6 6 6" />
  </Icon>
);
export const IconArrowRight = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
);
export const IconArrowUp = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 19V5M6 11l6-6 6 6" />
  </Icon>
);
export const IconArrowDown = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M6 13l6 6 6-6" />
  </Icon>
);
export const IconExternal = (p: IconProps) => (
  <Icon {...p}>
    <path d="M14 4.5h5.5V10M19.5 4.5 11 13" />
    <path d="M18 14v4.5A1.5 1.5 0 0 1 16.5 20h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" />
  </Icon>
);
export const IconCalendar = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
    <path d="M3.5 10h17M8 3v4M16 3v4" />
  </Icon>
);
export const IconClock = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 2" />
  </Icon>
);
export const IconRefresh = (p: IconProps) => (
  <Icon {...p}>
    <path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3L19.5 9" />
    <path d="M19.5 4.5V9H15" />
  </Icon>
);
export const IconPlus = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);
export const IconClose = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
);
export const IconCheck = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4.5 12.5l4.5 4.5L19.5 6.5" />
  </Icon>
);
export const IconAlert = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4 21 19.5H3z" />
    <path d="M12 10v4.5M12 17.2v.1" />
  </Icon>
);
export const IconInfo = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5.5M12 7.8v.1" />
  </Icon>
);
export const IconUpload = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" />
    <path d="M4.5 14.5v3.5A2 2 0 0 0 6.5 20h11a2 2 0 0 0 2-2v-3.5" />
  </Icon>
);
export const IconDownload = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5" />
    <path d="M4.5 14.5v3.5A2 2 0 0 0 6.5 20h11a2 2 0 0 0 2-2v-3.5" />
  </Icon>
);
export const IconFile = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6.5 3.5h7.5l4.5 4.5v12.5h-12z" />
    <path d="M13.5 3.5V8.5h5" />
  </Icon>
);
export const IconSparkle = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3.5c.6 4.2 2.3 5.9 6.5 6.5-4.2.6-5.9 2.3-6.5 6.5-.6-4.2-2.3-5.9-6.5-6.5 4.2-.6 5.9-2.3 6.5-6.5z" />
    <path d="M18.5 15.5c.3 1.8 1 2.5 2.5 2.8-1.5.3-2.2 1-2.5 2.7-.3-1.7-1-2.4-2.5-2.7 1.5-.3 2.2-1 2.5-2.8z" />
  </Icon>
);
export const IconMenu = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Icon>
);
export const IconPencil = (p: IconProps) => (
  <Icon {...p}>
    <path d="M15.5 5 19 8.5 8.5 19H5v-3.5z" />
    <path d="M13 7.5l3.5 3.5" />
  </Icon>
);
export const IconPause = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M10 9v6M14 9v6" />
  </Icon>
);
export const IconPlay = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M10 8.8v6.4l5-3.2z" />
  </Icon>
);
export const IconKey = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="8" cy="14" r="3.5" />
    <path d="M10.5 11.5 19 3M16 6l2.5 2.5M13.5 8.5 16 11" />
  </Icon>
);
export const IconLock = (p: IconProps) => (
  <Icon {...p}>
    <rect x="5" y="10.5" width="14" height="9.5" rx="2" />
    <path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" />
  </Icon>
);
export const IconLink = (p: IconProps) => (
  <Icon {...p}>
    <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7L11.5 6.8" />
    <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.5-1.5" />
  </Icon>
);
export const IconStar = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4l2.4 5 5.4.6-4 3.7 1.1 5.3L12 16l-4.9 2.6 1.1-5.3-4-3.7 5.4-.6z" />
  </Icon>
);
export const IconSearch = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M20 20l-4.3-4.3" />
  </Icon>
);
export const IconFilter = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 5.5h16l-6 7.5v5.5l-4 1.5v-7z" />
  </Icon>
);
export const IconBed = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3.5 18.5V6M3.5 14.5h17v4M20.5 14.5V12a2.5 2.5 0 0 0-2.5-2.5h-7v5" />
    <circle cx="7" cy="11.5" r="1.8" />
  </Icon>
);

/** Logo: mặt tiền 3×2 ô cửa, hai ô sáng (cùng logo trang giới thiệu). */
export function BrandMark({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 28 28" width={size} height={size} aria-hidden="true" className={className}>
      <rect x="1" y="1" width="26" height="26" rx="7" fill="var(--sb-brand)" />
      {[0, 1, 2].map((c) =>
        [0, 1].map((r) => {
          const lit = (c === 1 && r === 0) || (c === 2 && r === 1);
          return (
            <rect
              key={`${c}${r}`}
              x={6.5 + c * 5.5}
              y={8 + r * 6.5}
              width="4"
              height="4.5"
              rx="1"
              fill={lit ? "var(--sb-exact)" : "#fff"}
              opacity={lit ? 1 : 0.9}
            />
          );
        }),
      )}
    </svg>
  );
}
