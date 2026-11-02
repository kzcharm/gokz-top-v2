import csv
import json
from dataclasses import asdict

import numpy as np
import pytest

from app.core.rank_system import get_rank_system_settings
from scripts.publish_rating_candidate import load_candidate
from scripts.tune_ratings import DTYPE, FIELDS, checksum


def test_publish_requires_complete_population_and_matching_runtime(tmp_path):
    runtime = get_rank_system_settings()
    player = 76561199022242128
    np.save(
        tmp_path / "runs.npy",
        np.asarray([(player, i, i, 900) for i in range(10)], dtype=DTYPE),
    )
    (tmp_path / "maps.json").write_text("{}")
    hashes = {name: checksum(tmp_path / name) for name in ("runs.npy", "maps.json")}
    (tmp_path / "metadata.json").write_text(
        json.dumps({"scope": "OVR", "players": 1, "sha256": hashes})
    )
    report = {
        "scope": "OVR",
        "players": 1,
        "fields": FIELDS,
        "snapshot_sha256": hashes,
        "rating_settings": asdict(runtime.rating),
    }
    (tmp_path / "candidate.json").write_text(json.dumps(report, default=str))
    curves = {
        "source_scope": "OVR",
        "sample_size": 1,
        "snapshot_sha256": hashes,
        "rating_settings": asdict(runtime.rating),
        "metrics": dict.fromkeys(FIELDS[:3], runtime.display_anchors),
    }
    (tmp_path / "candidate.converters.json").write_text(json.dumps(curves, default=str))
    candidate = tmp_path / "candidate.csv"
    with candidate.open("w") as out:
        writer = csv.writer(out)
        writer.writerow(("steamid64", *FIELDS))
        writer.writerow((player, *([100] * len(FIELDS))))
    rows, _ = load_candidate(tmp_path, candidate)
    assert rows == [(player, *([100] * len(FIELDS)), 10)]
    with candidate.open("a") as out:
        csv.writer(out).writerow((player, *([100] * len(FIELDS))))
    with pytest.raises(ValueError, match="exactly once"):
        load_candidate(tmp_path, candidate)
    curves["rating_settings"]["decay"] = "0.975"
    (tmp_path / "candidate.converters.json").write_text(json.dumps(curves, default=str))
    with pytest.raises(ValueError, match="parameters must match"):
        load_candidate(tmp_path, candidate)
