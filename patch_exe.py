"""
Patch JARVIS.exe: replaces the bytecode for
jarvis.ui.computer_use_overlay inside the embedded PYZ archive.

Run from the jarvis root:
    python patch_exe.py
"""
import marshal, os, shutil, struct, tempfile, zlib

EXE = r"dist\JARVIS.exe"
SRC = r"jarvis\ui\computer_use_overlay.py"

# ── 1. Compile the fixed source ───────────────────────────────────────────────
print("[1] Compiling fixed source ...")
with open(SRC, "r", encoding="utf-8") as fh:
    source = fh.read()
new_code_obj = compile(source, r"jarvis\ui\computer_use_overlay.py", "exec")

# ── 2. Read the EXE ───────────────────────────────────────────────────────────
print("[2] Reading EXE ...")
exe_bytes = bytearray(open(EXE, "rb").read())
print("    EXE size: {:,} bytes".format(len(exe_bytes)))

# ── 3. Locate the CArchive cookie ────────────────────────────────────────────
MAGIC = b"MEI\014\013\012\013\016"
cookie_pos = bytes(exe_bytes).rfind(MAGIC)
assert cookie_pos != -1, "PyInstaller MAGIC not found in EXE"

# Cookie: magic(8) + pkg_length(4) + toc_offset(4) + toc_length(4) + pyver(4) + pylib(64)
_COOKIE_FMT = "!8sIIII64s"
(_, pkg_len, toc_off, toc_sz, pyver, _) = struct.unpack_from(_COOKIE_FMT, exe_bytes, cookie_pos)
arch_start = len(exe_bytes) - pkg_len
print("    arch_start={:,}, pkg_len={:,}, toc_off={:,}, toc_sz={:,}".format(
    arch_start, pkg_len, toc_off, toc_sz))

# ── 4. Parse the CArchive TOC to find PYZ.pyz ────────────────────────────────
# TOC entry: entry_length(4) + offset(4) + length(4) + uncmpr_length(4) + cmpr_flag(1) + typecode(1) + name(padded)
_TOC_ENTRY_FMT  = "!IIIIBc"
_TOC_ENTRY_BASE = struct.calcsize(_TOC_ENTRY_FMT)   # 14 bytes

c_toc_abs = arch_start + toc_off
c_toc_raw = exe_bytes[c_toc_abs : c_toc_abs + toc_sz]

pyz_info = None
i = 0
while i < len(c_toc_raw):
    (entry_len, offset, length, uncmpr_len,
     cmpr_flag, typecode) = struct.unpack_from(_TOC_ENTRY_FMT, c_toc_raw, i)
    name = c_toc_raw[i + _TOC_ENTRY_BASE : i + entry_len].split(b"\x00")[0].decode()

    if name == "PYZ.pyz":
        pyz_info = (c_toc_abs + i, entry_len, offset, length, uncmpr_len)
        print("    PYZ.pyz: data_offset={:,}, length={:,}, cmpr_flag={}".format(
            offset, length, cmpr_flag))
        break
    i += entry_len

assert pyz_info is not None, "PYZ.pyz not found in CArchive TOC"
toc_entry_abs, toc_entry_len, pyz_data_offset, pyz_data_len, pyz_uncmpr_len = pyz_info

pyz_abs = arch_start + pyz_data_offset
print("    PYZ.pyz in EXE at [{:,} ... {:,}]".format(pyz_abs, pyz_abs + pyz_data_len))

assert exe_bytes[pyz_abs:pyz_abs+4] == b"PYZ\x00", \
    "Expected PYZ magic at {:,}, got {}".format(pyz_abs, exe_bytes[pyz_abs:pyz_abs+4])

# ── 5. Extract and parse the PYZ ─────────────────────────────────────────────
print("[3] Parsing PYZ archive ...")
pyz_raw = bytes(exe_bytes[pyz_abs : pyz_abs + pyz_data_len])

toc_offset_in_pyz = struct.unpack("!i", pyz_raw[8:12])[0]
pyz_toc_list = marshal.loads(pyz_raw[toc_offset_in_pyz:])
print("    PYZ modules: {:,}".format(len(pyz_toc_list)))

TARGET = "jarvis.ui.computer_use_overlay"
target_entry = next((e for e in pyz_toc_list if e[0] == TARGET), None)
assert target_entry is not None, "{!r} not found in PYZ".format(TARGET)
_, (orig_typecode, orig_off, orig_size) = target_entry
print("    Target: typecode={}, offset={:,}, cmpr_size={:,}".format(
    orig_typecode, orig_off, orig_size))

# ── 6. Compress the new bytecode ─────────────────────────────────────────────
print("[4] Compressing new bytecode ...")
new_blob = zlib.compress(marshal.dumps(new_code_obj), 6)
print("    Old size: {:,}  New size: {:,}".format(orig_size, len(new_blob)))

# ── 7. Rebuild PYZ data + TOC ────────────────────────────────────────────────
print("[5] Rebuilding PYZ ...")
# PYZ header is 17 bytes: 4 (magic) + 4 (py-magic) + 4 (toc_off) + 5 (padding zeros)
# TOC entry offsets are ABSOLUTE from byte 0 of the PYZ file; data starts at byte 17.
PYZ_HEADER = 17

data_section = bytearray()
new_toc_list = []

for entry_name, (typecode, off, size) in pyz_toc_list:
    if typecode == 2 or size == 0:
        new_toc_list.append((entry_name, (typecode, PYZ_HEADER + len(data_section), 0)))
        continue
    blob = new_blob if entry_name == TARGET else pyz_raw[off : off + size]
    new_off = PYZ_HEADER + len(data_section)   # absolute offset in new PYZ
    data_section += blob
    new_toc_list.append((entry_name, (typecode, new_off, len(blob))))

new_toc_bytes = marshal.dumps(new_toc_list)
new_pyz_toc_off = PYZ_HEADER + len(data_section)
new_pyz = (
    pyz_raw[:8]                              # PYZ\x00 + python magic (8 bytes)
    + struct.pack("!i", new_pyz_toc_off)     # updated TOC offset (4 bytes)
    + pyz_raw[12:17]                         # 5 bytes of padding zeros (preserved)
    + bytes(data_section)                    # data blobs start at byte 17
    + new_toc_bytes
)
delta_exe = len(new_pyz) - pyz_data_len
print("    Old PYZ size: {:,}  New PYZ size: {:,}  (delta={:+,})".format(
    pyz_data_len, len(new_pyz), delta_exe))

# ── 8. Splice new PYZ into exe_bytes ─────────────────────────────────────────
print("[6] Splicing into EXE ...")
exe_bytes[pyz_abs : pyz_abs + pyz_data_len] = new_pyz

# ── 9. Update CArchive TOC + cookie if size changed ──────────────────────────
if delta_exe != 0:
    # After the splice everything past pyz_abs has shifted by delta_exe.
    # Both the CArchive TOC and the cookie live AFTER the PYZ blob, so
    # their absolute positions have moved by delta_exe.
    new_toc_entry_abs = toc_entry_abs + delta_exe
    new_cookie_pos    = cookie_pos    + delta_exe

    # Update PYZ.pyz length fields in CArchive TOC entry
    # layout: entry_len(4) + offset(4) + length(4) + uncmpr_len(4) + ...
    new_length     = pyz_data_len   + delta_exe
    new_uncmpr_len = pyz_uncmpr_len + delta_exe
    struct.pack_into("!I", exe_bytes, new_toc_entry_abs + 8,  new_length)
    struct.pack_into("!I", exe_bytes, new_toc_entry_abs + 12, new_uncmpr_len)

    # Update cookie: toc_offset and pkg_length
    new_toc_off = toc_off + delta_exe
    new_pkg_len = pkg_len + delta_exe
    struct.pack_into("!I", exe_bytes, new_cookie_pos + 8,  new_pkg_len)
    struct.pack_into("!I", exe_bytes, new_cookie_pos + 12, new_toc_off)
    print("    pkg_len {:,} -> {:,}, toc_off {:,} -> {:,}".format(
        pkg_len, new_pkg_len, toc_off, new_toc_off))

# ── 10. Write patched EXE ────────────────────────────────────────────────────
backup = EXE + ".bak"
if not os.path.exists(backup):
    shutil.copy2(EXE, backup)
    print("[7] Backup saved -> {}".format(backup))
else:
    print("[7] Backup already exists (keeping original)")

with open(EXE, "wb") as fh:
    fh.write(exe_bytes)

print("")
print("Done! EXE size: {:,} bytes".format(len(exe_bytes)))
print("Launch JARVIS_debug.bat to test.")
