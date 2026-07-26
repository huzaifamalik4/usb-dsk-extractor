# USB DSK Image Extractor

Recover files from raw USB disk backups (`.dsk`, `.dd`, `.img`, `.bin`, `.iso`).

Takes a sector-by-sector disk image and extracts all readable files from any
filesystem found inside — even when the partition table is damaged or missing.

## Features

- **Automatic filesystem detection** — scans for NTFS, exFAT, FAT32, FAT16
- **Corrupt partition table support** — works with or without MBR/GPT
- **File carving** (`--carve`) — recovers deleted files from free space by
  scanning for JPEG, PNG, MP4, ZIP, and other signatures
- **Safe filenames** — handles invalid Windows characters, reserved names,
  duplicate names, long paths
- **Cross-platform** — works on Windows, macOS, Linux (anywhere Python runs)

## Requirements

- Python 3.8+
- [pytsk3](https://pypi.org/project/pytsk3/) — Python bindings for The Sleuth Kit

## Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/usb-dsk-extractor.git
cd usb-dsk-extractor

# Install dependencies
pip install pytsk3

# Optional: install as a command-line tool
pip install .
```

## Usage

```bash
# Basic extraction
python usb_dsk_extractor.py backup.dsk output_folder

# Also scan for deleted files (file carving)
python usb_dsk_extractor.py backup.dsk output_folder --carve

# Specify output directory
python usb_dsk_extractor.py "D:\USB Backup.dsk" "E:\recovered_data"

# If installed via pip
usb-dsk-extractor backup.dsk output_folder --carve
```

### Arguments

| Argument | Description |
|----------|-------------|
| `image` | Path to the raw disk image (`.dsk`, `.dd`, `.img`, `.bin`) |
| `output` | Output directory (default: `extracted_data`) |
| `--carve` | Enable file carving to recover deleted files from free space |

## How It Works

1. The tool opens the image with **The Sleuth Kit** (`pytsk3`)
2. It attempts to read the **partition table** (MBR/GPT)
3. If no valid partition table exists, it **scans for filesystem signatures**
   at common alignment boundaries (1 MB steps)
4. For each filesystem found, it **recursively walks the directory tree**
   and extracts every file
5. With `--carve`, it reads the **NTFS $Bitmap** to find free clusters,
   then scans those clusters for known file headers (magic bytes)

## Supported Filesystems

| Filesystem | Read | Write |
|------------|------|-------|
| NTFS       | Yes  | No    |
| exFAT      | Yes  | No    |
| FAT32      | Yes  | No    |
| FAT16      | Yes  | No    |
| FAT12      | Yes  | No    |
| ext2/3/4   | Yes  | No    |
| HFS+       | Yes  | No    |

## Troubleshooting

**"No valid partition table found"**
Most USB drives use GPT, which might be damaged if the backup was taken from
a failing drive. The tool automatically falls back to signature scanning — it
will find the filesystem even without a partition table.

**"Cannot determine file system type"**
The tool scans at 1 MB boundaries. If your filesystem is at a non-standard
offset, this may miss it. Try using a tool like `testdisk` first to locate
the partition, then pass the offset manually.

**"FileExistsError" on Windows**
Some files on the USB may have the same name (e.g. a 0-byte file and a
directory with the same name). The tool handles this by appending `_file` or
`_dir` suffixes automatically.

## License

[MIT](LICENSE)
