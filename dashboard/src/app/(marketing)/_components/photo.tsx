import { useTranslations } from "next-intl";
import Image from "next/image";
import type { Messages } from "@/messages";

export type Photo = {
  src: string;
  width: number;
  height: number;
  alt: keyof Messages["landing"]["photos"];
  credit: string;
  creditUrl: string;
};

/** Ảnh chụp bo góc, màu thật. */
export function PhotoFrame({
  photo,
  sizes,
  className,
  position,
  priority,
}: {
  photo: Photo;
  sizes: string;
  className?: string;
  position?: string;
  priority?: boolean;
}) {
  const t = useTranslations("landing.photos");
  return (
    <div className={`lp-photo ${className ?? ""}`}>
      <Image
        src={photo.src}
        alt={t(photo.alt)}
        width={photo.width}
        height={photo.height}
        sizes={sizes}
        priority={priority}
        style={position ? { objectPosition: position } : undefined}
      />
    </div>
  );
}
