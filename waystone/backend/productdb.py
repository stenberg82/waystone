"""Read install/update progress from Battle.net Agent's product.db.

product.db is a protobuf ``ProductDb`` message. We decode the handful of
fields we need with a tiny schema-less wire-format reader:

    ProductDb       { repeated ProductInstall installs = 1; }
    ProductInstall  { string uid = 1; string product_code = 2;
                      UserSettings settings = 3; CachedProductState state = 4; }
    UserSettings    { string install_path = 1; }
    CachedProductState { BaseProductState base = 1; UpdateProgress update = 4; }
    BaseProductState   { bool installed = 1; bool playable = 2; bool update_complete = 3;
                         string current_version = 7; }
    UpdateProgress     { double progress = 2; uint64 total_to_download = 4;
                         uint64 download_remaining = 5; }
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from . import paths

PRODUCT_DB = paths.DRIVE_C / "ProgramData" / "Battle.net" / "Agent" / "product.db"


@dataclass
class ProductStatus:
    uid: str = ""
    code: str = ""
    install_path: str = ""
    installed: bool = False
    playable: bool = False
    update_complete: bool = False
    version: str = ""                    # e.g. '1.60.1.71037'
    progress: float | None = None        # 0..1
    total_bytes: int = 0
    remaining_bytes: int = 0

    @property
    def downloading(self) -> bool:
        return not self.update_complete and (self.progress is not None or self.total_bytes > 0)


def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def _fields(buf: bytes):
    """Yield (field_number, wire_type, value) for one message."""
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            val, i = _varint(buf, i)
        elif wt == 1:
            val, i = buf[i:i + 8], i + 8
        elif wt == 2:
            ln, i = _varint(buf, i)
            val, i = buf[i:i + ln], i + ln
        elif wt == 5:
            val, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        yield num, wt, val


def _sub(buf: bytes, num: int) -> bytes:
    for n, wt, v in _fields(buf):
        if n == num and wt == 2:
            return v
    return b""


def parse(data: bytes) -> list[ProductStatus]:
    out = []
    for num, wt, install in _fields(data):
        if num != 1 or wt != 2:
            continue
        st = ProductStatus()
        for n, w, v in _fields(install):
            if w != 2:
                continue
            if n == 1:
                st.uid = v.decode(errors="replace")
            elif n == 2:
                st.code = v.decode(errors="replace")
            elif n == 3:
                st.install_path = _sub(v, 1).decode(errors="replace")
            elif n == 4:
                for sn, sw, sv in _fields(v):
                    if sn == 1 and sw == 2:
                        for bn, bw, bv in _fields(sv):
                            if bn == 7 and bw == 2:
                                st.version = bv.decode(errors="replace")
                            if bw == 0:
                                if bn == 1: st.installed = bool(bv)
                                elif bn == 2: st.playable = bool(bv)
                                elif bn == 3: st.update_complete = bool(bv)
                    elif sn == 4 and sw == 2:
                        for un, uw, uv in _fields(sv):
                            if un == 2 and uw == 1:
                                st.progress = struct.unpack("<d", uv)[0]
                            elif un == 4 and uw == 0:
                                st.total_bytes = uv
                            elif un == 5 and uw == 0:
                                st.remaining_bytes = uv
        out.append(st)
    return out


def read(path: Path = PRODUCT_DB) -> list[ProductStatus]:
    try:
        return parse(path.read_bytes())
    except (OSError, ValueError, IndexError, struct.error):
        return []


def find(launch_code: str, folder: str, products: list[ProductStatus] | None = None) -> ProductStatus | None:
    products = read() if products is None else products
    code = launch_code.lower()
    hint = folder.strip("_").lower()
    for p in products:
        if p.code.lower() == code or p.uid.lower() == code:
            return p
    for p in products:  # fall back to the install folder, e.g. ".../_forever_"
        if hint and (p.install_path.lower().rstrip("/\\").endswith(folder.lower())
                     or p.uid.lower().endswith(hint)):
            return p
    return None


def interface_number(version: str) -> int | None:
    """'1.60.1.71037' -> 16001 (the ## Interface value addons declare)."""
    try:
        major, minor, patch = (int(x) for x in version.split(".")[:3])
    except ValueError:
        return None
    return major * 10000 + minor * 100 + patch
