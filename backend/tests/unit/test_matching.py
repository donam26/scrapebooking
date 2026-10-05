"""Chấm điểm ứng viên listing chéo kênh (D8)."""

from app.collector.matching import distance_m, match_score, name_similarity, normalize_name

CARAVELLE = (10.7763, 106.7036)


def test_normalize_drops_accents_and_generic_words() -> None:
    assert normalize_name("Khách sạn Đà Lạt Palace") == "da lat palace"
    assert normalize_name("The Reverie Saigon Hotel") == "reverie"
    assert normalize_name("Hotel") == ""


def test_name_similarity() -> None:
    assert name_similarity("Caravelle Saigon", "Caravelle Hotel Sài Gòn") == 1.0
    assert name_similarity("Hotel", "Rex Hotel") == 0.0  # chỉ có từ chung chung
    assert name_similarity("Caravelle", "Park Hyatt") < 0.4


def test_match_score_name_only_without_coordinates() -> None:
    assert match_score("Caravelle Saigon", "Caravelle Hotel") == 1.0
    assert match_score("Caravelle Saigon", "Caravelle Hotel", CARAVELLE, None) == 1.0


def test_match_score_weighs_distance() -> None:
    near = match_score("Caravelle", "Caravelle Hotel", CARAVELLE, (10.7764, 106.7037))
    far = match_score("Caravelle", "Caravelle Hotel", CARAVELLE, (10.35, 103.85))
    assert near == 1.0
    assert far == 0.6  # cùng tên nhưng cách hàng trăm km: chỉ còn phần tên
    # Khác tên, ngay cạnh nhau: phần khoảng cách không đủ để coi là cùng khách sạn.
    neighbour = match_score("Caravelle", "Park Hyatt", CARAVELLE, (10.7765, 106.7038))
    assert neighbour < 0.7


def test_distance_m() -> None:
    assert distance_m(*CARAVELLE, *CARAVELLE) == 0
    # ~0.01 độ vĩ ≈ 1.1 km
    assert 1100 < distance_m(10.77, 106.70, 10.78, 106.70) < 1120
