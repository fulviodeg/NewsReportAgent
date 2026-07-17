from pathlib import Path

from src.main import run_scheduler


def test_run_scheduler_fires_both_clocks_at_their_intervals():
    clock = {"t": 0.0}
    iters = {"n": 0}
    coll, proc = [], []

    def mono():
        return clock["t"]

    def wait(dt):
        clock["t"] += dt

    def cont():
        iters["n"] += 1
        return iters["n"] <= 3

    run_scheduler(
        lambda: coll.append(1),
        lambda: proc.append(1),
        coll_interval_s=60,
        proc_interval_s=300,
        monotonic=mono,
        wait=wait,
        should_continue=cont,
        tick=60,
    )
    # over 3 ticks of 60s: collection every tick, processing only at start
    assert len(coll) == 3
    assert len(proc) == 1


def test_cli_dispatch_uses_same_functions(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("src.main.run_collection", lambda *a, **k: calls.append("collection"))
    monkeypatch.setattr("src.main.run_processing", lambda *a, **k: calls.append("processing"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONFIG_PATH", str(Path(__file__).parents[1] / "config.toml"))

    from src.main import main

    main(["run-collection"])
    main(["run-processing"])
    assert calls == ["collection", "processing"]
