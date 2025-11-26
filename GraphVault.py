# -*- coding: utf-8 -*-
"""
GraphVault v2.3 – Ultra-fast Auto-MOC Generator + Smart Sync for Obsidian
Pure Python • Zero plugins • Blazing fast
"""

import os
import sys
import time
import json
import shutil
import gzip
from pathlib import Path
from collections import defaultdict, deque
from datetime import datetime

# ==================== CONFIGURATION ====================
SCRIPT_DIR = Path(__file__).parent
INPUT_FOLDER = SCRIPT_DIR / "input"
OUTPUT_FOLDER = SCRIPT_DIR / "graph-vault-archivos"
ATTACHMENTS_FOLDER = OUTPUT_FOLDER / "!_adjuntos"
CHECKPOINT_FILE = SCRIPT_DIR / "graph_checkpoint_v2.json.gz"
LOCK_FILE = SCRIPT_DIR / "graph_vault.lock"
LOG_FILE = SCRIPT_DIR / "graph_vault.log"

BATCH_SIZES = [100, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 5000]
DEFAULT_BATCH_INDEX = 2
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB

TEXT_EXT = {'.md', '.txt', '.pdf', '.docx', '.doc', '.rtf'}
CODE_EXT = {'.py', '.js', '.ts', '.jsx', '.html', '.css', '.java', '.cpp', '.c', '.go', '.rs', '.json', '.yaml', '.xml'}
MEDIA_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.mp4', '.mov', '.avi', '.mkv', '.mp3', '.wav', '.ogg'}
OTHER_EXT = {'.zip', '.rar', '.7z', '.csv', '.db', '.sqlite', '.xls', '.xlsx'}

ALL_EXT = TEXT_EXT | CODE_EXT | MEDIA_EXT | OTHER_EXT

IGNORE_DIRS = {".obsidian", ".git", ".trash", "attachments", "images", "img", "assets",
               "excalidraw", "canvas", "node_modules", "__pycache__", ".vscode", ".idea",
               "temp", "tmp", "cache", "logs", "backup", "build", "dist", ".npm", ".cache",
               "Thumbs.db", ".DS_Store"}

# =========================================================
# LOG + PROGRESS BAR
# =========================================================

def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    try:
        LOG_FILE.open("a", encoding="utf-8").write(line + "\n")
    except: pass

def print_progress(done: int, total: int, prefix: str = "", length: int = 50):
    if total == 0:
        percent = 100.0
    else:
        percent = 100 * (done / total)
    filled = int(length * done // total) if total > 0 else length
    bar = "█" * filled + "░" * (length - filled)
    line = f"\r{prefix} |{bar}| {done:,}/{total:,} ({percent:6.2f}%)"
    print(line, end="", flush=True)
    if done == total or done == 0:
        print()

# =========================================================

class WindowsLock:
    def __init__(self, lock_file): self.lock_file = lock_file; self.acquired = False
    def __enter__(self):
        if self.lock_file.exists():
            try:
                pid = self.lock_file.read_text().strip()
                print(f"\nAnother instance is already running (PID {pid}) → Close it first!")
                sys.exit(1)
            except: pass
        self.lock_file.write_text(str(os.getpid()))
        self.acquired = True
        return self
    def __exit__(self, *args):
        if self.acquired and self.lock_file.exists():
            try: self.lock_file.unlink()
            except: pass

class GraphVaultPro:
    def __init__(self):
        self.input = INPUT_FOLDER
        self.output = OUTPUT_FOLDER
        self.attach = ATTACHMENTS_FOLDER
        self.output.mkdir(exist_ok=True)
        self.attach.mkdir(exist_ok=True)

        self.folders = {}
        self.processed_folders = set()
        self.processed_files = set()
        self.stats = {"copied": 0, "linked": 0, "batches": 0}
        self.mode = "folders"
        self.batch_idx = DEFAULT_BATCH_INDEX

        print("GraphVault v2.3 – Ultra-fast Auto-MOC Generator")
        log("=== GraphVault v2.3 STARTED ===")
        self.load_checkpoint()
        if not self.folders:
            self.scan()
        else:
            log(f"Structure loaded: {len(self.folders):,} folders")

    def scan(self):
        print("Scanning input folder...", flush=True)
        log("Scanning...")
        start = time.time()
        self.folders.clear()

        queue = deque([(self.input, 0)])
        total_files = folder_count = scanned = 0

        while queue:
            folder, level = queue.popleft()
            scanned += 1
            if scanned % 100 == 0 or not queue:
                print(f"\rScanning... {scanned + len(queue):,} folders processed", end="", flush=True)

            rel = folder.relative_to(self.input)
            rel_str = str(rel) if rel != Path('.') else ''

            if folder.name in IGNORE_DIRS or folder.name.startswith('.'):
                continue

            try:
                entries = list(folder.iterdir())
            except (PermissionError, OSError):
                log(f"Access denied: {folder}")
                continue

            files = []

            # Subfolders first
            for sub in entries:
                if sub.is_dir() and sub.name not in IGNORE_DIRS and not sub.name.startswith('.'):
                    queue.append((sub, level + 1))

            # Files
            for f in entries:
                if f.is_file() and f.suffix.lower() in ALL_EXT and not f.name.startswith('.'):
                    info = self.analyze_file(f)
                    if info:
                        files.append(info)
                        total_files += 1

            if files or level == 0:
                self.folders[rel_str] = {
                    "path": folder, "rel": rel, "name": folder.name if rel_str else "ROOT",
                    "level": level, "files": files, "file_count": len(files),
                    "children": [], "parent": str(rel.parent) if rel_str and rel.parent != Path('.') else None
                }
                folder_count += 1

        # Build tree
        for key, info in self.folders.items():
            if info["parent"] and info["parent"] in self.folders:
                self.folders[info["parent"]]["children"].append(key)
        for info in self.folders.values():
            info["children"].sort(key=lambda x: self.folders[x]["name"].lower())

        elapsed = time.time() - start
        print(f"\nDone → {folder_count:,} folders | {total_files:,} files | {elapsed:.1f}s")
        log(f"Scan completed in {elapsed:.1f}s → {folder_count:,} folders")

    def analyze_file(self, path: Path):
        try:
            size = path.stat().st_size
            ext = path.suffix.lower()
            cat = "other"
            if ext in TEXT_EXT: cat = "text"
            elif ext in CODE_EXT: cat = "code"
            elif ext in MEDIA_EXT:
                if ext in {'.jpg','.jpeg','.png','.gif','.webp','.svg'}: cat = "image"
                elif ext in {'.mp4','.mov','.avi','.mkv'}: cat = "video"
                else: cat = "audio"
            elif ext in {'.csv','.db','.sqlite'}: cat = "data"
            elif ext in {'.zip','.rar','.7z'}: cat = "archive"

            return {
                "path": path, "name": path.name, "stem": path.stem, "ext": ext,
                "size": size, "mb": round(size / (1024*1024), 2), "cat": cat,
                "rel": path.relative_to(self.input), "copy": size <= MAX_FILE_SIZE
            }
        except: return None

    def process_batch(self):
        pending = [k for k in self.folders if k not in self.processed_folders]
        pending.sort(key=lambda x: (self.folders[x]["level"], self.folders[x]["name"].lower()))
        if not pending:
            print("100% COMPLETED")
            log("ALL FOLDERS PROCESSED")
            self.create_root_index()
            return

        total = len(self.folders)
        done = len(self.processed_folders)
        batch = pending[:BATCH_SIZES[self.batch_idx]]

        print(f"\nFOLDERS → +{len(batch)}", flush=True)
        log(f"Processing folder batch: +{len(batch)}")

        for i, rel_str in enumerate(batch, 1):
            self.create_moc_for_folder(rel_str)
            self.processed_folders.add(rel_str)
            print_progress(done + i, total, prefix="FOLDERS")

        self.stats["batches"] += 1
        self.save_checkpoint()
        self.create_root_index()

    def create_moc_for_folder(self, rel_str: str):
        info = self.folders.get(rel_str)
        if not info: return

        out_path = self.output / rel_str
        out_path.mkdir(parents=True, exist_ok=True)
        moc_path = out_path / f"{info['name']}.md"

        lines = [f"# {info['name']}\n", f"*Level {info['level']} | {info['file_count']} files*\n\n"]

        if info["parent"] and info["parent"] in self.folders:
            lines += [f"## Parent\n- [[{self.folders[info['parent']]['name']}]]\n\n"]

        if info["children"]:
            lines.append("## Subfolders\n")
            for child in info["children"]:
                lines.append(f"- [[{self.folders[child]['name']}]]\n")
            lines.append("\n")

        processed_files = [f for f in info["files"] if str(f["rel"]) in self.processed_files]
        by_cat = defaultdict(list)
        for f in processed_files:
            by_cat[f["cat"]].append(f)

        for cat in ["text", "code", "image", "video", "audio", "data", "archive", "other"]:
            if cat in by_cat:
                lines.append(f"## {cat.title()}\n")
                for f in sorted(by_cat[cat], key=lambda x: x["name"].lower()):
                    link = self.get_obsidian_link(f, out_path)
                    lines.append(f"- {link} ({f['mb']} MB)\n")
                lines.append("\n")

        if not processed_files and info["children"]:
            lines.append("*Navigation folder*\n")

        lines.append("---\n*GraphVault v2.3*")
        moc_path.write_text("".join(lines), encoding="utf-8")

    def get_obsidian_link(self, file_info, target_folder):
        name = file_info["name"]
        if file_info["copy"]:
            dest = target_folder / name
            if not dest.exists():
                shutil.copy2(file_info["path"], dest)
                self.stats["copied"] += 1
            return f"![[{name}]]" if file_info["ext"] in MEDIA_EXT else f"[[{name}]]"
        else:
            proxy = self.attach / f"{file_info['stem']}.md"
            if not proxy.exists():
                proxy.write_text(f"# {name}\n*Large file → {file_info['mb']} MB*\n`{file_info['path']}`", encoding="utf-8")
            self.stats["linked"] += 1
            return f"[[!_adjuntos/{file_info['stem']}]]"

    def copy_or_link_file(self, file_info, target_folder):
        if str(file_info["rel"]) in self.processed_files: return
        self.get_obsidian_link(file_info, target_folder)

    def sync_deletions(self):
        print("\nSyncing deletions...", end="", flush=True)
        log("Syncing deletions...")
        expected_folders = set(self.folders.keys())
        expected_files = {str(f["rel"]) for info in self.folders.values() for f in info["files"]}
        deleted = 0

        for p in self.output.rglob("*"):
            if p.is_dir() and p != self.attach:
                try:
                    rel = str(p.relative_to(self.output))
                    if rel and rel not in expected_folders:
                        shutil.rmtree(p)
                        deleted += 1
                except: pass
            elif p.suffix == ".md" and self.attach not in p.parents:
                try:
                    rel = str(p.relative_to(self.output))
                    is_moc = p.stem == p.parent.name
                    parent_rel = str(p.parent.relative_to(self.output))
                    if (not is_moc and rel not in expected_files) or (is_moc and parent_rel not in expected_folders):
                        p.unlink()
                        deleted += 1
                except: pass

        for p in self.attach.glob("*.md"):
            if not any(p.stem == f["stem"] for info in self.folders.values() for f in info["files"] if not f["copy"]):
                p.unlink()
                deleted += 1

        print(f" → {deleted} items removed")
        log(f"Sync completed: {deleted} items deleted")

    def create_root_index(self):
        path = self.output / "Main Index.md"
        lines = ["# GraphVault – Main Index\n\n"]
        level1 = [k for k, v in self.folders.items() if v["level"] == 1]
        if level1:
            lines.append("## Top-level Folders\n")
            for k in sorted(level1, key=lambda x: self.folders[x]["name"].lower()):
                lines.append(f"- [[{self.folders[k]['name']}]]\n")

        total_f = len(self.folders)
        done_f = len(self.processed_folders)
        total_files = sum(info["file_count"] for info in self.folders.values())
        done_files = len(self.processed_files)

        lines += [
            f"\n## Status ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n",
            f"- Folders: **{done_f:,}/{total_f:,}** ({done_f/total_f*100:.1f}%)\n",
            f"- Files: **{done_files:,}/{total_files:,}** ({done_files/total_files*100:.1f}%)\n",
            f"- Mode: **{self.mode.upper()}**\n"
        ]
        path.write_text("".join(lines), encoding="utf-8")

    def save_checkpoint(self):
        data = {
            "processed_folders": list(self.processed_folders),
            "processed_files": list(self.processed_files),
            "stats": self.stats,
            "mode": self.mode,
            "batch_idx": self.batch_idx
        }
        try:
            CHECKPOINT_FILE.write_bytes(gzip.compress(json.dumps(data).encode('utf-8')))
            log("Checkpoint saved")
        except: log("ERROR saving checkpoint")

    def load_checkpoint(self):
        if not CHECKPOINT_FILE.exists(): return
        try:
            raw = gzip.decompress(CHECKPOINT_FILE.read_bytes())
            data = json.loads(raw)
            self.processed_folders = set(data.get("processed_folders", []))
            self.processed_files = set(data.get("processed_files", []))
            self.stats = data.get("stats", {"copied": 0, "linked": 0, "batches": 0})
            self.mode = data.get("mode", "folders")
            self.batch_idx = data.get("batch_idx", DEFAULT_BATCH_INDEX)
            log(f"Checkpoint loaded → {self.stats['batches']} batches | {len(self.processed_folders):,} folders")
        except Exception as e:
            log(f"Corrupted checkpoint → ignored ({e})")

    def dashboard(self):
        total_f = len(self.folders)
        done_f = len(self.processed_folders)
        total_files = sum(v["file_count"] for v in self.folders.values())
        done_files = len(self.processed_files)

        print("\n" + "═" * 72)
        print("       GraphVault v2.3 – Ultra-fast Auto-MOC Generator")
        print("═" * 72)
        print_progress(done_f, total_f, prefix="FOLDERS ")
        print_progress(done_files, total_files, prefix="FILES   ")
        print(f"   Batch: {BATCH_SIZES[self.batch_idx]:,} │ Mode: {self.mode.upper()} │ Log: {LOG_FILE.name}")
        print()
        print("   [Enter] Process    1-9 Batch size    m Mode    r Rescan    s Sync deletions    q Quit")
        print("─" * 72)

    def run(self):
        print("Ready! Press Enter to start.")
        log("System ready")
        while True:
            self.dashboard()
            try:
                cmd = input("→ ").strip().lower()
                if cmd == "": 
                    self.process_batch() if self.mode == "folders" else self.process_file_batch()
                elif cmd in "123456789":
                    idx = int(cmd) - 1
                    if 0 <= idx < len(BATCH_SIZES):
                        self.batch_idx = idx
                        log(f"Batch size → {BATCH_SIZES[idx]}")
                elif cmd == "m":
                    self.mode = "files" if self.mode == "folders" else "folders"
                    log(f"Mode → {self.mode}")
                elif cmd == "r":
                    log("RESCANNING EVERYTHING")
                    self.processed_folders.clear()
                    self.processed_files.clear()
                    self.scan()
                    self.sync_deletions()
                elif cmd == "s":
                    self.sync_deletions()
                elif cmd == "q":
                    log("EXITING")
                    self.save_checkpoint()
                    print("See you next time!")
                    break
            except KeyboardInterrupt:
                log("INTERRUPTED – Saving state")
                self.save_checkpoint()
                break

def main():
    if not INPUT_FOLDER.exists():
        print("\nCREATE A FOLDER NAMED 'input' HERE:")
        print(f"   {SCRIPT_DIR}")
        input("Press Enter to exit...")
        return
    with WindowsLock(LOCK_FILE):
        GraphVaultPro().run()

if __name__ == "__main__":
    main()
