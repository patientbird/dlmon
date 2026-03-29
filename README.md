# dlmon

A zero-dependency terminal dashboard that monitors a directory for active downloads in real time. Detects transfers in progress, tracks speeds, shows file counts, and logs recent completions.

Works with any download tool — curl, wget, Python scripts, browsers, whatever. If files are landing in a directory, dlmon can watch them.

## Features

- **Active download detection** — identifies files still being written by comparing sizes between polls
- **Rolling speed** — 30-second average throughput
- **Progress bar + ETA** — when you provide an expected file count (manually or via `--url`)
- **Estimated total size** — extrapolates from average file size when expected count is known
- **Multi-panel dashboard** — monitor multiple directories at once with `--also`
- **Auto-detect extensions** — samples the directory and filters to the dominant file type
- **Remote file counting** — fetches an HTTP directory listing and counts files automatically
- **Sidecar files** — drop a `.dlmon` file in any directory for automatic progress bars
- **Watch mode** — scans a parent directory for the most recently active subdirectory
- **Zero dependencies** — Python 3.10+ standard library only
- **Cross-platform** — Windows (ANSI via Win32 API) and Unix

## Important: How Monitoring Works

dlmon watches a **directory**, not a process. It detects downloads by watching for files that appear or grow in the target folder. This means:

- **Terminal downloads** (curl, wget, scripts) — point dlmon at the destination directory your script writes to
- **Browser downloads** — point dlmon at your browser's download folder (e.g. `~/Downloads` or wherever your browser saves files)
- **Any other tool** — same idea: point dlmon at wherever the files land

dlmon doesn't hook into any specific application. If a file is being written to the monitored directory, dlmon will see it — regardless of what's doing the writing.

When no downloads are active, dlmon still shows the current state of the directory (file count, total size, progress toward the expected total if known). This gives you an at-a-glance view of how complete a collection is.

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

# Monitor terminal downloads + browser downloads side by side
dlmon /path/to/scripts/output --also ~/Downloads

# Monitor multiple directories
dlmon /data/incoming --also /tmp/uploads ~/Downloads

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
 dlmon
============================================================
  TERMINAL  my-downloads
  Files: 186/500  (+12)
  Size:  4.2 GB  (~11.3 GB est.)  (+312.5 MB)
  Speed: 8.4 MB/s  Time: 2:34
  [###########-------------------] 37.2%  ETA ~4:18
    > archive-part-003.zip  142.8 MB  9.1 MB/s
    > archive-part-004.zip  28.3 MB  7.6 MB/s
    + archive-part-002.zip  256.0 MB  0:12 ago
    + archive-part-001.zip  248.7 MB  0:38 ago
------------------------------------------------------------
  DOWNLOADS  Downloads
  Files: 3  (+1)
  Size:  48.2 MB  (+15.7 MB)
  Speed: 2.1 MB/s  Time: 2:34
    > setup-v2.exe  15.7 MB  2.1 MB/s
============================================================
  Ctrl+C to stop  |  Polling every 1.0s
```

## How It Works

Every poll cycle (default: 1 second), dlmon snapshots all files in the target directory. By comparing sizes between snapshots:

- **New file appeared** → active download
- **File size increased** → still downloading
- **File size unchanged** (was previously active) → just completed

This is tool-agnostic. It doesn't hook into curl or any specific downloader — it just watches the filesystem. Any file being written to a monitored directory will be detected, whether it comes from a terminal script, a browser, a torrent client, or anything else.

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
| `--also` | `-a` | | Additional directories to watch (each gets its own panel) |
| `--url` | `-u` | | HTTP directory listing URL — counts files for progress bar |
| `--expected` | `-n` | | Expected total file count (manual, overrides `--url`) |
| `--ext` | `-e` | auto | File extensions to track (e.g. `.zip .7z`) |
| `--interval` | `-i` | `1.0` | Poll interval in seconds |

## Requirements

- Python 3.10+
- That's it

## License

MIT
