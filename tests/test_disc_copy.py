"""Disc-copy state machine: happy path plus the safety-critical guards."""
import pytest
from src.core.errors import DriveError, MediaError
from src.services.disc_copy import DiscCopyMachine, CopyState


def source():
    return {"present": True, "readable": True, "device": "D:", "label": "MOVIE",
            "profile": "DVD-ROM", "capacity_bytes": 4_700_000_000, "blank": False}


def blank_target(device="E:", capacity=4_700_000_000):
    return {"present": True, "writable": True, "blank": True, "rewritable": False,
            "device": device, "capacity_bytes": capacity}


def drive_to_ready(m, target=None):
    m.analyze_source().read_source().image_created("/tmp/x.iso", 4_000_000_000)
    m.eject_source().wait_for_target()
    m.detect_target(target or blank_target()).validate_target().ready_to_burn()
    return m


def test_full_happy_path_with_and_without_verify():
    m = DiscCopyMachine(source(), verify=True)
    drive_to_ready(m).burn().verifying().done()
    assert m.state == CopyState.DONE and m.finished

    m2 = DiscCopyMachine(source(), verify=False)
    drive_to_ready(m2).burn().done()
    assert m2.state == CopyState.DONE


def test_verify_enabled_forbids_skipping_verification():
    m = DiscCopyMachine(source(), verify=True)
    drive_to_ready(m).burn()
    with pytest.raises(DriveError):
        m.done()                                  # muss erst verifying()


def test_source_must_be_present_and_readable():
    with pytest.raises(MediaError):
        DiscCopyMachine({"present": False})
    with pytest.raises(MediaError):
        DiscCopyMachine({"present": True, "readable": False})


def test_invalid_transition_is_rejected():
    m = DiscCopyMachine(source())
    with pytest.raises(DriveError):
        m.burn()                                  # aus SOURCE_DETECTED nicht erlaubt


def test_empty_image_fails_machine():
    m = DiscCopyMachine(source())
    m.analyze_source().read_source()
    with pytest.raises(MediaError):
        m.image_created("/tmp/x.iso", 0)
    assert m.state == CopyState.FAILED and m.ctx.error


def test_no_target_media_stays_waiting():
    m = DiscCopyMachine(source())
    m.analyze_source().read_source().image_created("/tmp/x.iso", 4_000_000_000)
    m.eject_source().wait_for_target()
    with pytest.raises(MediaError):
        m.detect_target({"present": False})
    assert m.state == CopyState.WAIT_FOR_TARGET   # kein Fehlerzustand, Nutzer legt Medium ein


def test_source_drive_before_eject_is_rejected():
    m = DiscCopyMachine(source())
    m.analyze_source().read_source().image_created("/tmp/x.iso", 4_000_000_000)
    # noch nicht ausgeworfen -> gleiches Laufwerk (D:) als Ziel verboten
    m.state = CopyState.WAIT_FOR_TARGET            # simuliere Sprung ohne eject (nur für Guard-Test)
    m.ctx.source_ejected = False
    with pytest.raises(MediaError):
        m.detect_target(blank_target(device="D:"))


def test_reinserted_source_is_rejected_as_target():
    m = DiscCopyMachine(source())
    m.analyze_source().read_source().image_created("/tmp/x.iso", 4_000_000_000)
    m.eject_source().wait_for_target()
    reinserted = {"present": True, "readable": True, "blank": False, "writable": False,
                  "device": "E:", "label": "MOVIE", "profile": "DVD-ROM",
                  "capacity_bytes": 4_700_000_000}
    with pytest.raises(MediaError, match="Quelldisc"):
        m.detect_target(reinserted)
    assert m.state == CopyState.WAIT_FOR_TARGET


@pytest.mark.parametrize("target,match", [
    ({"present": True, "writable": False, "blank": True, "device": "E:", "capacity_bytes": 4_700_000_000},
     "nicht beschreibbar"),
    ({"present": True, "writable": True, "blank": False, "rewritable": False, "device": "E:",
      "capacity_bytes": 4_700_000_000}, "nicht leer"),
    ({"present": True, "writable": True, "blank": True, "device": "E:", "capacity_bytes": 1_000_000},
     "zu klein"),
])
def test_invalid_target_rejected_and_returns_to_waiting(target, match):
    m = DiscCopyMachine(source())
    m.analyze_source().read_source().image_created("/tmp/x.iso", 4_000_000_000)
    m.eject_source().wait_for_target().detect_target(target)
    with pytest.raises(MediaError, match=match):
        m.validate_target()
    assert m.state == CopyState.WAIT_FOR_TARGET and m.ctx.target is None


@pytest.mark.parametrize("upto", ["analyze", "read", "image", "wait", "burn"])
def test_cancel_works_in_every_phase_and_keeps_cleanup(upto):
    m = DiscCopyMachine(source())
    if upto in ("read", "image", "wait", "burn"):
        m.analyze_source().read_source()
    else:
        m.analyze_source()
    if upto in ("image", "wait", "burn"):
        m.image_created("/tmp/x.iso", 4_000_000_000)
    if upto in ("wait", "burn"):
        m.eject_source().wait_for_target()
    if upto == "burn":
        m.detect_target(blank_target()).validate_target().ready_to_burn().burn()
    m.cancel()
    assert m.state == CopyState.CANCELLED
    if upto in ("image", "wait", "burn"):
        assert "/tmp/x.iso" in m.cleanup_paths     # temporäres Abbild zum Aufräumen vermerkt


def test_fail_records_error_and_is_terminal_noop_after():
    m = DiscCopyMachine(source())
    m.fail(MediaError("kaputt"))
    assert m.state == CopyState.FAILED and m.ctx.error["code"] == "media_error"
    m.cancel()                                     # nach Terminal: No-Op
    assert m.state == CopyState.FAILED
