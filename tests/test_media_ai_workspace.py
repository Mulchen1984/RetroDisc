"""Media AI: die Arbeitsmappe.

Die Mappe ist der Ort, an dem alles zu einem Import zusammenliegt. Sie muss
drei Dinge sicher koennen: einen Windows-tauglichen Namen bilden, niemals
eine vorhandene Mappe uebernehmen, und ihren Zustand so schreiben, dass ein
Absturz mitten im Schreiben die alte Datei nicht zerstoert.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.media_ai.workspace import (
    AUDIO_NAME,
    METADATA_NAME,
    TRANSCRIPT_NAME,
    MediaJob,
    MediaWorkspace,
    WorkspaceError,
    create_workspace,
    list_workspaces,
    open_workspace,
    safe_title,
)


# ── Windows-taugliche Namen ───────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("Ein normales Video", "Ein normales Video"),
    ('Titel mit <>:"/\\|?* Zeichen', "Titel mit _ Zeichen"),
    ("   viele    Leerzeichen   ", "viele Leerzeichen"),
    ("Punkt am Ende...", "Punkt am Ende"),
    ("", "Import"),
    ("   ", "Import"),
    ("...", "Import"),
])
def test_titles_become_valid_folder_names(raw, expected):
    assert safe_title(raw) == expected


@pytest.mark.parametrize("device", ["CON", "con", "PRN", "NUL", "COM1", "LPT9"])
def test_reserved_windows_device_names_are_escaped(device):
    """Ein Ordner namens CON laesst sich unter Windows nicht anlegen."""
    result = safe_title(device)

    assert result.upper() not in {"CON", "PRN", "NUL", "COM1", "LPT9"}
    assert result.endswith("_")


def test_a_very_long_title_is_shortened():
    result = safe_title("A" * 500)

    assert len(result) <= 60


def test_non_cp1252_characters_survive():
    """NTFS kann sie, und ein japanischer Titel soll japanisch bleiben."""
    assert safe_title("【4K】 Björk – Jóga") == "【4K】 Björk – Jóga"


# ── Anlegen ohne Kollision ────────────────────────────────────────────

def test_a_workspace_is_created_with_the_title(tmp_path):
    workspace = create_workspace(tmp_path, "Mein Konzert")

    assert workspace.root == tmp_path / "Mein Konzert"
    assert workspace.root.is_dir()


def test_a_second_import_never_takes_over_the_first_folder(tmp_path):
    first = create_workspace(tmp_path, "Konzert")
    (first.root / "original.mp4").write_bytes(b"erstes video")

    second = create_workspace(tmp_path, "Konzert")

    assert second.root == tmp_path / "Konzert (1)"
    assert (first.root / "original.mp4").read_bytes() == b"erstes video"


def test_the_counter_keeps_climbing(tmp_path):
    names = [create_workspace(tmp_path, "X").root.name for _ in range(3)]

    assert names == ["X", "X (1)", "X (2)"]


def test_opening_a_missing_workspace_is_reported(tmp_path):
    with pytest.raises(WorkspaceError):
        open_workspace(tmp_path / "gibtsnicht")


# ── Feste Dateinamen ──────────────────────────────────────────────────

def test_the_workspace_knows_its_fixed_paths(tmp_path):
    workspace = create_workspace(tmp_path, "T")

    assert workspace.audio == workspace.root / AUDIO_NAME
    assert workspace.transcript == workspace.root / TRANSCRIPT_NAME
    assert workspace.metadata == workspace.root / METADATA_NAME
    assert workspace.frames == workspace.root / "frames"


def test_original_and_video_are_found_by_stem(tmp_path):
    """Die Endung steht erst nach dem Download fest."""
    workspace = create_workspace(tmp_path, "T")
    (workspace.root / "original.webm").write_bytes(b"x")
    (workspace.root / "video.webm").write_bytes(b"y")

    assert workspace.original().name == "original.webm"
    assert workspace.video().name == "video.webm"


def test_a_staging_file_is_not_mistaken_for_a_result(tmp_path):
    """FFmpeg schreibt nach '.name.retrodisc-<uuid>.ext', bevor es umbenennt."""
    workspace = create_workspace(tmp_path, "T")
    (workspace.root / ".video.retrodisc-abc123.mp4").write_bytes(b"halb")

    assert workspace.video() is None


def test_missing_artefacts_are_reported_as_absent(tmp_path):
    workspace = create_workspace(tmp_path, "T")

    assert workspace.original() is None
    assert workspace.existing_artefacts() == {}


def test_an_empty_file_does_not_count_as_an_artefact(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    (workspace.root / "original.mp4").write_bytes(b"")

    assert "original" not in workspace.existing_artefacts()


def test_frames_are_counted(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    workspace.frames.mkdir()
    for i in range(3):
        (workspace.frames / f"frame_{i:06d}.png").write_bytes(b"p")

    artefacts = workspace.existing_artefacts()

    assert artefacts["frame_count"] == "3"


# ── Zustand ───────────────────────────────────────────────────────────

def test_the_state_survives_a_round_trip(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    state = MediaJob(url="https://example.invalid/v", title="T",
                     source_id="abc", uploader="Kanal")
    state.record("Download läuft")

    workspace.save_job(state)
    reloaded = workspace.load_job()

    assert reloaded.url == "https://example.invalid/v"
    assert reloaded.source_id == "abc"
    assert reloaded.uploader == "Kanal"
    assert "Download läuft" in reloaded.stages


def test_saving_records_what_really_exists(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    (workspace.root / "original.mp4").write_bytes(b"x")

    workspace.save_job(MediaJob(title="T"))

    stored = json.loads(workspace.metadata.read_text(encoding="utf-8"))
    assert "original" in stored["artefacts"]


def test_a_stage_is_never_recorded_twice(tmp_path):
    state = MediaJob()
    state.record("Fertig")
    state.record("Fertig")

    assert state.stages == ["Fertig"]


def test_a_broken_metadata_file_does_not_block_the_workspace(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    workspace.metadata.write_text("{kein json", encoding="utf-8")

    state = workspace.load_job()

    assert state.title == "T", "Ein kaputter Zustand muss auf die Vorgabe fallen"


def test_unknown_fields_in_metadata_are_ignored(tmp_path):
    """Eine aeltere oder neuere Fassung darf das Laden nicht sprengen."""
    workspace = create_workspace(tmp_path, "T")
    workspace.metadata.write_text(
        json.dumps({"title": "T", "vollkommen_neu": 42}), encoding="utf-8")

    assert workspace.load_job().title == "T"


def test_saving_leaves_no_temporary_file_behind(tmp_path):
    workspace = create_workspace(tmp_path, "T")

    workspace.save_job(MediaJob(title="T"))

    assert list(workspace.root.glob(".metadata.json.*")) == []


def test_the_metadata_is_readable_unicode(tmp_path):
    workspace = create_workspace(tmp_path, "T")

    workspace.save_job(MediaJob(title="Björk – Jóga"))

    assert "Björk" in workspace.metadata.read_text(encoding="utf-8"), \
        "Der Titel darf nicht als \\uXXXX geschrieben werden"


# ── Auflisten ─────────────────────────────────────────────────────────

def test_only_folders_with_metadata_count_as_workspaces(tmp_path):
    real = create_workspace(tmp_path, "Echt")
    real.save_job(MediaJob(title="Echt"))
    (tmp_path / "irgendein-auftragsordner").mkdir()
    (tmp_path / ".retrodisc-dl-xyz").mkdir()
    (tmp_path / "lose-datei.mp4").write_bytes(b"x")

    found = list_workspaces(tmp_path)

    assert [w.name for w in found] == ["Echt"]


def test_listing_a_missing_folder_is_empty_not_an_error(tmp_path):
    assert list_workspaces(tmp_path / "gibtsnicht") == []


def test_describe_carries_everything_the_ui_needs(tmp_path):
    workspace = create_workspace(tmp_path, "T")
    (workspace.root / "original.mp4").write_bytes(b"x")
    workspace.save_job(MediaJob(title="T", url="https://example.invalid/v"))

    described = workspace.describe()

    assert described["name"] == "T"
    assert described["root"] == str(workspace.root)
    assert described["url"] == "https://example.invalid/v"
    assert "original" in described["artefacts"]
