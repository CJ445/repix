from app.core import config
from app.core.config import Settings, available_cpus


def test_explicit_ai_threads_wins():
    assert Settings(ai_threads=3).effective_ai_threads == 3


def test_auto_threads_is_at_least_one():
    assert Settings(ai_threads=0).effective_ai_threads >= 1


def test_cgroup_v2_quota_caps_cpus(monkeypatch, tmp_path):
    cpu_max = tmp_path / "cpu.max"
    cpu_max.write_text("150000 100000\n")
    monkeypatch.setattr(config.os, "cpu_count", lambda: 16)
    monkeypatch.setattr(config.os, "sched_getaffinity", lambda _: set(range(16)), raising=False)
    real_path = config.Path
    monkeypatch.setattr(
        config, "Path", lambda p: cpu_max if p == "/sys/fs/cgroup/cpu.max" else real_path(p)
    )
    assert available_cpus() == 2  # 1.5 CPUs rounds up
