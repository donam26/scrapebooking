"""Email mời đặt mật khẩu (UX Phase 3, C5): theo ngôn ngữ tenant, escape, không chữ kỹ thuật."""

from app.api.auth import verify_password
from app.api.invites import INVITE_TTL_HOURS, invite_url, unusable_password
from app.db.models import User
from app.notify.render import render_invite

URL = "https://app.otaradar.vn/set-password?token=12.abc"


def test_render_invite_vi_and_en() -> None:
    vi = render_invite("Rex <Hotel>", "gm@rex.vn", "viewer", URL, INVITE_TTL_HOURS, "vi")
    assert vi.subject == "Rex <Hotel> mời bạn dùng OTARadar"
    assert "quyền chỉ xem" in vi.text and "72 giờ" in vi.text and URL in vi.text
    assert "Rex &lt;Hotel&gt;" in vi.html and "<Hotel>" not in vi.html
    assert f'href="{URL}"' in vi.html and ">Đặt mật khẩu<" in vi.html

    en = render_invite("Rex", "gm@rex.vn", "tenant_admin", URL, 72, "en")
    assert en.subject == "Rex invited you to OTARadar"
    assert "with admin access" in en.text and "72 hours" in en.text
    assert '<html lang="en">' in en.html
    for word in ("tenant", "token", "role", "SMTP"):
        assert word not in en.text.replace(URL, "").lower().replace("otaradar", "")


def test_invite_url_and_unusable_password() -> None:
    assert invite_url("http://x/", "5.s") == "http://x/set-password?token=5.s"
    pw = unusable_password()
    assert not verify_password("", pw) and not verify_password(pw, pw)
    assert User(password_hash=pw).invite_pending
    assert not User(password_hash="$argon2id$v=19$m=65536,t=3,p=4$x$y").invite_pending
