"""Zentraler, medienunabhängiger Capacity Planner.

Berechnet VOR jeder Kodierung/jedem Authoring, ob und wie ein ausgewählter
Disc-Inhalt (``DiscTitle``-Objekte aus dem ``DiscContent``-Modell, siehe
P0 Block 1) auf ein Zielmedium passt. Eine nachträgliche "Datei ist zu
groß"-Meldung nach dem Encode ersetzt diesen Planer ausdrücklich nicht.

Rechenweg (siehe P0_CAPACITY_PLANNING.md für die vollständige Herleitung
und Begründung der einzelnen Konstanten):

    verfügbare Zielkapazität (TargetMedium.usable_capacity_bytes)
    minus Authoring-/Container-Overhead   (Navigationsstruktur: IFO/BUP bzw. BDMV-Index)
    = verfügbare Nutzdatenkapazität
    minus Audio-Budget                     (Summe der ausgewählten Audiospuren über die Gesamtdauer)
    minus sonstiger Overhead                (Untertitel-Reserve)
    = verfügbares Video-Budget
    verfügbares Video-Budget * 8 / Gesamtdauer(s) = maximale durchschnittliche Video-Bitrate (bit/s)

Fehlende Eingaben (Bitrate, Dateigröße) werden über dokumentierte,
konservative Standardannahmen ersetzt und in ``CapacityPlan.warnings`` als
Schätzung gekennzeichnet - nie stillschweigend als gemessener Wert
ausgegeben.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from src.config.target_media import (
    AuthoringFormat,
    TargetMedium,
    custom_target_medium,
    get_target_medium,
    target_medium_capability_issue,
)
from src.models.disc_content import DiscAudioTrack, DiscSubtitleTrack, DiscTitle

if TYPE_CHECKING:
    from src.services.drive_inspector import DriveCapabilities


@dataclass
class CapacityPlan:
    target_medium_id: str
    target_authoring_format: str
    target_capacity_bytes: int
    usable_capacity_bytes: int
    reserved_overhead_bytes: int
    available_payload_bytes: int
    total_duration_seconds: float
    estimated_source_size_bytes: Optional[int]
    required_space_bytes: Optional[int]
    audio_budget_bytes: int
    subtitle_overhead_bytes: int
    video_budget_bytes: int
    max_average_video_bitrate_bps: Optional[float]
    fits_without_reduction: Optional[bool]
    transcoding_required: Optional[bool]
    video_mode_hint: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "target_medium_id": self.target_medium_id,
            "target_authoring_format": self.target_authoring_format,
            "target_capacity_bytes": self.target_capacity_bytes,
            "usable_capacity_bytes": self.usable_capacity_bytes,
            "reserved_overhead_bytes": self.reserved_overhead_bytes,
            "available_payload_bytes": self.available_payload_bytes,
            "total_duration_seconds": self.total_duration_seconds,
            "estimated_source_size_bytes": self.estimated_source_size_bytes,
            "required_space_bytes": self.required_space_bytes,
            "audio_budget_bytes": self.audio_budget_bytes,
            "subtitle_overhead_bytes": self.subtitle_overhead_bytes,
            "video_budget_bytes": self.video_budget_bytes,
            "max_average_video_bitrate_bps": self.max_average_video_bitrate_bps,
            "fits_without_reduction": self.fits_without_reduction,
            "transcoding_required": self.transcoding_required,
            "video_mode_hint": self.video_mode_hint,
            "warnings": list(self.warnings),
            "error": self.error,
        }


class CapacityPlanner:
    """Zustandslos - jede ``plan()``-Berechnung ist unabhängig und reproduzierbar."""

    # Konservative, dokumentierte Standardannahmen - keine Messwerte.
    # Werden nur verwendet, wenn eine Audiospur keine gemessene Bitrate trägt.
    DEFAULT_AUDIO_BITRATE_STEREO_BPS = 192_000     # z. B. AC-3 2.0, gängiger DVD-/BD-Wert
    DEFAULT_AUDIO_BITRATE_SURROUND_BPS = 448_000    # z. B. AC-3 5.1, gängiger DVD-/BD-Wert

    # Grobe, konservative Reserve pro Untertitelspur (Bitmap-Untertitel für
    # einen Spielfilm können durchaus mehrere MB erreichen).
    SUBTITLE_TRACK_RESERVE_BYTES = 5_000_000

    # Grobe, konservative Reserve für die Authoring-Navigationsstruktur
    # (IFO/BUP bei DVD, index.bdmv/MovieObject.bdmv/PLAYLIST bei Blu-ray).
    # Keine Messung - siehe P0_CAPACITY_PLANNING.md.
    AUTHORING_OVERHEAD_BY_FORMAT = {
        AuthoringFormat.DVD_VIDEO: 10_000_000,
        AuthoringFormat.BDMV: 5_000_000,
    }

    def plan(
        self,
        *,
        titles: list[DiscTitle],
        target_medium_id: str,
        selected_audio_tracks: Optional[list[DiscAudioTrack]] = None,
        selected_subtitle_tracks: Optional[list[DiscSubtitleTrack]] = None,
        custom_target_bytes: Optional[int] = None,
        custom_authoring_format: Optional[AuthoringFormat] = None,
        duration_seconds: Optional[float] = None,
        video_mode_hint: Optional[str] = None,
        drive_capabilities: Optional["DriveCapabilities"] = None,
    ) -> CapacityPlan:
        # ── Zielmedium auflösen ────────────────────────────────────────
        # Ungültige Zielangaben (unbekannte ID, ungültige/fehlende Custom-
        # Angaben) führen NIE zu einer Exception, sondern zu einem
        # CapacityPlan mit gesetztem .error - damit die Bridge immer
        # gleichförmig json.dumps(plan.to_dict()) zurückgeben kann.
        if target_medium_id == "custom":
            if not custom_target_bytes or custom_target_bytes <= 0:
                return self._error_plan(
                    "custom", video_mode_hint,
                    "Ungültige Custom-Zielgröße: muss eine positive Byte-Anzahl sein.",
                )
            if custom_authoring_format is None:
                return self._error_plan(
                    "custom", video_mode_hint,
                    "Custom-Zielgröße benötigt eine Angabe des Authoring-Formats (DVD-Video oder BDMV).",
                )
            try:
                medium = custom_target_medium(custom_target_bytes, custom_authoring_format)
            except ValueError as exc:
                return self._error_plan("custom", video_mode_hint, str(exc))
        else:
            try:
                medium = get_target_medium(target_medium_id)
            except ValueError as exc:
                return self._error_plan(target_medium_id, video_mode_hint, str(exc))

        warnings: list[str] = []
        capability_error: Optional[str] = None

        # ── Laufwerks-/Backend-Fähigkeit: nie Unterstützung behaupten ohne
        #    Beleg (BD-Schreibfähigkeit, DVD-Schreibfähigkeit, BDXL) ───────
        capability_issue = target_medium_capability_issue(medium, drive_capabilities)
        if capability_issue:
            if drive_capabilities is None:
                warnings.append(capability_issue)
            else:
                capability_error = capability_issue   # definitiv nicht unterstützt -> Fehlerzustand

        # ── Audio-/Untertitel-Auswahl normalisieren ─────────────────────
        if selected_audio_tracks is None:
            selected_audio_tracks = [a for t in titles for a in t.audio_tracks]
        if selected_subtitle_tracks is None:
            selected_subtitle_tracks = [s for t in titles for s in t.subtitle_tracks]

        # ── Gesamtdauer ──────────────────────────────────────────────────
        if duration_seconds is None:
            known_durations = [t.duration_seconds for t in titles if t.duration_seconds is not None]
            if len(known_durations) < len(titles):
                warnings.append(
                    "Laufzeit mindestens eines ausgewählten Titels ist unbekannt - "
                    "die Gesamtdauer ist nur eine Teilsumme der bekannten Titel."
                )
            duration_seconds = sum(known_durations)

        # ── Geschätzte Quellgröße ─────────────────────────────────────────
        known_sizes = [t.size_bytes for t in titles if t.size_bytes is not None]
        if titles and len(known_sizes) < len(titles):
            estimated_source_size_bytes = None
            warnings.append(
                "Quellgröße mindestens eines ausgewählten Titels ist unbekannt - "
                "die Gesamtgröße kann nicht verlässlich geschätzt werden."
            )
        else:
            estimated_source_size_bytes = sum(known_sizes)

        # ── Audio-Budget ─────────────────────────────────────────────────
        audio_budget_bytes = 0
        for track in selected_audio_tracks:
            if track.bitrate:
                bitrate_bps = track.bitrate
            else:
                bitrate_bps = (
                    self.DEFAULT_AUDIO_BITRATE_SURROUND_BPS
                    if track.channels and track.channels > 2
                    else self.DEFAULT_AUDIO_BITRATE_STEREO_BPS
                )
                warnings.append(
                    f"Bitrate für Audiospur {track.index} unbekannt - Standardannahme "
                    f"{bitrate_bps} bit/s verwendet (Schätzung, keine Messung)."
                )
            audio_budget_bytes += int(bitrate_bps * duration_seconds / 8)

        # ── Untertitel-/sonstiger Overhead ───────────────────────────────
        subtitle_overhead_bytes = len(selected_subtitle_tracks) * self.SUBTITLE_TRACK_RESERVE_BYTES

        # ── Authoring-/Container-Overhead ─────────────────────────────────
        reserved_overhead_bytes = (
            self.AUTHORING_OVERHEAD_BY_FORMAT[medium.authoring_format] + medium.authoring_overhead_bytes
        )

        available_payload_bytes = medium.usable_capacity_bytes - reserved_overhead_bytes
        video_budget_bytes = available_payload_bytes - audio_budget_bytes - subtitle_overhead_bytes

        error: Optional[str] = capability_error
        if available_payload_bytes <= 0:
            capacity_error = (
                "Zielmedium ist kleiner als der Authoring-/Container-Overhead allein - "
                "technisch nicht erreichbar."
            )
            error = f"{error}; {capacity_error}" if error else capacity_error
        elif video_budget_bytes <= 0:
            capacity_error = (
                "Zielmedium reicht nicht einmal für die ausgewählten Audio-/Untertitelspuren "
                "allein - für Video bleibt kein Budget übrig."
            )
            error = f"{error}; {capacity_error}" if error else capacity_error

        if duration_seconds and duration_seconds > 0 and video_budget_bytes > 0:
            max_average_video_bitrate_bps: Optional[float] = video_budget_bytes * 8 / duration_seconds
        else:
            max_average_video_bitrate_bps = None
            if not duration_seconds:
                warnings.append(
                    "Gesamtdauer ist 0 (oder unbekannt) - maximale Video-Bitrate kann nicht berechnet werden."
                )

        # Bis zum künftigen Smart Space Optimizer identisch mit der
        # geschätzten Quellgröße - siehe P0_CAPACITY_PLANNING.md,
        # Abschnitt "Vorbereitung Smart Space Optimizer".
        required_space_bytes = estimated_source_size_bytes

        if estimated_source_size_bytes is None:
            fits_without_reduction: Optional[bool] = None
            transcoding_required: Optional[bool] = None
        else:
            fits_without_reduction = estimated_source_size_bytes <= available_payload_bytes
            transcoding_required = not fits_without_reduction

        return CapacityPlan(
            target_medium_id=medium.id,
            target_authoring_format=medium.authoring_format.value,
            target_capacity_bytes=medium.nominal_capacity_bytes,
            usable_capacity_bytes=medium.usable_capacity_bytes,
            reserved_overhead_bytes=reserved_overhead_bytes,
            available_payload_bytes=available_payload_bytes,
            total_duration_seconds=duration_seconds,
            estimated_source_size_bytes=estimated_source_size_bytes,
            required_space_bytes=required_space_bytes,
            audio_budget_bytes=audio_budget_bytes,
            subtitle_overhead_bytes=subtitle_overhead_bytes,
            video_budget_bytes=video_budget_bytes,
            max_average_video_bitrate_bps=max_average_video_bitrate_bps,
            fits_without_reduction=fits_without_reduction,
            transcoding_required=transcoding_required,
            video_mode_hint=video_mode_hint,
            warnings=warnings,
            error=error,
        )

    @staticmethod
    def _error_plan(medium_id: str, video_mode_hint: Optional[str], message: str) -> CapacityPlan:
        return CapacityPlan(
            target_medium_id=medium_id, target_authoring_format="", target_capacity_bytes=0,
            usable_capacity_bytes=0, reserved_overhead_bytes=0, available_payload_bytes=0,
            total_duration_seconds=0.0, estimated_source_size_bytes=None, required_space_bytes=None,
            audio_budget_bytes=0, subtitle_overhead_bytes=0, video_budget_bytes=0,
            max_average_video_bitrate_bps=None, fits_without_reduction=None, transcoding_required=None,
            video_mode_hint=video_mode_hint, warnings=[], error=message,
        )
