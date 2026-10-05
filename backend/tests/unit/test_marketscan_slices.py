"""Kế hoạch lát khám phá (thuần): lát con từ facet, ước lượng thu thêm theo thẻ đã thấy, dừng theo
độ phủ 98% hoặc ngân sách request. Phần mô phỏng dùng một "chợ" giả: trang của mỗi lát là trang đầu
(per_page thẻ) của các khách sạn khớp bộ lọc theo thứ tự yêu cầu, facet đếm trên đúng lát đó."""

import gzip
from decimal import Decimal
from pathlib import Path

import pytest

from app.marketscan.parser import SearchCard, SearchPage, parse_search_page
from app.marketscan.slices import Slice, SlicePlanner, card_matches

TYPES = (204, 201, 203)


def _card(i: int) -> SearchCard:
    stars = i % 6
    return SearchCard(
        slug=f"vn/h{i}",
        url=f"https://www.booking.com/hotel/vn/h{i}.html",
        name=f"H{i}",
        stars=Decimal(stars) if stars else None,
        type_id=TYPES[i % 3],
        review_score=Decimal(60 + i % 40) / 10,
        review_count=10,
        price=Decimal((i * 37) % 120 * 10_000 + 300_000),
        currency="VND",
    )


def _page(universe: list[SearchCard], s: Slice, per_page: int) -> SearchPage:
    members = [c for c in universe if all(card_matches(c, f) for f in s.filters)]
    by = {
        None: lambda c: int(c.slug[4:]),
        "price": lambda c: c.price,
        "price_from_high_to_low": lambda c: -(c.price or 0),
        "review_score_and_price": lambda c: -(c.review_score or 0),
    }.get(s.order, lambda c: -int(c.slug[4:]))
    members.sort(key=by)  # type: ignore[arg-type]
    options = [f"class={n}" for n in range(1, 6)] + [f"ht_id={t}" for t in TYPES]
    options += [f"review_score={n}" for n in (90, 80, 70, 60)]
    facets = {o: sum(1 for c in members if card_matches(c, o)) for o in options}
    return SearchPage(
        total=len(members),
        checkin=None,
        cards=members[:per_page],
        source="apollo",
        per_page=per_page,
        offset=0,
        facets={k: v for k, v in facets.items() if v},
    )


def _discover(
    universe: list[SearchCard], budget: int, per_page: int = 20
) -> tuple[SlicePlanner, list[Slice]]:
    root = Slice()
    page = _page(universe, root, per_page)
    planner = SlicePlanner(page.total, per_page)
    planner.add_cards(page.cards)
    planner.observe(root, page)
    fetched = [root]
    while len(fetched) < budget and not planner.done():
        s = planner.next()
        if s is None:
            break
        page = _page(universe, s, per_page)
        planner.observe(s, page)
        planner.add_cards(page.cards)
        fetched.append(s)
    return planner, fetched


@pytest.fixture(scope="module")
def real_root() -> SearchPage:
    path = (
        Path(__file__).parent.parent / "fixtures" / "html" / "searchresults_hcmc_2026-10-09.html.gz"
    )
    return parse_search_page(gzip.decompress(path.read_bytes()).decode("utf-8"))


def test_children_come_from_split_facets_with_alternative_orders(
    real_root: SearchPage,
) -> None:
    planner = SlicePlanner(real_root.total)
    planner.add_cards(real_root.cards)
    planner.observe(Slice(), real_root)
    cands = planner._candidates
    assert Slice(("class=5",)) in cands and Slice(("ht_id=203",)) in cands
    assert Slice(("review_score=90",)) in cands and Slice(("di=6750",)) in cands
    assert Slice((), "price") in cands and Slice((), "price_from_high_to_low") in cands
    # Trường không dùng để chia (tiện nghi, chính sách…) bị bỏ.
    assert not any("hotelfacility" in (c.nflt or "") for c in cands)
    assert not any("fc=" in (c.nflt or "") for c in cands)

    # Lát đã liệt kê hết (tổng ≤ số thẻ): bỏ mọi thứ tự khác của lát, không sinh lát con.
    small = SearchPage(5, None, real_root.cards[:5], "apollo", 25, 0, {"ht_id=204": 2})
    before = set(planner._candidates)
    planner.observe(Slice(("class=1",)), small)
    assert planner._candidates == {c for c in before if c.filters != ("class=1",)}
    assert Slice(("class=1", "ht_id=204")) not in planner._candidates


def test_gain_subtracts_seen_hotels_matching_the_slice(real_root: SearchPage) -> None:
    planner = SlicePlanner(real_root.total)
    planner.add_cards(real_root.cards)
    planner.observe(Slice(), real_root)
    five = sum(1 for c in real_root.cards if c.stars == 5)
    hotels = sum(1 for c in real_root.cards if c.type_id == 204)
    assert five > 0 and hotels > 0
    # Thứ tự mặc định: khách sạn đã thấy của lát đứng đầu trang, còn lại là thẻ mới.
    assert planner.gain(Slice(("class=5",))) == 25 - five
    assert planner.gain(Slice(("ht_id=204",))) == 25 - hotels
    # Thứ tự khác trên cả khu vực: phần đã thấy coi như rải đều.
    expected = 25 * (3944 - 25) / 3944 * 0.9
    assert planner.gain(Slice((), "price")) == pytest.approx(expected)
    # Lát con cũng có sẵn các thứ tự khác (tổng đã biết từ facet).
    assert planner.gain(Slice(("class=5",), "price")) == pytest.approx(
        25 * (100 - five) / 100 * 0.9
    )
    # Khu phố không có trên thẻ: ước theo tỉ lệ (536/3944 của 25 khách sạn đã thấy).
    assert planner.gain(Slice(("di=6750",))) == pytest.approx(25 - 25 * 536 / 3944)
    first = planner.next()
    assert first is not None and planner.gain(first) == 25  # lát chưa thấy ai, đủ một trang
    assert first not in planner._candidates


def test_card_matches() -> None:
    c = _card(10)  # 4 sao, căn hộ (201), điểm 7.0
    assert card_matches(c, "class=4") and not card_matches(c, "class=3")
    assert card_matches(c, "ht_id=201") and not card_matches(c, "ht_id=204")
    assert card_matches(c, "review_score=70") and not card_matches(c, "review_score=80")
    assert card_matches(c, "di=6750") is None  # khu phố không có trên thẻ
    assert card_matches(_card(6), "class=1") is False  # chưa xếp hạng


def test_discovery_reaches_98_percent_well_under_budget_without_repeating_slices() -> None:
    universe = [_card(i) for i in range(120)]
    planner, fetched = _discover(universe, budget=40)
    assert planner.done() and planner.seen >= 0.98 * 120
    assert len(fetched) <= 12  # các lát hạng sao/loại liệt kê hết + vài thứ tự
    assert len(set(fetched)) == len(fetched)
    # Khách sạn chưa xếp hạng (không có facet riêng) vẫn tới được qua loại chỗ ở/thứ tự.
    unrated = {c.slug for c in universe if c.stars is None}
    assert unrated <= set(planner._seen)


def test_deeper_market_coverage_grows_with_budget() -> None:
    universe = [_card(i) for i in range(535)]
    small, _ = _discover(universe, budget=20, per_page=25)
    large, fetched = _discover(universe, budget=60, per_page=25)
    assert small.seen < large.seen and len(fetched) == 60
    assert large.seen >= 0.7 * 535


def test_budget_caps_requests() -> None:
    universe = [_card(i) for i in range(500)]
    planner, fetched = _discover(universe, budget=4)
    assert len(fetched) == 4 and not planner.done()
    assert 20 < planner.seen <= 80


def test_nothing_to_plan_when_first_page_lists_everything() -> None:
    planner, fetched = _discover([_card(i) for i in range(15)], budget=10)
    assert fetched == [Slice()] and planner.done() and planner.next() is None
