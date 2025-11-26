# -*- coding: utf-8 -*-
"""
GRAPH VAULT 2.2 – LA VERSIÓN QUE TODOS QUERÍAN (AHORA SÍ DE VERDAD)
→ Carpetas y archivos suben siempre juntos (da igual el modo)
→ MOC creado desde el primer archivo
→ Modo FOLDERS ahora también copia/enlaza archivos → progreso REAL
→ Consola aún más épica
"""

import os
import sys
import time
import json
import shutil
import gzip
from pathlib import Path
from collections import defaultdict, deque

# ==================== CONFIGURACIÓN ====================
SCRIPT_DIR = Path(__file__).parent
INPUT_FOLDER = SCRIPT_DIR / "input"
OUTPUT_FOLDER = SCRIPT_DIR / "graph-vault-archivos"
ATTACHMENTS_FOLDER = OUTPUT_FOLDER / "!_adjuntos"
CHECKPOINT_FILE = SCRIPT_DIR / "graph_checkpoint_v2.json.gz"
LOCK_FILE = SCRIPT_DIR / "graph_vault.lock"

BATCH_SIZES = [100, 200, 300, 500, 750, 1000, 1500, 2000, 3000, 5000]
DEFAULT_BATCH_INDEX = 5  # arrancamos en 750 (el punto dulce)

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB → se copian, más grandes → proxy

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

class WindowsLock:
    def __init__(self, lock_file): self.lock_file = lock_file; self.acquired = False
    def __enter__(self):
        if self.lock_file.exists():
            try:
                pid = self.lock_file.read_text().strip()
                print(f"YA HAY OTRA INSTANCIA (PID {pid}) → CIÉRRALA")
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
        self.mode = "folders"        # ahora es el modo rey
        self.batch_idx = DEFAULT_BATCH_INDEX

        print("Iniciando Graph Vault 2.2 – LA BESTIA DEFINITIVA")
        self.load_checkpoint()
        if not self.folders:
            self.scan()
        else:
            print(f"Estructura cargada: {len(self.folders):,} carpetas")

    def scan(self):
        print("Escaneando carpeta input (BFS)... ", end="", flush=True)
        start = time.time()
        self.folders.clear()

        queue = deque([(self.input, 0)])
        total_files = 0
        folder_count = 0

        while queue:
            folder, level = queue.popleft()
            rel = folder.relative_to(self.input)
            rel_str = str(rel) if rel != Path('.') else ''

            if folder.name in IGNORE_DIRS or folder.name.startswith('.'):
                continue

            for sub in folder.iterdir():
                if sub.is_dir() and sub.name not in IGNORE_DIRS and not sub.name.startswith('.'):
                    queue.append((sub, level + 1))

            files = []
            for f in folder.iterdir():
                if f.is_file() and f.suffix.lower() in ALL_EXT and not f.name.startswith('.'):
                    info = self.analyze_file(f)
                    if info:
                        files.append(info)
                        total_files += 1

            if files or level == 0:
                self.folders[rel_str] = {
                    "path": folder,
                    "rel": rel,
                    "name": folder.name if rel_str else "ROOT",
                    "level": level,
                    "files": files,
                    "file_count": len(files),
                    "children": [],
                    "parent": str(rel.parent) if rel_str and rel.parent != Path('.') else None
                }
                folder_count += 1
                if folder_count % 1000 == 0:
                    print(f"{folder_count:,} carpetas...", end="", flush=True)

        # Jerarquía
        for key, info in self.folders.items():
            if info["parent"] and info["parent"] in self.folders:
                self.folders[info["parent"]]["children"].append(key)

        for info in self.folders.values():
            info["children"].sort(key=lambda x: self.folders[x]["name"].lower())

        elapsed = time.time() - start
        print(f"\nEscaneo completo → {len(self.folders):,} carpetas | {total_files:,} archivos | {elapsed:.1f}s")

    def analyze_file(self, path: Path):
        try:
            size = path.stat().st_size
            ext = path.suffix.lower()
            cat = "otros"
            if ext in TEXT_EXT: cat = "texto"
            elif ext in CODE_EXT: cat = "código"
            elif ext in MEDIA_EXT:
                if ext in {'.jpg','.jpeg','.png','.gif','.webp','.svg'}: cat = "imagen"
                elif ext in {'.mp4','.mov','.avi','.mkv'}: cat = "video"
                else: cat = "audio"
            elif ext in {'.csv','.db','.sqlite'}: cat = "datos"
            elif ext in {'.zip','.rar','.7z'}: cat = "archivo"

            return {
                "path": path, "name": path.name, "stem": path.stem, "ext": ext,
                "size": size, "mb": round(size / (1024*1024), 2), "cat": cat,
                "rel": path.relative_to(self.input), "copy": size <= MAX_FILE_SIZE
            }
        except: return None

    def get_pending_folders(self):
        pending = [k for k in self.folders if k not in self.processed_folders]
        pending.sort(key=lambda x: (self.folders[x]["level"], self.folders[x]["name"].lower()))
        return pending

    # ←←← LA FUNCIÓN MÁGICA QUE LO ARREGLA TODO ←←←
    def process_folder_files(self, rel_str: str):
        info = self.folders[rel_str]
        out_folder = self.output / rel_str
        out_folder.mkdir(parents=True, exist_ok=True)

        added = 0
        for f in info["files"]:
            if str(f["rel"]) not in self.processed_files:
                self.copy_or_link_file(f, out_folder)
                self.processed_files.add(str(f["rel"]))
                added += 1

        # MOC actualizado con los nuevos archivos
        self.create_moc_for_folder(rel_str)

        # Si ya están todos → marcamos carpeta como completada
        if len(info["files"]) == sum(1 for f in info["files"] if str(f["rel"]) in self.processed_files):
            self.processed_folders.add(rel_str)

        return added

    def process_batch(self):
        pending = self.get_pending_folders()
        if not pending:
            print("\nCOMPLETADO 100% – ¡TU VAULT ESTÁ LISTO!")
            self.create_root_index()
            return

        total = len(self.folders)
        done = len(self.processed_folders)
        batch_size = BATCH_SIZES[self.batch_idx]
        batch = pending[:batch_size]

        print(f"\nCarpetas {done:,}/{total:,} → Procesando lote de {len(batch)} carpetas", flush=True)

        for i, rel_str in enumerate(batch, 1):
            added_files = self.process_folder_files(rel_str)
            self.processed_folders.add(rel_str)  # siempre la marcamos (aunque tenga 0 archivos)

            if i % 50 == 0 or i == len(batch):
                current_done = len(self.processed_folders)
                print(f"   Carpetas {current_done:,}/{total:,}  |  +{added_files} archivos en esta carpeta", flush=True)

        self.stats["batches"] += 1
        self.save_checkpoint()
        self.create_root_index()

    def create_moc_for_folder(self, rel_str: str):
        info = self.folders.get(rel_str)
        if not info: return

        out_path = self.output / rel_str
        out_path.mkdir(parents=True, exist_ok=True)
        moc_path = out_path / f"{info['name']}.md"

        lines = [f"# {info['name']}\n", f"*Nivel {info['level']} | {info['file_count']} archivos*\n\n"]

        if info["parent"] and info["parent"] in self.folders:
            parent_name = self.folders[info["parent"]]["name"]
            lines += [f"## Nivel Superior\n- [[{parent_name}]]\n\n"]

        if info["children"]:
            lines.append("## Subcarpetas\n")
            for child in info["children"]:
                lines.append(f"- [[{self.folders[child]['name']}]]\n")
            lines.append("\n")

        processed_files = [f for f in info["files"] if str(f["rel"]) in self.processed_files]
        by_cat = defaultdict(list)
        for f in processed_files:
            by_cat[f["cat"]].append(f)

        added = False
        for cat in ["texto", "código", "imagen", "video", "audio", "datos", "archivo", "otros"]:
            if cat in by_cat:
                lines.append(f"## {cat.title()}\n")
                for f in sorted(by_cat[cat], key=lambda x: x["name"].lower()):
                    link = self.get_obsidian_link(f, out_path)
                    lines.append(f"- {link} ({f['mb']} MB)\n")
                    added = True
                lines.append("\n")

        if not added and info["children"]:
            lines.append("*Carpeta de navegación pura*\n")

        lines.append("---\n*Graph Vault 2.2 – La bestia definitiva*")
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
                proxy.write_text(f"# {name}\n*Archivo grande → {file_info['mb']} MB*\n`{file_info['path']}`", encoding="utf-8")
            self.stats["linked"] += 1
            return f"[[!_adjuntos/{file_info['stem']}]]"

    def copy_or_link_file(self, file_info, target_folder):
        if str(file_info["rel"]) in self.processed_files:
            return
        self.get_obsidian_link(file_info, target_folder)

    def sync_deletions(self):
        print("Sincronizando eliminaciones... ", end="", flush=True)
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

        print(f"{deleted} elementos eliminados")

    def create_root_index(self):
        path = self.output / "Índice Principal.md"
        lines = ["# Índice Principal - Graph Vault 2.2\n\n"]

        level1 = [k for k, v in self.folders.items() if v["level"] == 1]
        if level1:
            lines.append("## Carpetas Principales\n")
            for k in sorted(level1, key=lambda x: self.folders[x]["name"].lower()):
                lines.append(f"- [[{self.folders[k]['name']}]]\n")

        total_f = len(self.folders)
        done_f = len(self.processed_folders)
        total_files = sum(info["file_count"] for info in self.folders.values())
        done_files = len(self.processed_files)

        lines += [
            f"\n## Progreso\n",
            f"- Carpetas: **{done_f:,}/{total_f:,}** ({done_f/total_f*100:.2f}%)\n",
            f"- Archivos: **{done_files:,}/{total_files:,}** ({done_files/total_files*100:.2f}%)\n",
            f"- Archivos copiados: {self.stats['copied']:,} | Enlazados (grandes): {self.stats['linked']:,}\n",
        ]
        path.write_text("".join(lines), encoding="utf-8")

    def save_checkpoint(self):
        data = {
            "processed_folders": list(self.processed_folders),
            "processed_files": list(self.processed_files),
            "stats": self.stats,
            "batch_idx": self.batch_idx
        }
        try:
            CHECKPOINT_FILE.write_bytes(gzip.compress(json.dumps(data).encode('utf-8')))
        except: pass

    def load_checkpoint(self):
        if not CHECKPOINT_FILE.exists():
            return
        try:
            raw = gzip.decompress(CHECKPOINT_FILE.read_bytes())
            data = json.loads(raw)
            self.processed_folders = set(data.get("processed_folders", []))
            self.processed_files = set(data.get("processed_files", []))
            self.stats = data.get("stats", {"copied": 0, "linked": 0, "batches": 0})
            self.batch_idx = data.get("batch_idx", DEFAULT_BATCH_INDEX)
            print(f"Checkpoint cargado → {self.stats['batches']} lotes procesados")
        except:
            print("Checkpoint corrupto → empezando de cero")

    def dashboard(self):
        total_f = len(self.folders)
        done_f = len(self.processed_folders)
        total_files = sum(v["file_count"] for v in self.folders.values())
        done_files = len(self.processed_files)

        print("\n" + "═" * 78)
        print("          GRAPH VAULT 2.2 – LA BESTIA DEFINITIVA")
        print("═" * 78)
        print(f"   Carpetas : {done_f:,}/{total_f:,}   ({done_f/total_f*100:6.2f}%)")
        print(f"   Archivos  : {done_files:,}/{total_files:,}   ({done_files/total_files*100:6.2f}%)")
        print(f"   Lote      : {BATCH_SIZES[self.batch_idx]:,}  |  Modo: CARPETAS (el único que necesitas)")
        print()
        print("   [Enter] Procesar lote    1-9 Cambiar tamaño de lote")
        print("   r Re-escanear todo      s Solo limpiar eliminados")
        print("   q Salir y guardar")
        print("─" * 78)

    def run(self):
        print("GRAPH VAULT 2.2 LISTO – Pulsa Enter para arrasar")
        while True:
            self.dashboard()
            try:
                cmd = input("→ ").strip().lower()
                if cmd == "":
                    self.process_batch()
                elif cmd in "123456789":
                    idx = int(cmd) - 1
                    if 0 <= idx < len(BATCH_SIZES):
                        self.batch_idx = idx
                        print(f"Lote → {BATCH_SIZES[idx]:,}")
                elif cmd == "r":
                    print("Re-escaneando todo...")
                    self.processed_folders.clear()
                    self.processed_files.clear()
                    self.scan()
                    self.sync_deletions()
                elif cmd == "s":
                    self.sync_deletions()
                elif cmd == "q":
                    self.save_checkpoint()
                    print("¡Vault guardado! Nos vemos, crack")
                    break
            except KeyboardInterrupt:
                print("\nGuardando checkpoint y saliendo...")
                self.save_checkpoint()
                break

def main():
    if not INPUT_FOLDER.exists():
        print("ERROR: Crea la carpeta 'input' al lado del script y mete ahí tu vault")
        print(f"   Ruta: {SCRIPT_DIR}")
        input("Enter para salir...")
        return
    with WindowsLock(LOCK_FILE):
        GraphVaultPro().run()

if __name__ == "__main__":
    main()