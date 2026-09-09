"""Detect and report optical-drive capabilities. Detection only — never modifies firmware.

Robust, pure parser over typical dvd+rw-mediainfo / INQUIRY output. Tolerant of
empty output, unusual locale, Unicode vendor strings and garbage: anything not
positively detected stays False/empty (no capability is ever assumed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DriveCapabilities:
    drive_letter: str = ""
    vendor: str = ""
    model: str = ""
    firmware: str = ""
    dvd_read: bool = False
    dvd_write: bool = False
    dvd_plus_r: bool = False
    dvd_plus_rw: bool = False
    dvd_plus_r_dl: bool = False
    dvd_dash_r: bool = False
    dvd_dash_rw: bool = False
    bd_read: bool = False
    bd_r: bool = False
    bd_re: bool = False
    bd_xl: bool = False
    write_speeds: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: (list(v) if isinstance(v, list) else v) for k, v in self.__dict__.items()}


def parse_inquiry(text: str) -> tuple[str, str, str]:
    """Extract (vendor, model, firmware) from an INQUIRY '[VENDOR][MODEL][FW]' line."""
    match = re.search(r"INQUIRY:\s*\[([^\]]*)\]\s*\[([^\]]*)\]\s*\[([^\]]*)\]", text or "", re.I)
    if not match:
        return "", "", ""
    return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()


def parse_capabilities(text: str, *, drive_letter: str = "") -> DriveCapabilities:
    caps = DriveCapabilities(drive_letter=drive_letter)
    if not text:
        return caps
    vendor, model, firmware = parse_inquiry(text)
    caps.vendor, caps.model, caps.firmware = vendor, model, firmware
    upper = text.upper()

    def has(token: str) -> bool:
        return token in upper

    caps.dvd_plus_r_dl = has("DVD+R DL") or has("DVD+R/DL") or has("DVD+R DUAL")
    caps.dvd_plus_rw = has("DVD+RW")
    caps.dvd_plus_r = has("DVD+R")
    caps.dvd_dash_rw = has("DVD-RW")
    caps.dvd_dash_r = bool(re.search(r"DVD-R(?![OW])", upper))     # DVD-R, aber nicht DVD-ROM/DVD-RW
    caps.dvd_read = has("DVD-ROM") or has("DVD READ") or has("DVD ") or any(
        [caps.dvd_plus_r, caps.dvd_plus_rw, caps.dvd_plus_r_dl, caps.dvd_dash_r, caps.dvd_dash_rw])
    caps.dvd_write = any([caps.dvd_plus_r, caps.dvd_plus_rw, caps.dvd_plus_r_dl,
                          caps.dvd_dash_r, caps.dvd_dash_rw])

    caps.bd_xl = has("BD-R XL") or has("BD-RE XL") or has("BDXL")
    caps.bd_re = has("BD-RE")
    caps.bd_r = bool(re.search(r"BD-R(?!E)", upper))
    caps.bd_read = has("BD-ROM") or has("BLU-RAY") or caps.bd_r or caps.bd_re

    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*[xX]\s*(\d{3,5})?", text):
        speed = f"{value}x"
        if speed not in caps.write_speeds:
            caps.write_speeds.append(speed)
    return caps
