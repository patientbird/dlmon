"""
dlmon - Download directory monitor.

Watches a directory and shows live download progress:
active transfers, speeds, file counts, and recent completions.

Usage:
    dlmon /path/to/downloads
    dlmon /path/to/downloads --url https://example.com/files/
    dlmon /path/to/downloads --expected 500 --ext .zip
    dlmon --watch /data --interval 0.5
"""
import argparse
import ctypes
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path

# ── ANSI ─────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
WHITE = "\033[97m"
CURSOR_HOME = "\033[H"
CLEAR_TO_END = "\033[J"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

# ── Helpers ──────────────────────────────────────────────────────


def count_remote_files(url: str, extensions: list[str] | None = None) -> int:
    """Fetch an HTTP directory listing and count linked files."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    hrefs = re.findall(r'href="([^"]+)"', html)

    if extensions:
        return sum(
            1 for h in hrefs
            if any(urllib.parse.unquote(h).lower().endswith(ext) for ext in extensions)
        )
    return sum(
        1 for h in hrefs
        if not h.startswith("?") and not h.startswith("/") and not h.startswith("#")
        and "." in h.split("/")[-1]
    )


def find_active_download_dir(root: Path) -> Path | None:
    """Find the subdirectory under *root* modified most recently (within the last hour)."""
    best_dir = None
    best_mtime = 0.0
    cutoff = time.time() - 3600

    for subdir in root.iterdir():
        if not subdir.is_dir():
            continue
        try:
            dir_mtime = subdir.stat().st_mtime
            if dir_mtime > cutoff and dir_mtime > best_mtime:
                best_mtime = dir_mtime
                best_dir = subdir
        except OSError:
            continue

    return best_dir


def detect_extensions(directory: Path, sample: int = 50) -> list[str] | None:
    """Sample files in a directory and return the dominant extension (if >80%)."""
    ext_counts: dict[str, int] = {}
    count = 0
    try:
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
            count += 1
            if count >= sample:
                break
    except OSError:
        return None

    if not ext_counts:
        return None

    top_ext = max(ext_counts, key=ext_counts.get)
    if ext_counts[top_ext] / count > 0.8:
        return [top_ext]
    return None


def enable_ansi_windows():
    """Enable ANSI escape code processing on Windows."""
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


def fmt_speed(bps: float) -> str:
    if bps <= 0:
        return "---"
    return f"{fmt_size(int(bps))}/s"


def fmt_duration(secs: float) -> str:
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def bar(fraction: float, width: int = 30) -> str:
    filled = int(fraction * width)
    empty = width - filled
    pct = fraction * 100
    return f"{CYAN}[{'#' * filled}{'-' * empty}]{RESET} {pct:.1f}%"


# ── Data types ───────────────────────────────────────────────────

@dataclass
class FileSnapshot:
    path: str
    size: int
    mtime: float


@dataclass
class ActiveDownload:
    name: str
    size: int
    prev_size: int
    speed: float
    first_seen: float


@dataclass
class CompletedFile:
    name: str
    size: int
    completed_at: float


# ── Monitor ──────────────────────────────────────────────────────

class DownloadMonitor:
    def __init__(self, directory: str, extensions: list[str] | None = None,
                 expected: int | None = None, interval: float = 1.0):
        self.directory = Path(directory)
        self.extensions = [e.lower() for e in extensions] if extensions else None
        self.expected = expected
        self.interval = interval

        self.prev_snapshot: dict[str, FileSnapshot] = {}
        self.active: dict[str, ActiveDownload] = {}
        self.recent_completed: deque[CompletedFile] = deque(maxlen=8)
        self.start_time = time.time()
        self.total_downloaded_bytes = 0
        self.files_completed_this_session = 0
        self.initial_file_count = 0
        self.initial_total_size = 0
        self.first_scan = True
        self.speed_samples: deque[tuple[float, int]] = deque(maxlen=30)

    def scan(self) -> dict[str, FileSnapshot]:
        result = {}
        try:
            for entry in self.directory.iterdir():
                if not entry.is_file():
                    continue
                name = entry.name
                if self.extensions:
                    if not any(name.lower().endswith(ext) for ext in self.extensions):
                        continue
                try:
                    stat = entry.stat()
                    result[name] = FileSnapshot(
                        path=str(entry), size=stat.st_size, mtime=stat.st_mtime,
                    )
                except OSError:
                    pass
        except OSError as e:
            print(f"{RED}Error scanning directory: {e}{RESET}")
        return result

    def update(self):
        now = time.time()
        current = self.scan()

        if self.first_scan:
            self.initial_file_count = len(current)
            self.initial_total_size = sum(f.size for f in current.values())
            self.first_scan = False
            self.prev_snapshot = current
            return

        bytes_this_cycle = 0
        new_active: dict[str, ActiveDownload] = {}

        for name, snap in current.items():
            prev = self.prev_snapshot.get(name)

            if prev is None:
                speed = snap.size / self.interval if self.interval > 0 else 0
                bytes_this_cycle += snap.size
                if snap.size > 0:
                    new_active[name] = ActiveDownload(
                        name=name, size=snap.size, prev_size=0,
                        speed=speed, first_seen=now,
                    )
            elif snap.size != prev.size:
                delta = snap.size - prev.size
                speed = delta / self.interval if self.interval > 0 else 0
                bytes_this_cycle += max(delta, 0)
                existing = self.active.get(name)
                new_active[name] = ActiveDownload(
                    name=name, size=snap.size, prev_size=prev.size,
                    speed=speed,
                    first_seen=existing.first_seen if existing else now,
                )
            else:
                if name in self.active:
                    self.recent_completed.append(
                        CompletedFile(name=name, size=snap.size, completed_at=now)
                    )
                    self.files_completed_this_session += 1

        recently_completed_names = {c.name for c in self.recent_completed}
        for name in self.active:
            if name not in new_active and name in current and name not in recently_completed_names:
                snap = current[name]
                self.recent_completed.append(
                    CompletedFile(name=name, size=snap.size, completed_at=now)
                )
                self.files_completed_this_session += 1

        self.active = new_active
        self.total_downloaded_bytes += bytes_this_cycle

        if bytes_this_cycle > 0:
            self.speed_samples.append((now, bytes_this_cycle))

        self.prev_snapshot = current

    def get_rolling_speed(self) -> float:
        if not self.speed_samples:
            return 0.0
        now = time.time()
        recent = [(t, b) for t, b in self.speed_samples if now - t < 30]
        if not recent:
            return 0.0
        total_bytes = sum(b for _, b in recent)
        span = now - recent[0][0]
        if span <= 0:
            return total_bytes / self.interval
        return total_bytes / span

    def render(self) -> str:
        now = time.time()
        elapsed = now - self.start_time
        current_files = len(self.prev_snapshot)
        current_size = sum(f.size for f in self.prev_snapshot.values())
        new_files = current_files - self.initial_file_count
        new_bytes = current_size - self.initial_total_size
        speed = self.get_rolling_speed()

        lines: list[str] = []

        lines.append(f"{BOLD}{CYAN} dlmon{RESET}  {DIM}{self.directory}{RESET}")
        lines.append(f"{DIM}{'=' * 60}{RESET}")

        lines.append(
            f"  {WHITE}Files:{RESET}  {BOLD}{current_files}{RESET}"
            + (f"  {DIM}(+{new_files} this session){RESET}" if new_files > 0 else "")
        )
        lines.append(
            f"  {WHITE}Size:{RESET}   {BOLD}{fmt_size(current_size)}{RESET}"
            + (f"  {DIM}(+{fmt_size(new_bytes)}){RESET}" if new_bytes > 0 else "")
        )
        lines.append(f"  {WHITE}Speed:{RESET}  {BOLD}{fmt_speed(speed)}{RESET}")
        lines.append(f"  {WHITE}Time:{RESET}   {fmt_duration(elapsed)}")

        if self.expected and self.expected > 0:
            frac = min(current_files / self.expected, 1.0)
            lines.append(f"  {WHITE}Goal:{RESET}   {bar(frac)}  {current_files}/{self.expected}")

            if new_files > 0 and self.files_completed_this_session > 0:
                rate = self.files_completed_this_session / elapsed if elapsed > 0 else 0
                remaining = self.expected - current_files
                if rate > 0 and remaining > 0:
                    eta = remaining / rate
                    lines.append(f"  {WHITE}ETA:{RESET}    ~{fmt_duration(eta)}")

        lines.append(f"{DIM}{'=' * 60}{RESET}")

        if self.active:
            lines.append(f"  {YELLOW}ACTIVE ({len(self.active)}){RESET}")
            sorted_active = sorted(self.active.values(), key=lambda a: a.name)
            for dl in sorted_active[:10]:
                name_display = dl.name if len(dl.name) <= 45 else "..." + dl.name[-42:]
                lines.append(
                    f"    {YELLOW}>{RESET} {name_display}"
                    f"  {DIM}{fmt_size(dl.size)}  {fmt_speed(dl.speed)}{RESET}"
                )
            if len(sorted_active) > 10:
                lines.append(f"    {DIM}  ...and {len(sorted_active) - 10} more{RESET}")
        else:
            lines.append(f"  {DIM}No active downloads{RESET}")

        if self.recent_completed:
            lines.append(f"\n  {GREEN}COMPLETED (recent){RESET}")
            for comp in reversed(list(self.recent_completed)):
                age = now - comp.completed_at
                name_display = comp.name if len(comp.name) <= 45 else "..." + comp.name[-42:]
                lines.append(
                    f"    {GREEN}+{RESET} {name_display}"
                    f"  {DIM}{fmt_size(comp.size)}  {fmt_duration(age)} ago{RESET}"
                )

        lines.append(f"\n{DIM}  Ctrl+C to stop  |  Polling every {self.interval}s{RESET}")

        return "\n".join(lines)

    def run(self):
        print(HIDE_CURSOR, end="", flush=True)
        print("\033[2J", end="", flush=True)
        try:
            while True:
                self.update()
                output = self.render()
                print(CURSOR_HOME + output + CLEAR_TO_END, end="", flush=True)
                time.sleep(self.interval)
        except KeyboardInterrupt:
            pass
        finally:
            print(SHOW_CURSOR, end="", flush=True)
            print(f"\n{GREEN}Monitor stopped.{RESET}")


# ── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Monitor a directory for download progress.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  dlmon /path/to/downloads
  dlmon /data/incoming --url https://example.com/files/
  dlmon /data/incoming --expected 500 --ext .zip
  dlmon --watch /data --interval 0.5""",
    )
    parser.add_argument("directory", nargs="?", default=None,
                        help="Directory to monitor (default: current directory)")
    parser.add_argument(
        "--watch", "-w", default=None,
        help="Parent directory to scan for the most recently active subdirectory",
    )
    parser.add_argument(
        "--url", "-u", default=None,
        help="Remote directory listing URL to auto-count expected files",
    )
    parser.add_argument(
        "--expected", "-n", type=int, default=None,
        help="Expected total file count (enables progress bar + ETA)",
    )
    parser.add_argument(
        "--ext", "-e", nargs="+", default=None,
        help="File extensions to track (e.g. .zip .7z). Auto-detected if omitted",
    )
    parser.add_argument(
        "--interval", "-i", type=float, default=1.0,
        help="Poll interval in seconds (default: 1.0)",
    )
    args = parser.parse_args()

    enable_ansi_windows()

    # ── Resolve directory ──
    if args.directory:
        directory = Path(args.directory)
    elif args.watch:
        watch_root = Path(args.watch)
        if not watch_root.is_dir():
            print(f"{RED}Error: watch directory '{watch_root}' not found{RESET}")
            sys.exit(1)
        print(f"{CYAN}Scanning for active downloads...{RESET}")
        directory = find_active_download_dir(watch_root)
        if directory is None:
            print(f"{RED}No recently active subdirectories found under {watch_root}{RESET}")
            print(f"{DIM}Tip: pass a directory path directly, or start a download first{RESET}")
            sys.exit(1)
        print(f"{GREEN}Found:{RESET} {directory.name}")
    else:
        directory = Path.cwd()

    if not directory.is_dir():
        print(f"{RED}Error: '{directory}' is not a directory{RESET}")
        sys.exit(1)

    # ── Auto-detect extensions ──
    exts = None
    if args.ext:
        exts = [e if e.startswith(".") else f".{e}" for e in args.ext]
    else:
        exts = detect_extensions(directory)

    # ── Resolve expected count ──
    expected = args.expected
    if expected is None and args.url:
        print(f"{CYAN}Fetching remote file count...{RESET}")
        try:
            expected = count_remote_files(args.url, exts)
            print(f"{CYAN}Remote files:{RESET} {expected}")
        except Exception as e:
            print(f"{YELLOW}Warning: couldn't fetch remote count: {e}{RESET}")

    # ── Start ──
    monitor = DownloadMonitor(
        directory=str(directory),
        extensions=exts,
        expected=expected,
        interval=args.interval,
    )

    file_count = len(monitor.scan())
    print(f"{CYAN}Monitoring:{RESET} {directory}")
    print(f"{CYAN}Files:{RESET} {file_count}" + (f"  {CYAN}Ext:{RESET} {', '.join(exts)}" if exts else ""))
    if expected:
        print(f"{CYAN}Expected:{RESET} {expected}")
    print(f"\nStarting in 1s...")
    time.sleep(1)

    monitor.prev_snapshot = monitor.scan()
    monitor.first_scan = False
    monitor.initial_file_count = len(monitor.prev_snapshot)
    monitor.initial_total_size = sum(f.size for f in monitor.prev_snapshot.values())

    monitor.run()


if __name__ == "__main__":
    main()
