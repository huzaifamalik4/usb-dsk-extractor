#!/usr/bin/env python3
"""
USB DSK Image Extractor — recover files from raw USB disk backups (.dsk, .dd, .img, .iso).
"""

import argparse
import os
import sys

try:
    import pytsk3
except ImportError:
    print("Error: pytsk3 not installed. Run: pip install pytsk3", file=sys.stderr)
    sys.exit(1)

CHUNK_SIZE = 1024 * 1024
PROGRESS_EVERY = 100

INVALID_CHARS = set('\\/*?:"<>|')
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

SECTOR_SIZE = 512
FS_SIGNATURES = [
    (3, b'NTFS    ', 'NTFS'),
    (3, b'EXFAT   ', 'exFAT'),
    (82, b'FAT32   ', 'FAT32'),
    (82, b'FAT16   ', 'FAT16'),
    (82, b'FAT12   ', 'FAT12'),
]


def sanitize(name):
    name = "".join("_" if c in INVALID_CHARS else c for c in name).strip()
    if not name:
        name = "_unnamed"
    stem = name.rpartition(".")[0] if "." in name else name
    if stem.upper() in RESERVED or name.upper() in RESERVED:
        name = "_" + name
    return name


def long_path(path):
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(path)
    return path


def scan_filesystems(img):
    size = img.get_size()
    found = []
    scan_offsets = set()

    for off in range(0, min(8 * 1024 * 1024, size), SECTOR_SIZE):
        scan_offsets.add(off)
    for off in range(8 * 1024 * 1024, size, 1024 * 1024):
        scan_offsets.add(off)

    print("  Scanning for filesystems...")
    checked = 0
    for off in sorted(scan_offsets):
        if off >= size:
            continue
        sector = img.read(off, SECTOR_SIZE)
        if len(sector) < SECTOR_SIZE:
            continue
        checked += 1
        if checked % 5000 == 0:
            print(f"    Scanned {off // (1024*1024)} MB / {size // (1024*1024)} MB", end="\r", flush=True)

        for sig_off, sig_bytes, fs_name in FS_SIGNATURES:
            if sector[sig_off:sig_off + len(sig_bytes)] == sig_bytes:
                found.append((off, fs_name))
                print(f"\n    Found {fs_name} at sector {off // SECTOR_SIZE} (offset {off})")
                break

    print(f"\n    Scan complete: {checked} sectors checked, {len(found)} filesystem(s) found")
    return found


class Extractor:
    def __init__(self, image, output):
        self.image = image
        self.output = output
        self.total = 0
        self.ok = 0
        self.err = 0

    def run(self):
        os.makedirs(long_path(self.output), exist_ok=True)
        print(f"Opening image: {self.image}")
        img = pytsk3.Img_Info(self.image)

        offsets = []
        vols = None
        try:
            vols = pytsk3.Volume_Info(img)
        except OSError:
            pass

        has_partitions = False
        if vols:
            for v in vols:
                if not (v.flags & 1):
                    has_partitions = True
                    break

        if has_partitions:
            for v in vols:
                if v.flags & 1:
                    continue
                off = v.start * v.blocksize
                offsets.append((off, f"partition_{v.addr}: {v.desc}"))
        else:
            print("  No valid partition table found.")
            found = scan_filesystems(img)
            for off, fs_name in found:
                offsets.append((off, f"{fs_name} at sector {off // SECTOR_SIZE}"))

        if not offsets:
            print("  Trying offset 0 as a fallback...")
            offsets.append((0, "offset 0"))

        for off, label in offsets:
            print(f"\n--- {label} (offset {off}) ---")
            self._process_fs(img, off, os.path.join(self.output, label.replace(":", "_")))

        self._summary()

    def _process_fs(self, img, offset, out):
        os.makedirs(long_path(out), exist_ok=True)
        try:
            fs = pytsk3.FS_Info(img, offset=offset)
        except Exception as e:
            print(f"  Cannot open filesystem: {e}")
            return
        self._walk(fs, "/", out)

    def _resolve_dir_collision(self, path):
        if os.path.exists(long_path(path)) and not os.path.isdir(long_path(path)):
            base, name = os.path.split(path)
            path = os.path.join(base, name + "_dir")
            return self._resolve_dir_collision(path)
        return path

    def _resolve_file_collision(self, path):
        if os.path.exists(long_path(path)) and os.path.isdir(long_path(path)):
            base, name = os.path.split(path)
            stem, ext = os.path.splitext(name)
            path = os.path.join(base, stem + "_file" + ext)
            return self._resolve_file_collision(path)
        return path

    def _walk(self, fs, path, out):
        try:
            d = fs.open_dir(path)
        except Exception as e:
            print(f"  Cannot read directory {path}: {e}")
            return

        for e in d:
            nb = e.info.name.name
            if nb in (b".", b".."):
                continue

            name = nb.decode("utf-8", errors="replace")
            name = sanitize(name)
            if not name:
                continue

            sub = os.path.join(out, name)
            fsp = "/" + name if path == "/" else path + "/" + name

            meta = e.info.meta
            if meta and meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
                sub = self._resolve_dir_collision(sub)
                os.makedirs(long_path(sub), exist_ok=True)
                self._walk(fs, fsp, sub)
            else:
                sub = self._resolve_file_collision(sub)
                self._extract(fs, fsp, sub)

    def _extract(self, fs, fsp, sub):
        self.total += 1
        try:
            f = fs.open(fsp)
            sz = f.info.meta.size if f.info.meta else 0

            with open(long_path(sub), "wb") as fp:
                if sz > 0:
                    pos = 0
                    while pos < sz:
                        want = min(CHUNK_SIZE, sz - pos)
                        data = f.read_random(pos, want)
                        if not data:
                            break
                        fp.write(data)
                        pos += len(data)

            self.ok += 1
            if self.ok % PROGRESS_EVERY == 0:
                print(f"  Extracted {self.ok} files ...", end="\r", flush=True)
        except Exception:
            self.err += 1

    def _summary(self):
        print("\n")
        print("=" * 60)
        print(f"  Total files found:  {self.total}")
        print(f"  Extracted:          {self.ok}")
        print(f"  Skipped (errors):   {self.err}")
        print(f"  Output directory:   {self.output}")
        print("=" * 60)


CARVE_SIGNATURES = [
    (b'\xff\xd8\xff',           'jpg',  2000),
    (b'\x89PNG\r\n\x1a\n',      'png',  200),
    (b'\x00\x00\x00\x1cftyp',    'mp4',  5000),
    (b'\x00\x00\x00\x20ftyp',    'mp4',  5000),
    (b'\x00\x00\x00\x18ftyp',    'mov',  5000),
    (b'\x00\x00\x00\x14ftyp3gp', '3gp',  5000),
    (b'ftypmp4',                 'mp4',  5000),
    (b'ftyp3gp',                 '3gp',  5000),
    (b'ftypisom',                'mp4',  5000),
    (b'PK\x03\x04',              'zip',  200),
]


def carve_files(image_path, partition_offset, output_dir, max_files=500):
    import pytsk3
    print("\n=== File Carving (recovering deleted files from free space) ===")
    img = pytsk3.Img_Info(image_path)
    fs = pytsk3.FS_Info(img, offset=partition_offset)
    bm = fs.open('/' + chr(36) + 'Bitmap')
    bd = bm.read_random(0, bm.info.meta.size)
    tc = len(bd) * 8
    cluster_size = 4096

    ranges = []
    i = 0
    while i < tc:
        bi = i // 8
        if bi >= len(bd):
            break
        free = not ((bd[bi] >> (i % 8)) & 1)
        if free:
            s = i
            while i < tc:
                bi = i // 8
                if bi >= len(bd):
                    break
                if not ((bd[bi] >> (i % 8)) & 1):
                    i += 1
                else:
                    break
            ranges.append((s * cluster_size, (i - s) * cluster_size))
        i += 1

    total_free = sum(sz for _, sz in ranges)
    print(f"  Free space: {total_free / 1e9:.2f} GB across {len(ranges)} range(s)")

    carve_out = os.path.join(output_dir, "carved_files")
    os.makedirs(carve_out, exist_ok=True)
    carved = set()
    count = 0
    max_size = 200 * 1024 * 1024

    raw = open(image_path, 'rb')
    for r_idx, (r_start, r_size) in enumerate(ranges):
        if count >= max_files:
            break
        abs_start = partition_offset + r_start
        pos = 0
        buf_size = 4 * 1024 * 1024

        while pos < r_size and count < max_files:
            chunk = min(buf_size, r_size - pos)
            raw.seek(abs_start + pos)
            buf = raw.read(chunk)
            if not buf:
                break

            for magic, ext, min_sz in CARVE_SIGNATURES:
                off = 0
                while True:
                    if count >= max_files:
                        break
                    hit = buf.find(magic, off)
                    if hit == -1:
                        break
                    fstart = abs_start + pos + hit
                    if fstart in carved:
                        off = hit + 1
                        continue

                    remaining = r_size - (pos + hit)
                    carve_sz = min(max_size, remaining)
                    if carve_sz < min_sz:
                        off = hit + 1
                        continue

                    if ext == 'jpg':
                        raw.seek(fstart)
                        more = raw.read(min(carve_sz, max_size))
                        eoi = more.find(b'\xff\xd9')
                        if eoi == -1:
                            off = hit + 1
                            continue
                        carve_sz = eoi + 2

                    raw.seek(fstart)
                    data = raw.read(int(carve_sz))
                    if len(data) < min_sz:
                        off = hit + 1
                        continue
                    if ext == 'jpg' and data[:2] != b'\xff\xd8':
                        off = hit + 1
                        continue

                    fname = f"{ext}_{fstart}_{len(data)}.{ext}"
                    fpath = os.path.join(carve_out, fname)
                    with open(fpath, 'wb') as fp:
                        fp.write(data)
                    carved.add(fstart)
                    count += 1
                    if count % 50 == 0:
                        print(f"  Carved {count} files ...", end="\r", flush=True)
                    off = hit + 1
            pos += chunk
        print(f"  Range {r_idx + 1}/{len(ranges)} scanned ({count} files carved so far)")

    raw.close()
    print(f"  Carving complete: {count} files recovered")
    return count


def main():
    ap = argparse.ArgumentParser(
        description="Extract files from a raw USB disk image (.dsk, .dd, .img, .bin)."
    )
    ap.add_argument("image", help="Path to the disk image file")
    ap.add_argument(
        "output",
        nargs="?",
        default="extracted_data",
        help="Output directory (default: extracted_data)",
    )
    ap.add_argument(
        "--carve",
        action="store_true",
        help="Also scan free space for deleted files via signature carving",
    )
    a = ap.parse_args()

    if not os.path.isfile(a.image):
        print(f"Error: image file not found: {a.image}", file=sys.stderr)
        sys.exit(1)

    Extractor(os.path.abspath(a.image), os.path.abspath(a.output)).run()

    if a.carve:
        try:
            carve_files(
                os.path.abspath(a.image),
                2048 * 512,
                os.path.abspath(a.output),
            )
        except Exception as e:
            print(f"  Carving failed: {e}")


if __name__ == "__main__":
    main()
