"""Ghi một trang kết quả tìm kiếm: khách sạn + listing kênh (`active`, quét được ngay không cần
verify), khách sạn của khu vực, giá trên thẻ.

Khách sạn dùng chung toàn hệ thống: thẻ nào đã có listing cùng kênh (cùng slug hoặc cùng id của
kênh) thì dùng khách sạn đó, không tạo trùng; thông tin định danh không ghi đè (như verify), chỉ
điểm/số review/ảnh/quận được làm mới theo lần thấy gần nhất.
"""

from datetime import datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Hotel, Listing
from app.logging import get_logger
from app.marketscan.models import MarketAreaHotel, MarketListPrice
from app.marketscan.parser import SearchCard

log = get_logger(__name__)


def _refresh(hotel: Hotel, card: SearchCard) -> None:
    if card.review_count is not None:
        hotel.review_count = card.review_count
        hotel.review_score = card.review_score
    hotel.image_url = card.image_url or hotel.image_url
    hotel.district = card.district or hotel.district
    hotel.name = hotel.name or card.name
    hotel.address = hotel.address or card.address
    hotel.city = hotel.city or card.city
    if hotel.lat is None and card.lat is not None:
        hotel.lat, hotel.lng = card.lat, card.lng
    if hotel.star_rating is None and card.stars is not None:
        hotel.star_rating = card.stars


async def _existing(
    s: AsyncSession, channel: str, cards: list[SearchCard]
) -> tuple[dict[str, int], dict[str, int]]:
    slugs = [c.slug for c in cards]
    ext_ids = [c.external_id for c in cards if c.external_id]
    rows = await s.execute(
        select(Listing.listing_key, Listing.external_id, Listing.hotel_id).where(
            Listing.channel == channel,
            or_(Listing.listing_key.in_(slugs), Listing.external_id.in_(ext_ids)),
        )
    )
    by_slug: dict[str, int] = {}
    by_ext: dict[str, int] = {}
    for key, ext, hotel_id in rows:
        by_slug[key] = hotel_id
        if ext:
            by_ext[ext] = hotel_id
    return by_slug, by_ext


async def _create(s: AsyncSession, channel: str, card: SearchCard, now: datetime) -> int:
    """Khách sạn + listing mới; hai lượt quét song song cùng tạo thì bên sau dùng bản đã có."""
    try:
        async with s.begin_nested():
            hotel = Hotel(country_code=card.slug.split("/", 1)[0])
            _refresh(hotel, card)
            s.add(hotel)
            await s.flush()
            s.add(
                Listing(
                    hotel_id=hotel.id,
                    channel=channel,
                    listing_key=card.slug[:300],
                    external_id=card.external_id,
                    url=card.url,
                    name=card.name,
                    status="active",
                    verified_at=now,
                )
            )
            await s.flush()
            return hotel.id
    except IntegrityError:
        by_slug, by_ext = await _existing(s, channel, [card])
        hotel_id = by_slug.get(card.slug) or by_ext.get(card.external_id or "")
        if hotel_id is None:
            raise
        return hotel_id


async def resolve_hotels(
    s: AsyncSession, channel: str, cards: list[SearchCard], now: datetime
) -> list[int]:
    """hotel_id cho từng thẻ (cùng thứ tự), tạo khách sạn + listing kênh cho thẻ chưa có."""
    by_slug, by_ext = await _existing(s, channel, cards)
    known = {i: by_slug.get(c.slug) or by_ext.get(c.external_id or "") for i, c in enumerate(cards)}
    ids = [h for h in known.values() if h is not None]
    hotels = {h.id: h for h in (await s.execute(select(Hotel).where(Hotel.id.in_(ids)))).scalars()}
    out: list[int] = []
    for i, card in enumerate(cards):
        hotel_id = known[i]
        if hotel_id is None:
            hotel_id = await _create(s, channel, card, now)
        elif hotel_id in hotels:
            _refresh(hotels[hotel_id], card)
        out.append(hotel_id)
    await s.flush()
    return out


async def record_page(
    s: AsyncSession,
    *,
    area_id: int,
    scan_id: int,
    channel: str,
    ranked: list[tuple[int, SearchCard]],
    now: datetime,
    round_started: datetime,
    currency: str,
    area_rank: bool = True,
) -> list[int]:
    """Ghi các thẻ (vị trí, thẻ) của một trang; trả hotel_id theo thứ tự. Thẻ trùng khách sạn (quảng
    cáo lặp lại) chỉ ghi lần đầu. `area_rank`: vị trí là hạng theo thứ tự mặc định của kênh (trang
    đầu không lọc) → cập nhật `best_rank`; thẻ từ lát khám phá thì không."""
    hotel_ids = await resolve_hotels(s, channel, [c for _, c in ranked], now)
    rows: dict[int, tuple[int, SearchCard]] = {}
    for hotel_id, (rank, card) in zip(hotel_ids, ranked, strict=True):
        rows.setdefault(hotel_id, (rank, card))
    if not rows:
        return hotel_ids
    stmt = insert(MarketAreaHotel).values(
        [
            {
                "area_id": area_id,
                "hotel_id": h,
                "first_seen_at": now,
                "last_seen_at": now,
                "best_rank": rank if area_rank else None,
            }
            for h, (rank, _) in rows.items()
        ]
    )
    # Hạng tốt nhất tính trong lượt quét ngày này: dòng thấy lần cuối trước lượt này thì đặt lại
    # (lát khám phá chỉ xoá hạng cũ của lượt trước; LEAST bỏ qua NULL).
    stale = MarketAreaHotel.last_seen_at < round_started
    best_rank = (
        case(
            (stale, stmt.excluded.best_rank),
            else_=func.least(MarketAreaHotel.best_rank, stmt.excluded.best_rank),
        )
        if area_rank
        else case((stale, None), else_=MarketAreaHotel.best_rank)
    )
    await s.execute(
        stmt.on_conflict_do_update(
            index_elements=[MarketAreaHotel.area_id, MarketAreaHotel.hotel_id],
            set_={"last_seen_at": stmt.excluded.last_seen_at, "best_rank": best_rank},
        )
    )
    prices = insert(MarketListPrice).values(
        [
            {
                "scan_id": scan_id,
                "hotel_id": h,
                "rank": rank,
                "price": card.price if card.currency == currency else None,
                "currency": card.currency if card.currency == currency else None,
                "sponsored": card.sponsored,
                "badges": _badges(card) or None,
            }
            for h, (rank, card) in rows.items()
        ]
    )
    await s.execute(prices.on_conflict_do_nothing())
    await record_reviews(s, channel, [(h, c) for h, (_, c) in rows.items()], now)
    return hotel_ids


def _badges(card: SearchCard) -> list[str]:
    out = list(card.badges)
    if card.preferred:
        out.insert(0, card.preferred)
    if card.sponsored:
        out.insert(0, "ad")
    return out


async def record_reviews(
    s: AsyncSession, channel: str, cards: list[tuple[int, SearchCard]], now: datetime
) -> None:
    """Điểm/số review và huy hiệu theo ngày (roadmap 7.1): một dòng mỗi (khách sạn, kênh, ngày);
    lần thấy sau trong ngày ghi đè (số mới nhất)."""
    from app.market.models import HotelReviewSnapshot

    values = [
        {
            "hotel_id": h,
            "channel": channel,
            "observed_on": now.date(),
            "review_score": c.review_score,
            "review_count": c.review_count,
            "badges": _badges(c) or None,
            "preferred": c.preferred is not None,
        }
        for h, c in cards
        if c.review_count is not None or c.preferred or c.badges
    ]
    if not values:
        return
    stmt = insert(HotelReviewSnapshot).values(values)
    await s.execute(
        stmt.on_conflict_do_update(
            index_elements=[
                HotelReviewSnapshot.hotel_id,
                HotelReviewSnapshot.channel,
                HotelReviewSnapshot.observed_on,
            ],
            set_={
                "review_score": stmt.excluded.review_score,
                "review_count": stmt.excluded.review_count,
                "badges": stmt.excluded.badges,
                "preferred": stmt.excluded.preferred,
            },
        )
    )
