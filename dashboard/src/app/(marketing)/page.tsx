import type { Metadata } from "next";
import { cookies } from "next/headers";
import Link from "next/link";
import type { ReactNode } from "react";
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

export const metadata: Metadata = {
  title: { absolute: "ScrapeBooking · Theo dõi phòng còn và giá đối thủ trên Booking.com" },
  description:
    "ScrapeBooking đọc trang Booking.com của khách sạn bạn và đối thủ ba lần mỗi ngày, ghi lại số phòng còn và giá cho từng đêm trong 30 ngày tới, rồi gửi bản tin buổi sáng có bằng chứng.",
  openGraph: {
    title: "ScrapeBooking · Biết đối thủ còn mấy phòng trước khi bạn đặt giá",
    description: "Phòng còn và giá của đối thủ trên Booking.com, ba lần mỗi ngày, 30 đêm phía trước.",
    locale: "vi_VN",
    type: "website",
  },
};

const NAV = [
  { href: "#vi-sao", label: "Vì sao" },
  { href: "#cach-hoat-dong", label: "Cách hoạt động" },
  { href: "#bang-30-dem", label: "Bảng 30 đêm" },
  { href: "#ban-tin", label: "Bản tin AI" },
  { href: "#hoi-dap", label: "Hỏi đáp" },
];

const STEPS = [
  {
    time: "06:00",
    title: "Mở lịch 30 ngày",
    text: "Đọc lịch của từng khách sạn trước: đêm nào còn bán, đêm nào bắt ở tối thiểu mấy đêm. Đêm đã đóng không cần tải trang.",
  },
  {
    time: "Ngay sau đó",
    title: "Đọc từng đêm",
    text: "Tải trang cho từng đêm với đúng số đêm tối thiểu, ghi từng loại phòng, số phòng còn, giá, hoàn huỷ và bữa sáng.",
  },
  {
    time: "Khi lượt quét xong",
    title: "Đối chiếu lần trước",
    text: "So với lần quan sát dùng được gần nhất để tìm hết phòng, có phòng lại, giảm phòng và đổi giá từ 3% trở lên.",
  },
  {
    time: "07:30",
    title: "Bản tin buổi sáng",
    text: "Tóm tắt thị trường, tín hiệu cầu, cơ hội giá và rủi ro, mỗi nhận định bấm được tới số liệu gốc.",
  },
  {
    time: "14:00 · 22:00",
    title: "Quét thêm hai vòng",
    text: "Bắt kịp những đêm đang bán nhanh. Giờ quét, số mốc trong ngày và số đêm theo dõi đổi được theo múi giờ của bạn.",
  },
];

const CONFIDENCE = [
  { kind: "exact" as const, name: "Chính xác", text: "Trang hiện “Chỉ còn 2 phòng”. Con số đúng, dùng để tính tốc độ bán." },
  { kind: "capped" as const, name: "Ít nhất", text: "Ô chọn số phòng chạm trần của trang. Biết chắc còn từ mức đó trở lên." },
  { kind: "hidden" as const, name: "Ẩn", text: "Còn phòng nhưng trang không để lộ số. Ghi nhận là còn, không đoán thêm." },
  {
    kind: "sold_out" as const,
    name: "Hết phòng",
    text: "Loại phòng biến mất hoặc báo hết. Lịch được đọc trước để không nhầm với ràng buộc số đêm tối thiểu.",
  },
];

const PRINCIPLES: { icon: ReactNode; title: string; text: string }[] = [
  {
    icon: <IconEye />,
    title: "Chỉ đọc trang công khai",
    text: "Không đăng nhập Booking.com, không dùng tài khoản extranet của bạn, không lấy dữ liệu cá nhân của khách lưu trú.",
  },
  {
    icon: <IconClock />,
    title: "Nhịp độ chừng mực",
    text: "Các lần tải trang được giãn cách vài giây, không dồn dập, và mỗi khách sạn chỉ được đọc lần lượt từng trang.",
  },
  {
    icon: <IconGlobe />,
    title: "Giá đúng thị trường",
    text: "Xem trang như một khách ở nước của khách sạn. Giá giữ nguyên tiền tệ hiển thị, không quy đổi.",
  },
  {
    icon: <IconArchive />,
    title: "Giữ bản gốc",
    text: "Trang gốc được lưu lại một thời gian (mặc định 30 ngày). Khi Booking.com đổi giao diện, dữ liệu được đọc lại thay vì mất.",
  },
  {
    icon: <IconInfo />,
    title: "Nói rõ giới hạn",
    text: "Hiện chỉ theo dõi Booking.com. Mỗi lượt xem giả định 2 người lớn, nên loại phòng dành cho 1 người không xuất hiện.",
  },
];

const FAQ = [
  {
    q: "ScrapeBooking có cần tài khoản Booking.com của tôi không?",
    a: "Không. Hệ thống chỉ đọc trang công khai mà khách đặt phòng nào cũng thấy. Tài khoản extranet của bạn không liên quan.",
  },
  {
    q: "Số phòng còn lại chính xác đến đâu?",
    a: "Booking.com chỉ hiện con số chính xác khi còn ít phòng. Vì vậy mỗi con số trên ScrapeBooking đi kèm mức tin cậy: chính xác, ít nhất, ẩn hoặc hết. Tốc độ bán chỉ được tính từ các cặp số chính xác.",
  },
  {
    q: "Tôi theo dõi được những khách sạn nào?",
    a: "Bất kỳ khách sạn nào có trang trên Booking.com: dán đường link là thêm vào danh sách. Khách sạn của bạn nằm cùng danh sách để luôn được đặt cạnh đối thủ.",
  },
  { q: "Có theo dõi Agoda hay Expedia không?", a: "Hiện tại chỉ Booking.com." },
  {
    q: "Bao lâu thì có dữ liệu?",
    a: "Lượt quét đầu tiên chạy ngay khi thiết lập xong. Sự kiện như hết phòng hay đổi giá xuất hiện từ lượt quét thứ hai, và bản tin đến mỗi sáng lúc 07:30.",
  },
  {
    q: "Có bắt buộc kết nối PMS không?",
    a: "Không. Không có PMS bạn vẫn thấy đầy đủ dữ liệu đối thủ. Nhập file từ PMS giúp đặt công suất thật của bạn cạnh thị trường, cả trên bảng lẫn trong bản tin.",
  },
  {
    q: "Cả đội dùng chung được không?",
    a: "Được. Tài khoản quản trị cấu hình danh sách theo dõi, giờ quét và nhập PMS; tài khoản chỉ xem dành cho người cần đọc số liệu.",
  },
  { q: "Chi phí thế nào?", a: "Liên hệ để nhận báo giá phù hợp với khách sạn của bạn." },
];

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

export default async function LandingPage() {
  const signedIn = (await cookies()).has("sb_session");
  const startISO = todayInVietnam();
  const channels = contactChannels();
  const loginHref = signedIn ? "/overview" : "/login";
  const loginLabel = signedIn ? "Vào dashboard" : "Đăng nhập";

  return (
    <>
      <a className="lp-skip" href="#noi-dung">
        Bỏ qua tới nội dung
      </a>

      <header className="lp-nav">
        <div className="lp-nav-inner">
          <Link href="/" aria-label="ScrapeBooking, trang chủ" className="lp-nav-logo">
            <Wordmark />
          </Link>
          <nav aria-label="Mục trên trang" className="lp-nav-links">
            {NAV.map((n) => (
              <a key={n.href} href={n.href}>
                {n.label}
              </a>
            ))}
          </nav>
          <div className="lp-nav-actions">
            <NavMenu items={[...NAV, { href: "#lien-he", label: "Liên hệ tư vấn" }, { href: loginHref, label: loginLabel }]} />
            <a href="#lien-he" className="lp-btn-outline">
              <IconChat /> Liên hệ tư vấn
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
              <p className="lp-eyebrow">Theo dõi đối thủ khách sạn</p>
              <h1 id="hero-title" className="lp-h1">
                Biết đối thủ còn mấy phòng trước khi bạn đặt giá
              </h1>
              <Ticks
                items={[
                  "Phòng còn và giá của đối thủ trên Booking.com, 3 lần mỗi ngày",
                  "Báo hết phòng, có phòng lại, đổi giá cho từng đêm trong 30 ngày tới",
                  "Bản tin AI lúc 07:30, mỗi nhận định đều kèm bằng chứng",
                ]}
              />
              <p className="lp-price">
                <strong>Liên hệ báo giá</strong>
                <span>, chúng tôi thiết lập cùng bạn</span>
              </p>
              <div className="lp-hero-actions">
                <a href="#lien-he" className="lp-btn lp-btn-lg">
                  Liên hệ tư vấn
                </a>
                <a href="#bang-30-dem" className="lp-btn-ghost">
                  Xem bảng mẫu <IconArrow />
                </a>
              </div>
              <p className="lp-assure">
                <IconShield /> Không cần tài khoản Booking.com của bạn, không cần cài phần mềm
              </p>
            </div>
            <div className="lp-hero-art">
              <HeroVisual startISO={startISO} />
            </div>
          </div>

          <ul className="lp-trust" aria-label="Thông số dịch vụ">
            <li>
              <b>3 lượt quét</b> mỗi ngày
            </li>
            <li>
              <b>30 đêm</b> phía trước, theo từng loại phòng
            </li>
            <li>
              <b>9 loại sự kiện</b> giữa hai lượt quét
            </li>
            <li>
              Dữ liệu công khai từ <b>Booking.com</b>
            </li>
          </ul>
        </section>

        <section id="vi-sao" className="lp-section lp-soft" aria-labelledby="why-title">
          <div className="lp-wrap">
            <header className="lp-head">
              <h2 id="why-title" className="lp-h2">
                Giá chỉ kể một nửa câu chuyện
              </h2>
              <p>
                Hai khách sạn cùng để giá 1,2 triệu cho đêm thứ Bảy. Một nơi còn 14 phòng, nơi kia còn 2. Chỉ nhìn giá, bạn
                không biết thị trường đang nóng hay đang chậm. ScrapeBooking đếm phòng còn rồi mới đặt giá bên cạnh.
              </p>
            </header>

            <div className="lp-compare">
              {[
                { name: "Khách sạn A", left: 14, note: "Cầu còn chậm, đối thủ có thể sớm giảm giá", tone: "calm" },
                { name: "Khách sạn B", left: 2, note: "Sắp kín, đây là đêm bạn có thể giữ hoặc tăng giá", tone: "hot" },
              ].map((c) => (
                <article key={c.name} className="lp-card lp-compare-card" data-tone={c.tone}>
                  <div className="lp-compare-top">
                    <span className="lp-compare-name">{c.name}</span>
                    <span className="lp-compare-badge">{c.tone === "hot" ? "Chỉ còn 2 phòng" : "Còn nhiều phòng"}</span>
                  </div>
                  <p className="lp-compare-price">
                    1.200.000 ₫ <span>/ đêm thứ Bảy</span>
                  </p>
                  <div className="lp-compare-rooms" aria-label={`Còn ${c.left} trên 16 phòng`}>
                    {Array.from({ length: 16 }, (_, i) => (
                      <i key={i} data-open={i < c.left} />
                    ))}
                  </div>
                  <p className="lp-compare-note">
                    <b>Còn {c.left} phòng.</b> {c.note}
                  </p>
                </article>
              ))}
            </div>

            <div className="lp-conf-block">
              <h3 className="lp-h3">Booking.com không công bố số phòng. Chúng tôi nói rõ mình biết chắc tới đâu.</h3>
              <ul className="lp-card lp-legend-band">
                {CONFIDENCE.map((c) => (
                  <li key={c.kind}>
                    <ConfidenceSwatch kind={c.kind} className="lp-swatch-lg" />
                    <div>
                      <h4>{c.name}</h4>
                      <p>{c.text}</p>
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
                Mỗi ngày ba vòng quanh thị trường
              </h2>
              <p>
                Quy trình chạy đúng thứ tự ở mọi lượt quét. Mỗi bước chỉ dùng kết quả của bước trước, nên số liệu nào trên
                bảng cũng truy ngược được về trang gốc.
              </p>
            </header>
            <ol className="lp-rail">
              {STEPS.map((st, i) => (
                <li key={st.title}>
                  <span className="lp-rail-time">{st.time}</span>
                  <span className="lp-rail-stop">{i + 1}</span>
                  <div className="lp-rail-body">
                    <h3>{st.title}</h3>
                    <p>{st.text}</p>
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
                Ba mươi đêm tới trên một tấm bảng
              </h2>
              <p>
                Khách sạn của bạn ở hàng trên cùng, đối thủ bên dưới, dải compset ở cuối. Bấm vào một ô để xem từng loại
                phòng, giá và các lượt quan sát trước.
              </p>
            </header>
            <MarketBoard startISO={startISO} />
            <p className="lp-note lp-center">Bảng minh hoạ với khách sạn và số liệu giả định, dựng theo đúng cách dashboard hiển thị.</p>
          </div>
        </section>

        <section id="ban-tin" className="lp-section lp-dark" aria-labelledby="brief-title">
          <div className="lp-wrap lp-split">
            <div className="lp-split-copy">
              <h2 id="brief-title" className="lp-h2">
                Bản tin 07:30 chỉ nói điều dữ liệu chứng minh được
              </h2>
              <p>
                Mỗi sáng, dữ liệu của lượt quét gần nhất được gom lại cùng sự kiện 24 giờ và 7 ngày qua, chỉ số compset, công
                suất PMS và ngày lễ, rồi gửi cho mô hình AI viết bản tin.
              </p>
              <Ticks
                items={[
                  "Mỗi nhận định phải trích sự kiện hoặc chỉ số có thật",
                  "Nhận định thiếu bằng chứng bị loại và ghi lại để bạn xem",
                  "Cần gấp, bạn tạo bản tin mới ngay trên dashboard",
                ]}
              />
            </div>
            <div className="lp-brief-stage">
              <PhotoFrame photo={PHOTOS.coffee} sizes="(min-width: 1000px) 360px, 60vw" className="lp-brief-photo" />
              <BriefSheet startISO={startISO} />
              <p className="lp-note">Bản tin mẫu, dựng từ dữ liệu minh hoạ ở bảng phía trên.</p>
            </div>
          </div>
        </section>

        <section className="lp-section lp-white" aria-labelledby="pms-title">
          <div className="lp-wrap lp-split lp-split-pms">
            <div className="lp-split-copy">
              <h2 id="pms-title" className="lp-h2">
                Đặt công suất thật của bạn cạnh thị trường
              </h2>
              <p>
                Nhập file CSV hoặc Excel xuất từ PMS, ezCloud, Newway hay hệ thống nào cũng được. Đêm đối thủ kín dần mà bạn
                còn nhiều phòng là đêm nên giữ giá, thay vì bán rẻ những phòng cuối cùng.
              </p>
              <Ticks
                items={[
                  "Ánh xạ cột một lần, lần sau chỉ cần tải file lên",
                  "Báo lỗi từng dòng: sai ngày, trùng ngày, bán vượt tổng phòng",
                  "Nhập lại không nhân đôi dữ liệu",
                ]}
              />
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
              <div className="lp-card lp-import" aria-label="Kết quả nhập file PMS (minh hoạ)">
                <p className="lp-import-head">
                  <span>Kết quả nhập PMS</span>
                  <span>cong-suat-thang-10.xlsx</span>
                </p>
                <p className="lp-import-sum">
                  <b>30/31 dòng hợp lệ</b>, công suất 30 đêm đã được cập nhật.
                </p>
                <table>
                  <thead>
                    <tr>
                      <th scope="col">Dòng</th>
                      <th scope="col">Ngày</th>
                      <th scope="col">Lỗi</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>14</td>
                      <td>08/10</td>
                      <td>Số phòng bán (62) lớn hơn tổng số phòng (60)</td>
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
                Mỗi ô cửa sáng là một phòng chưa bán.
                <br />
                Chúng tôi đếm chúng, ba lần mỗi ngày.
              </p>
            </div>

            <header className="lp-head">
              <h2 id="principles-title" className="lp-h2">
                Thu thập chừng mực, minh bạch từng con số
              </h2>
              <p>Những nguyên tắc chúng tôi giữ khi đọc dữ liệu công khai cho bạn.</p>
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
                  <li key={p.title}>
                    <h3>
                      <span className="lp-feature-icon">{p.icon}</span>
                      {p.title}
                    </h3>
                    <p>{p.text}</p>
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
                Câu hỏi thường gặp
              </h2>
            </header>
            <div className="lp-faq-list">
              {FAQ.map((f) => (
                <details key={f.q}>
                  <summary>
                    <span>{f.q}</span>
                    <IconChevron />
                  </summary>
                  <p>{f.a}</p>
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
                  Gửi cho chúng tôi link Booking.com của bạn
                </h2>
                <p>
                  Kèm vài đối thủ bạn hay so sánh. Chúng tôi thiết lập danh sách theo dõi, chạy lượt quét đầu tiên và cho bạn
                  xem 30 đêm tới của thị trường.
                </p>
                <ol className="lp-cta-steps">
                  <li>
                    <b>Gửi link</b> khách sạn của bạn và các đối thủ
                  </li>
                  <li>
                    <b>Chúng tôi thiết lập</b> tài khoản và giờ quét theo múi giờ của bạn
                  </li>
                  <li>
                    <b>Đọc bản tin</b> mỗi sáng lúc 07:30
                  </li>
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
                  <p className="lp-channels-empty">Thông tin liên hệ đang được cập nhật.</p>
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
              <p>Theo dõi phòng còn và giá đối thủ trên Booking.com cho khách sạn Việt Nam.</p>
            </div>
            <nav aria-label="Liên kết chân trang" className="lp-footer-links">
              {NAV.map((n) => (
                <a key={n.href} href={n.href}>
                  {n.label}
                </a>
              ))}
              <a href="#lien-he">Liên hệ</a>
              <Link href={loginHref}>{loginLabel}</Link>
            </nav>
          </div>
          <div className="lp-footer-fine">
            <p>ScrapeBooking là dịch vụ độc lập, không liên kết với Booking.com. Booking.com là nhãn hiệu của Booking.com B.V.</p>
            <p>
              Ảnh:{" "}
              {Object.values(PHOTOS).map((p, i, all) => (
                <span key={p.src}>
                  <a href={p.creditUrl} rel="noreferrer" target="_blank">
                    {p.credit}
                  </a>
                  {i < all.length - 1 ? ", " : ""}
                </span>
              ))}{" "}
              trên Unsplash.
            </p>
          </div>
        </div>
      </footer>
    </>
  );
}
