"""Roadmap Phase 4 (radar), Phase 5 (OTB/pickup/pace/STLY/KPI), Phase 7 (uy tín, báo cáo)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

from app.analytics.compset import review_compset
from app.api.routers.reputation import next_threshold, review_velocity
from app.market.pacing import calibrate_by_lead
from app.market.radar import (
    area_scarcity,
    cancellation_profile,
    promo_runs,
    promo_share_by_night,
    restriction_for,
)
from app.pms.base import Table
from app.pms.otb import (
    Booking,
    build_curves,
    kpis,
    otb_night,
    parse_bookings,
    parse_otb_report,
    rebuild_snapshots,
    suggest_booking_mapping,
    suggest_otb_mapping,
)

N1, N2 = date(2026, 10, 17), date(2026, 10, 18)


def test_promo_runs_group_labels_and_origin() -> None:
    runs = promo_runs(
        {N1: {"Late Escape Deal": "44.6"}, N2: {"Late Escape Deal": "40", "Getaway Deal": None}},
        {"Late Escape Deal": datetime(2026, 10, 1, tzinfo=UTC)},
    )
    assert [(r.label, len(r.nights), r.max_depth_pct, r.origin) for r in runs] == [
        ("Late Escape Deal", 2, D("44.6"), "hotel"),
        ("Getaway Deal", 1, None, "hotel"),
    ]
    assert promo_runs({N1: {"Genius discount": "10"}})[0].origin == "channel"
    assert promo_runs({N1: {"SALE10": "10"}})[0].origin == "channel"
    share = promo_share_by_night([{N1: {"x": None}}, {N1: {}}, {}], [N1, N2])
    assert share == {N1: (1, 2), N2: (0, 0)}


def test_cancellation_profile_nr_discount() -> None:
    p = cancellation_profile(
        [
            {"t|f": "1000000", "f|f": "850000"},
            {"t|t": "1200000", "f|t": "1080000", "t|f": "1100000"},
            {"f|f": "900000"},
            None,
        ]
    )
    assert (p.nights_priced, p.nights_with_refundable, p.nights_with_nonrefundable) == (3, 2, 3)
    assert p.nr_discount_pct == D("12.5") and p.pairs == 2  # trung vị của 15% và 10%
    assert p.refundable_share == D("0.67")


def test_restriction_flags() -> None:
    assert not restriction_for(N1, 1, "available").any
    r = restriction_for(N1, 2, "available")
    assert r.any and r.min_stay == 2 and not r.closed_to_arrival
    assert restriction_for(N1, None, "restricted").closed_to_arrival


def test_area_scarcity_week_over_week() -> None:
    t0 = datetime(2026, 10, 1, 3, tzinfo=UTC)
    scans = [(N1, t0, 410), (N1, t0 + timedelta(days=8), 300), (N2, t0 + timedelta(days=8), 280)]
    out = area_scarcity(scans, [N1, N2, date(2026, 10, 19)])
    assert (out[0].properties, out[0].week_ago, out[0].change_pct) == (300, 410, D("-26.8"))
    assert out[1].week_ago is None and out[2].properties is None


def _table(rows: list[dict[str, object]]) -> Table:
    return Table(columns=list(rows[0]), rows=rows)


def test_parse_otb_report_and_bookings_with_vietnamese_headers() -> None:
    t = _table(
        [
            {
                "Ngày": "17/10/2026",
                "Phòng đã đặt": "42",
                "Doanh thu": "79.800.000",
                "Tổng phòng": "120",
            },
            {"Ngày": "bad", "Phòng đã đặt": "1", "Doanh thu": "", "Tổng phòng": "120"},
        ]
    )
    rows, errors = parse_otb_report(t, suggest_otb_mapping(t.columns), date(2026, 10, 9))
    assert len(rows) == 1 and len(errors) == 1
    assert (
        rows[0].as_of_date,
        rows[0].rooms_otb,
        rows[0].revenue_otb,
        rows[0].rooms_available,
    ) == (
        date(2026, 10, 9),
        42,
        D("79800000"),
        120,
    )
    b = _table(
        [
            {
                "Ngày đặt": "2026-09-01",
                "Ngày đến": "2026-10-17",
                "Ngày đi": "2026-10-19",
                "Số phòng": "1",
                "Doanh thu": "3600000",
                "Trạng thái": "confirmed",
            },
            {
                "Ngày đặt": "2026-09-05",
                "Ngày đến": "2026-10-17",
                "Ngày đi": "2026-10-18",
                "Số phòng": "2",
                "Doanh thu": "3800000",
                "Trạng thái": "Đã huỷ",
            },
        ]
    )
    bookings, errs = parse_bookings(b, suggest_booking_mapping(b.columns))
    assert not errs and bookings[1].cancel_date == date(2026, 9, 5) and bookings[0].nights == 2


def test_rebuild_snapshots_counts_bookings_until_cancelled() -> None:
    bookings = [
        Booking(date(2026, 9, 1), N1, N2 + timedelta(days=1), rooms=1, revenue=D("3600000")),
        Booking(
            date(2026, 9, 5), N1, N2, rooms=2, revenue=D("3800000"), cancel_date=date(2026, 9, 20)
        ),
        Booking(date(2026, 10, 8), N1, N2, rooms=3, revenue=D("6000000"), group=True),
    ]
    rows = rebuild_snapshots(bookings, today=date(2026, 10, 9), rooms_available=120)
    at = {(r.as_of_date, r.stay_date): r for r in rows}
    assert at[(date(2026, 9, 10), N1)].rooms_otb == 3  # 1 + 2 trước khi huỷ
    assert at[(date(2026, 9, 25), N1)].rooms_otb == 1  # đã huỷ 2
    assert at[(date(2026, 9, 25), N1)].cancellations == 2
    last = at[(date(2026, 10, 9), N1)]
    assert (last.rooms_otb, last.revenue_otb, last.group_rooms) == (4, D("7800000.00"), 3)
    assert max(r.as_of_date for r in rows) == date(2026, 10, 9)  # không quá hôm nay


def test_pickup_pace_stly_and_forecast() -> None:
    today = date(2026, 10, 9)
    stay = date(2026, 10, 23)  # thứ Sáu, lead 14
    rows = []
    # Đêm hiện tại: OTB 40 hôm nay, 37 hôm qua, 30 cách 7 ngày.
    rows += [
        (today, stay, 40),
        (today - timedelta(days=1), stay, 37),
        (today - timedelta(days=7), stay, 30),
    ]
    # Đêm 4 tuần trước (cùng thứ) ở lead 14: 32, kết thúc ở 70.
    ref = stay - timedelta(weeks=4)
    rows += [(ref - timedelta(days=14), ref, 32), (ref, ref, 70)]
    # Đêm cùng kỳ năm trước (364 ngày) ở lead 14: 45.
    ly = stay - timedelta(days=364)
    rows += [(ly - timedelta(days=14), ly, 45)]
    # Lịch sử cùng thứ để dự báo: các tuần trước có đường đầy đủ.
    for w in (1, 2, 3):
        d = stay - timedelta(weeks=w)
        rows += [(d - timedelta(days=14), d, 35), (d, d, 75)]
    n = otb_night(build_curves(rows), stay, today, capacity=80)
    assert (n.rooms_otb, n.pickup_1d, n.pickup_7d) == (40, 3, 10)
    assert (n.pace_4w, n.ref_4w) == (8, 32)
    assert (n.stly, n.pace_stly) == (45, -5)
    # Pickup lịch sử 14 → 0 ngày: (40+40+40+38)/4 = 39.5 → 40 → 40 + 40 = 80 (= sức chứa).
    assert n.forecast_rooms == 80 and n.forecast_basis == 4


def test_kpis_follow_str_definitions() -> None:
    k = kpis([(90, 120, D("180000000")), (60, 120, D("114000000")), (None, 120, D("1"))])
    assert (k.nights, k.occupancy_pct, k.adr, k.revpar) == (
        2,
        D("62.5"),
        D("1960000.00"),
        D("1225000.00"),
    )
    assert kpis([]).occupancy_pct is None


def test_calibration_by_lead_bucket_marks_unusable() -> None:
    triples = [(3, D("0.80"), D("0.78")), (5, D("0.70"), D("0.74")), (20, D("0.9"), D("0.5"))]
    by = {c.bucket: c for c in calibrate_by_lead(triples)}
    assert by["0-7"].nights == 2 and by["0-7"].mean_abs_error_pts == D("3.0") and by["0-7"].usable
    assert by["8-30"].mean_abs_error_pts == D("40.0") and not by["8-30"].usable
    assert by["31-90"].nights == 0 and not by["31-90"].usable


def test_compset_review_costar_rules() -> None:
    now = datetime(2026, 10, 9, tzinfo=UTC)
    r = review_compset([1, 2, 3], {1: 100, 2: 50, 3: None}, now - timedelta(days=30), now)
    assert r.warnings == ["too_few", "rooms_unknown"]
    big = review_compset(
        [1, 2, 3, 4], {1: 400, 2: 100, 3: 100, 4: 100}, now - timedelta(days=200), now
    )
    assert big.warnings == ["dominant_hotel", "review_due"] and big.dominant_hotel_id == 1
    assert big.dominant_share == D("0.57")


def test_reputation_helpers() -> None:
    assert review_velocity([(date(2026, 9, 1), 1000), (date(2026, 10, 1), 1060)]) == D("60.0")
    assert review_velocity([(date(2026, 9, 1), 1000)]) is None
    assert next_threshold(D("7.8")) == (D("8.0"), D("0.2"))
    assert next_threshold(D("9.3")) == (None, None)
