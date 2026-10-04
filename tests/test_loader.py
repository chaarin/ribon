"""QIT-CEMC 로더 테스트. 실제 데이터 없이 같은 구조의 작은 가짜 데이터로 확인한다."""
import numpy as np
import pytest

from src.config.settings import SENSOR_CHANNELS
from src.data.loader import FORCE_DIR, VIBRATION_DIR, active_slice, list_cycles, load_cycle


@pytest.fixture
def fake_root(tmp_path):
    (tmp_path / FORCE_DIR).mkdir()
    (tmp_path / VIBRATION_DIR).mkdir()
    rng = np.random.default_rng(0)
    # 순번 표기가 섞인 이름: 01-26-1, 01-26-2, 02-01-01 / 01-26-2 의 진동 파일은 없음 (Cycle 2 결측 재현)
    for name in ("01-26-1", "01-26-2", "02-01-01"):
        n = 3000
        signal = np.zeros(n)
        signal[1000:2500] = rng.normal(5, 1, 1500)  # 앞뒤 0 구간 + 절삭 구간
        lines = ["Time\tFx\tFy\tFz\tMz"] + [f"{i / 1e4:.4f}\t{v:.3f}\t{v:.3f}\t{v:.3f}\t{v / 10:.3f}" for i, v in enumerate(signal)]
        (tmp_path / FORCE_DIR / f"{name}.txt").write_text("\n".join(lines))
    for name in ("01-26-01", "02-01-01"):
        rows = ["time[x],AI1-01[m/s²],AI1-02[m/s²],AI1-03[m/s²],AI1-07[Pa]"]
        rows += [f"t,{a:.3f},{a:.3f},{a:.3f},{a:.3f}" for a in rng.normal(size=2000)]
        (tmp_path / VIBRATION_DIR / f"{name}.csv").write_text("\n".join(rows))
    return tmp_path


def test_cycles_are_ordered_and_matched(fake_root):
    cycles = list_cycles(fake_root)
    assert [c.force.stem for c in cycles] == ["01-26-1", "01-26-2", "02-01-01"]
    assert [c.cycle for c in cycles] == [1, 2, 3]
    assert cycles[0].vibration.stem == "01-26-01"  # '1'과 '01'을 같은 순번으로 매칭
    assert cycles[1].vibration is None


def test_load_cycle_trims_idle_and_keeps_channels(fake_root):
    labels = {1: [0.1, 0.2, 0.3, 0.4]}
    window = load_cycle(list_cycles(fake_root)[0], labels)
    assert set(window.signals) == set(SENSOR_CHANNELS)
    assert len(window.signals["Fx"]) < 3000  # 앞뒤 0 구간 제거
    assert window.vb_label_mm == [0.1, 0.2, 0.3, 0.4]


def test_missing_vibration_has_only_force_channels(fake_root):
    window = load_cycle(list_cycles(fake_root)[1], {})
    assert set(window.signals) == {"Fx", "Fy", "Fz", "Mz"}
    assert window.vb_label_mm is None


def test_active_slice_finds_cutting_region():
    x = np.zeros(100_000)
    x[30_000:70_000] = 3.0 + np.sin(np.arange(40_000) * 0.3)  # 절삭 중: 오프셋 + 날 통과에 따른 출렁임
    s = active_slice(x, fs=10_000)
    assert 29_000 <= s.start <= 30_000 and 70_000 <= s.stop <= 71_000


def test_detrend_removes_drift_keeps_oscillation():
    from src.data.preprocess import detrend

    fs = 10_000
    t = np.arange(20 * fs) / fs
    drift = 50 * t / t[-1]  # Cycle 동안 50만큼 밀리는 영점 드리프트
    oscillation = 10 * np.sin(2 * np.pi * 93 * t)  # 날 통과 주파수 성분
    out = detrend(drift + oscillation, int(0.1 * fs))
    assert abs(out.mean()) < 0.5
    assert out.std() == pytest.approx(oscillation.std(), rel=0.05)
