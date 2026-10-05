"""Mã lượt quét hiển thị cho tenant: không lộ mã tenant/khu vực thị trường của tenant khác."""

from app.api.routers.data import _visible_trigger_key


def test_manual_and_market_keys_are_masked_for_other_tenants() -> None:
    assert _visible_trigger_key("manual:t2:20261002T080000:booking", 1, set()) == "manual"
    assert _visible_trigger_key("manual:t1:h4:20261002T080000:booking", 1, set()).startswith(
        "manual:t1:"
    )
    assert _visible_trigger_key("market:7:20261002", 1, {3}) == "market"
    assert _visible_trigger_key("market:3:20261002", 1, {3}) == "market:3:20261002"
    assert _visible_trigger_key("2026-10-02T07:00:booking", 1, set()) == "2026-10-02T07:00:booking"
