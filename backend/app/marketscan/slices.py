"""Kế hoạch "lát" khám phá khách sạn của khu vực (thuần).

Trang kết quả SSR chỉ cho trang đầu (15–25 thẻ, `offset` bị bỏ qua), nên mỗi request là một lát:
bộ lọc (`nflt`, tối đa `MAX_DEPTH` lựa chọn) × thứ tự (`order`). Trang nào cũng kèm số chỗ ở theo
từng lựa chọn bộ lọc (facet) của truy vấn đó, nên biết trước lát con có bao nhiêu chỗ ở. Khách sạn
đã thấy được đối chiếu với bộ lọc trên thẻ (hạng sao, loại chỗ ở, điểm) để ước lượng mỗi lát còn
bao nhiêu khách sạn mới; mỗi bước chọn lát có ước lượng thu thêm lớn nhất (xem `gain`).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from app.marketscan.parser import SearchCard, SearchPage

# Trường lọc dùng để chia lát (facet của Booking): hạng sao, loại chỗ ở, điểm (ngưỡng ≥), khu phố.
SPLIT_FIELDS = ("class", "ht_id", "review_score", "di")
# Trường đối chiếu được trên thẻ kết quả (khu phố thì không).
CHECKABLE_FIELDS = ("class", "ht_id", "review_score")
# Thứ tự khác thứ tự mặc định ("popularity"): mỗi thứ tự cho một "đầu" khác của lát.
ALT_ORDERS = (
    "price",
    "price_from_high_to_low",
    "review_score_and_price",
    "distance_from_search",
    "bayesian_review_score",
    "class_asc",
)
ORDER_WEIGHT = 0.9  # đổi thứ tự: hơi kém chắc chắn hơn ước lượng của thứ tự mặc định
MAX_DEPTH = 2  # số lựa chọn lọc tối đa mỗi lát (vd. class=3;ht_id=201)
MIN_GAIN = 1.0  # lát ước lượng thu thêm dưới 1 khách sạn: không đáng một request
COVERAGE_TARGET = 0.98

Filters = tuple[str, ...]


@dataclass(frozen=True)
class Slice:
    filters: Filters = ()  # urlId đã sắp xếp: ("class=3", "ht_id=204")
    order: str | None = None  # None = popularity (mặc định của kênh)

    @property
    def nflt(self) -> str | None:
        return ";".join(self.filters) or None


def _field(uid: str) -> str:
    return uid.split("=", 1)[0]


def card_matches(card: SearchCard, uid: str) -> bool | None:
    """Thẻ có khớp lựa chọn lọc `uid` không; None khi không đối chiếu được trên thẻ."""
    name, _, value = uid.partition("=")
    if not value.isdigit():
        return None
    if name == "class":
        return card.stars is not None and int(card.stars) == int(value)
    if name == "ht_id":
        return None if card.type_id is None else card.type_id == int(value)
    if name == "review_score":
        return bool(card.review_count) and (card.review_score or 0) * 10 >= int(value)
    return None


def _known_part(filters: Filters) -> Filters:
    return tuple(f for f in filters if _field(f) in CHECKABLE_FIELDS)


class SlicePlanner:
    def __init__(self, properties_found: int | None, per_page: int = 25) -> None:
        self.properties_found = properties_found
        self.per_page = per_page
        self._seen: dict[str, SearchCard] = {}
        self._totals: dict[Filters, int] = {}  # tổng chỗ ở của mỗi bộ lọc đã biết
        self._matched: dict[Filters, int] = {}  # khách sạn đã thấy khớp phần đối chiếu được
        self._candidates: set[Slice] = set()
        self._fetched: set[Slice] = set()
        if properties_found is not None:
            self._know((), properties_found)

    @property
    def seen(self) -> int:
        return len(self._seen)

    @property
    def coverage(self) -> float | None:
        if not self.properties_found:
            return None
        return min(1.0, self.seen / self.properties_found)

    def done(self) -> bool:
        cov = self.coverage
        return cov is not None and cov >= COVERAGE_TARGET

    def _track(self, known: Filters) -> None:
        if known not in self._matched:
            self._matched[known] = sum(
                1 for c in self._seen.values() if all(card_matches(c, f) for f in known)
            )

    def _know(self, filters: Filters, total: int) -> None:
        if filters in self._totals:
            return
        self._totals[filters] = total
        self._track(_known_part(filters))
        for order in (None, *ALT_ORDERS):
            s = Slice(filters, order)
            if s not in self._fetched:
                self._candidates.add(s)

    def add_cards(self, cards: Iterable[SearchCard]) -> list[SearchCard]:
        """Ghi nhận thẻ đã thấy; trả thẻ mới (chưa thấy trong vòng này)."""
        new: list[SearchCard] = []
        for card in cards:
            if card.slug in self._seen:
                continue
            self._seen[card.slug] = card
            new.append(card)
            for known in self._matched:
                if all(card_matches(card, f) for f in known):
                    self._matched[known] += 1
        return new

    def observe(self, s: Slice, page: SearchPage) -> None:
        """Sau khi tải trang của lát `s`: cập nhật tổng, sinh lát con từ facet."""
        self._fetched.add(s)
        self._candidates.discard(s)
        if page.per_page:
            self.per_page = page.per_page
        if page.total is not None:
            self._totals.pop(s.filters, None)
            self._know(s.filters, page.total)
        total = self._totals.get(s.filters)
        if total is None or total <= len(page.cards):
            # Lát đã liệt kê hết: không cần thứ tự khác hay chia nhỏ.
            self._candidates = {c for c in self._candidates if c.filters != s.filters}
            return
        if len(s.filters) >= MAX_DEPTH:
            return
        used = {_field(f) for f in s.filters}
        for uid, count in page.facets.items():
            name = _field(uid)
            if name in SPLIT_FIELDS and name not in used and 0 < count < total:
                self._know(tuple(sorted((*s.filters, uid))), count)

    def matching(self, filters: Filters) -> float:
        """Số khách sạn đã thấy thuộc lát: đếm trên thẻ; khu phố không có trên thẻ nên ước theo tỉ
        lệ tổng của lát trên tổng phần đối chiếu được."""
        known = _known_part(filters)
        self._track(known)
        m = float(self._matched[known])
        if len(known) == len(filters):
            return m
        total = self._totals.get(filters)
        base = self._totals.get(known) if known else self.properties_found
        return m * min(1.0, total / base) if total and base else m

    def gain(self, s: Slice) -> float:
        """Ước lượng số khách sạn mới nếu tải lát `s`."""
        total = self._totals.get(s.filters)
        if not total:
            return 0.0
        seen = min(self.matching(s.filters), float(total))
        page = float(min(self.per_page, total))
        if s.order is None:
            # Thứ tự mặc định ("phổ biến") giống nhau giữa các lát: khách sạn đã thấy của lát (phần
            # lớn từ các trang phổ biến trước đó) đứng đầu trang, phần còn lại mới là thẻ mới.
            return max(0.0, page - seen)
        # Thứ tự khác lấy một đầu khác của lát: khách sạn đã thấy coi như rải đều trong lát.
        return page * (total - seen) / total * ORDER_WEIGHT

    def next(self) -> Slice | None:
        """Lát kế tiếp nên tải (ước lượng thu thêm lớn nhất); None khi không còn gì đáng tải."""
        best: Slice | None = None
        best_key: tuple[float, int, int, bool, str] | None = None
        for c in self._candidates:
            key = (
                self.gain(c),
                -self._totals.get(c.filters, 0),  # lát nhỏ (liệt kê hết được) trước
                -len(c.filters),
                c.order is None,
                f"{c.nflt}|{c.order}",
            )
            if best_key is None or key > best_key:
                best, best_key = c, key
        if best is None or best_key is None or best_key[0] < MIN_GAIN:
            return None
        self._candidates.discard(best)
        return best
