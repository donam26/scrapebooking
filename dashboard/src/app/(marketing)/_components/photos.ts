import type { Photo } from "./photo";

/** Ảnh Unsplash (giấy phép Unsplash, miễn phí) đã tải về public/landing; nguồn ghi ở README cùng thư mục. */
export const PHOTOS = {
  coffee: {
    src: "/landing/morning-coffee.webp",
    width: 900,
    height: 900,
    alt: "coffee",
    credit: "Tu Tran Anh",
    creditUrl: "https://unsplash.com/photos/-_Ae-vtB_5o",
  },
  windows: {
    src: "/landing/lit-windows.webp",
    width: 2400,
    height: 1600,
    alt: "windows",
    credit: "Jahanzeb Ahsan",
    creditUrl: "https://unsplash.com/photos/jlXe75DNvfA",
  },
  desk: {
    src: "/landing/front-desk.webp",
    width: 1100,
    height: 1650,
    alt: "desk",
    credit: "Anh Tuan To",
    creditUrl: "https://unsplash.com/photos/EDgZMOGc8LQ",
  },
  key: {
    src: "/landing/room-key.webp",
    width: 1000,
    height: 1498,
    alt: "key",
    credit: "Monique Caraballo",
    creditUrl: "https://unsplash.com/photos/39MfQLJS7Jg",
  },
  coast: {
    src: "/landing/coastline.webp",
    width: 1600,
    height: 900,
    alt: "coast",
    credit: "Thach Tran",
    creditUrl: "https://unsplash.com/photos/w_0Dk0_JN3A",
  },
} satisfies Record<string, Photo>;
