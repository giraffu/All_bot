from pathlib import Path

import pytest

from scripts.reconcile_media_archive_outbox import load_history_ids


def test_exact_history_manifest_is_sorted_deduplicated_and_bounded(tmp_path: Path):
    manifest = tmp_path / "history-ids.txt"
    manifest.write_text("# canary\n9\n2\n9\n")
    assert load_history_ids(str(manifest)) == (2, 9)


def test_exact_history_manifest_rejects_invalid_or_excessive_ids(tmp_path: Path):
    invalid = tmp_path / "invalid.txt"
    invalid.write_text("1\nnot-an-id\n")
    with pytest.raises(ValueError, match="line 2"):
        load_history_ids(str(invalid))

    excessive = tmp_path / "excessive.txt"
    excessive.write_text("\n".join(str(value) for value in range(1, 10002)))
    with pytest.raises(ValueError, match="10000"):
        load_history_ids(str(excessive))
