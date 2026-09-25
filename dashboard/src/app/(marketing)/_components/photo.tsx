import Image from "next/image";

export type Photo = {
  src: string;
  width: number;
  height: number;
  alt: string;
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
  return (
    <div className={`lp-photo ${className ?? ""}`}>
      <Image
        src={photo.src}
        alt={photo.alt}
        width={photo.width}
        height={photo.height}
        sizes={sizes}
        priority={priority}
        style={position ? { objectPosition: position } : undefined}
      />
    </div>
  );
}
