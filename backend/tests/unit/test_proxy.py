from app.collector.proxy import StaticProxyProvider


def test_static_provider_builds_sticky_endpoint() -> None:
    provider = StaticProxyProvider(
        "http://u-country-{country}-session-{session}:p@gate.example.com:7777",
        id_factory=lambda: "abc123",
    )
    ep = provider.new_endpoint("vn")
    assert ep.server == "http://gate.example.com:7777"
    assert ep.username == "u-country-vn-session-abc123"
    assert ep.password == "p"
    assert ep.country == "vn"
    assert ep.session_id == "abc123"
    assert ep.url == "http://u-country-vn-session-abc123:p@gate.example.com:7777"
    assert ep.id == "vn:abc123"


def test_new_endpoint_gets_new_session_id_each_time() -> None:
    provider = StaticProxyProvider("http://u-{country}-{session}:p@h:1")
    a = provider.new_endpoint("vn")
    b = provider.new_endpoint("vn")
    assert a.session_id != b.session_id


def test_template_without_credentials() -> None:
    provider = StaticProxyProvider("http://h:1?c={country}&s={session}", id_factory=lambda: "s1")
    ep = provider.new_endpoint("th")
    assert ep.username is None
    assert ep.password is None
    assert ep.url == "http://h:1?c=th&s=s1"
