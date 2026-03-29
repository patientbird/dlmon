# dlmon

A zero-dependency terminal dashboard that monitors a directory for active downloads in real time. Detects transfers in progress, tracks speeds, shows file counts, and logs recent completions.

Works with any download tool — curl, wget, Python scripts, browsers, whatever. If files are landing in a directory, dlmon can watch them.

## Features

- **Active download detection** — identifies files still being written by comparing sizes between polls
- **Rolling speed** — 30-second average throughput
- **Progress bar + ETA** — when you provide an expected file count (manually or via `--url`)
- **Auto-detect extensions** — samples the directory and filters to the dominant file type
- **Remote file counting** — fetches an HTTP directory listing and counts files automatically
- **Watch mode** — scans a parent directory for the most recently active subdirectory
- **Zero dependencies** — Python 3.10+ standard library only
- **Cross-platform** — Windows (ANSI via Win32 API) and Unix

## Install

It's a single file. Put it wherever you want.

```bash
# Clone
git clone https://github.com/patientbird/dlmon.git

# Or just grab the file
curl -O https://raw.githubusercontent.com/patientbird/dlmon/main/dlmon.py
```

### Optional: global command

```bash
# Unix/macOS
ln -s /path/to/dlmon.py /usr/local/bin/dlmon

# Windows — create dlmon.cmd somewhere on your PATH
echo @python "C:\path\to\dlmon.py" %* > C:\Users\YOU\bin\dlmon.cmd
```

## Usage

```bash
# Monitor a specific directory
dlmon /path/to/downloads

# Auto-detect the most recently active subdirectory under a parent
dlmon --watch /data/downloads

# Monitor current directory
dlmon

# Filter to specific file types
dlmon /path/to/downloads --ext .zip .7z

# Show progress bar with a known total
dlmon /path/to/downloads --expected 500

# Auto-count expected files from a remote directory listing
dlmon /path/to/downloads --url https://example.com/files/

# Faster polling
dlmon /path/to/downloads --interval 0.5
```

## Dashboard

```
 dlmon  /data/downloads
============================================================
  Files:  186  (+12 this session)
  Size:   4.2 GB  (+312.5 MB)
  Speed:  8.4 MB/s
  Time:   2:34
  Goal:   [###########-------------------] 37.2%  186/500
  ETA:    ~4:18
============================================================
  ACTIVE (2)
    > archive-part-003.zip  142.8 MB  9.1 MB/s
    > archive-part-004.zip  28.3 MB  7.6 MB/s

  COMPLETED (recent)
    + archive-part-002.zip  256.0 MB  0:12 ago
    + archive-part-001.zip  248.7 MB  0:38 ago

  Ctrl+C to stop  |  Polling every 1.0s
```

## How It Works

Every poll cycle (default: 1 second), dlmon snapshots all files in the target directory. By comparing sizes between snapshots:

- **New file appeared** → active download
- **File size increased** → still downloading
- **File size unchanged** (was previously active) → just completed

This is tool-agnostic. It doesn't hook into curl or any specific downloader — it just watches the filesystem.

## Sidecar File (`.dlmon`)

Drop a `.dlmon` file in the download directory to automatically enable the progress bar — no flags needed.

```
url=https://example.com/files/
expected=500
```

| Key | Purpose |
|-----|---------|
| `url` | HTTP directory listing — dlmon counts the linked files |
| `expected` | Total file count (takes priority over `url`) |

Either key is optional. Your download script can write this file before starting, and dlmon will pick it up automatically.

```python
# Example: write .dlmon from a download script
with open(os.path.join(dest_dir, ".dlmon"), "w") as f:
    f.write(f"url={source_url}\n")
```

## Flags

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `directory` | | `.` | Directory to monitor |
| `--watch` | `-w` | | Parent directory — auto-selects the most recently modified subdirectory |
| `--url` | `-u` | | HTTP directory listing URL — counts files for progress bar |
| `--expected` | `-n` | | Expected total file count (manual, overrides `--url`) |
| `--ext` | `-e` | auto | File extensions to track (e.g. `.zip .7z`) |
| `--interval` | `-i` | `1.0` | Poll interval in seconds |

## Requirements

- Python 3.10+
- That's it

## License

MIT
