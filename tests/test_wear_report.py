import pytest

from src.schemas import EdgeWear, WearReport
from tests.helpers import make_wear


def test_edge_statistics():
    wear = make_wear([0.10, 0.12, 0.20, 0.10])
    assert wear.vb_max == 0.20
    assert wear.vb_min == 0.10
    assert wear.worst_edge == 3
    assert wear.vb_mean == pytest.approx(0.13)
    assert wear.uneven_index == pytest.approx(0.10 / 0.13)
    assert wear.uneven_flag


def test_uniform_wear_is_not_uneven():
    assert not make_wear([0.10, 0.11, 0.10, 0.105]).uneven_flag


def test_small_wear_is_not_judged_uneven():
    # 초기 마모 구간에서는 상대 편차가 커도 노이즈로 보고 편마모로 판단하지 않는다
    wear = make_wear([0.01, 0.01, 0.03, 0.01])
    assert wear.uneven_index > 0.3
    assert not wear.uneven_flag


def test_requires_four_edges():
    with pytest.raises(ValueError):
        WearReport("T01", 1, [EdgeWear(1, 0.1, 0.01)])
