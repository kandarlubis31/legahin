#!/usr/bin/env python3
"""
AI Storage Cleaner Agent - CLI Tool
Scans, analyzes, and helps clean your storage intelligently.
"""

import os
import sys
import hashlib
import shutil
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
import argparse

try:
    from openai import OpenAI
except ImportError:
    print("❌ Install dependencies: pip install openai")
    sys.exit(1)

# ── OpenRouter Config ─────────────────────────────────────────────────────────

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL   = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_BASE    = "https://openrouter.ai/api/v1"

def get_client() -> OpenAI:
    if not OPENROUTER_API_KEY:
        print("❌ Set environment variable: export OPENROUTER_API_KEY='sk-or-...'")
        sys.exit(1)
    return OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE,
        default_headers={
            "HTTP-Referer": "https://github.com/storage-cleaner",
            "X-Title": "AI Storage Cleaner",
        }
    )

# ── Config ────────────────────────────────────────────────────────────────────

LARGE_FILE_MB = 50          # files > this are "large"
OLD_FILE_DAYS = 180         # files not accessed in N days
MIN_FREE_PERCENT = 20       # warn if free space < this %

SKIP_DIRS = {
    '.git', 'node_modules', '__pycache__', '.venv', 'venv',
    'env', '.env', 'dist', 'build', '.cache', 'Library',
    'System', 'Windows', 'Program Files', 'proc', 'sys', 'dev'
}

SKIP_EXTENSIONS = {'.sys', '.dll', '.so', '.dylib'}

# ── Helpers ───────────────────────────────────────────────────────────────────

def human_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

def file_hash(path: Path, chunk=65536) -> Optional[str]:
    try:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            while chunk_data := f.read(chunk):
                h.update(chunk_data)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None

def disk_usage(path: str):
    try:
        usage = shutil.disk_usage(path)
        return {
            'total': usage.total,
            'used': usage.used,
            'free': usage.free,
            'percent_used': (usage.used / usage.total) * 100
        }
    except Exception:
        return None

# ── Scanner ───────────────────────────────────────────────────────────────────

def scan_directory(root: str, max_files: int = 10000) -> dict:
    root_path = Path(root).expanduser().resolve()
    print(f"\n🔍 Scanning: {root_path}")
    print("   (This may take a moment...)\n")

    files = []
    skipped = 0
    count = 0

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Skip unwanted dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith('.')
        ]

        for fname in filenames:
            if count >= max_files:
                break
            fpath = Path(dirpath) / fname
            ext = fpath.suffix.lower()
            if ext in SKIP_EXTENSIONS:
                skipped += 1
                continue
            try:
                stat = fpath.stat()
                files.append({
                    'path': str(fpath),
                    'name': fname,
                    'ext': ext or '(no ext)',
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'atime': stat.st_atime,
                })
                count += 1
            except (PermissionError, OSError):
                skipped += 1

    print(f"   ✅ Found {len(files):,} files  |  Skipped {skipped:,}")
    return {'root': str(root_path), 'files': files}

# ── Analysis ──────────────────────────────────────────────────────────────────

def find_duplicates(files: list) -> dict[str, list]:
    """Group files by hash to find exact duplicates."""
    print("\n🔎 Finding duplicates...")
    hash_map = defaultdict(list)
    for f in files:
        if f['size'] == 0:
            continue
        h = file_hash(Path(f['path']))
        if h:
            hash_map[h].append(f)
    dupes = {h: fs for h, fs in hash_map.items() if len(fs) > 1}
    total_waste = sum(
        sum(f['size'] for f in group[1:])  # keep 1 copy
        for group in dupes.values()
    )
    print(f"   Found {len(dupes)} duplicate groups  |  Wasted: {human_size(total_waste)}")
    return dupes, total_waste

def find_large_files(files: list, threshold_mb=LARGE_FILE_MB) -> list:
    threshold = threshold_mb * 1024 * 1024
    large = sorted([f for f in files if f['size'] >= threshold],
                   key=lambda x: x['size'], reverse=True)
    print(f"\n📦 Large files (>{threshold_mb}MB): {len(large)}")
    return large

def find_old_files(files: list, days=OLD_FILE_DAYS) -> list:
    cutoff = time.time() - (days * 86400)
    old = [f for f in files if f.get('atime', f['mtime']) < cutoff]
    old.sort(key=lambda x: x.get('atime', x['mtime']))
    print(f"⏰ Old files (not accessed {days}d+): {len(old)}")
    return old

def extension_summary(files: list) -> dict:
    ext_data = defaultdict(lambda: {'count': 0, 'size': 0})
    for f in files:
        ext_data[f['ext']]['count'] += 1
        ext_data[f['ext']]['size'] += f['size']
    return dict(sorted(ext_data.items(), key=lambda x: x[1]['size'], reverse=True))

# ── AI Analysis ───────────────────────────────────────────────────────────────

def ai_analyze(scan_data: dict, dupes: dict, large: list, old: list, disk: dict) -> str:
    client = get_client()

    total_size = sum(f['size'] for f in scan_data['files'])
    ext_summary = extension_summary(scan_data['files'])

    top_exts = [
        f"  {ext}: {data['count']} files, {human_size(data['size'])}"
        for ext, data in list(ext_summary.items())[:10]
    ]
    top_large = [
        f"  {human_size(f['size'])} - {f['path']}"
        for f in large[:5]
    ]
    dupe_count = sum(len(g) - 1 for g in dupes.values())
    dupe_waste = sum(sum(f['size'] for f in g[1:]) for g in dupes.values())

    # Duplicate detail
    dupe_detail = []
    for h, group in list(dupes.items())[:5]:
        dupe_detail.append(f"  [{human_size(group[0]['size'])} each]")
        for f in group:
            dupe_detail.append(f"    - {f['path']}")

    # All files sorted by size
    all_files_lines = [
        f"  {human_size(f['size']):>10}  {f['name']}  ({f['path']})"
        for f in sorted(scan_data['files'], key=lambda x: x['size'], reverse=True)[:100]
    ]

    summary = (
        f"Storage Scan Report\n"
        f"===================\n"
        f"Root: {scan_data['root']}\n"
        f"Total files: {len(scan_data['files']):,}\n"
        f"Total size: {human_size(total_size)}\n"
        f"Disk used: {human_size(disk['used'])} / {human_size(disk['total'])} ({disk['percent_used']:.1f}%)\n"
        f"Disk free: {human_size(disk['free'])}\n\n"
        f"Duplicates: {dupe_count} extra copies wasting {human_size(dupe_waste)}\n"
        + ('\n'.join(dupe_detail) if dupe_detail else '  (tidak ada duplikat)') + '\n\n'
        + f"Large files (>{LARGE_FILE_MB}MB): {len(large)}\n"
        + ('\n'.join(top_large) if top_large else '  (tidak ada)') + '\n\n'
        + f"Old files (>{OLD_FILE_DAYS}d not accessed): {len(old)}\n\n"
        + f"File types by size:\n" + '\n'.join(top_exts) + '\n\n'
        + f"All files (sorted by size):\n" + '\n'.join(all_files_lines)
    )

    print(f"\n🤖 AI sedang menganalisis... (model: {OPENROUTER_MODEL})\n")
    print("─" * 60)

    full_response = ""
    stream = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        max_tokens=1000,
        stream=True,
        messages=[
            {
                "role": "system",
                "content": (
                    "Kamu adalah AI storage cleaner expert. "
                    "Kamu diberikan data storage NYATA beserta daftar file lengkap. "
                    "Analisis data tersebut dan berikan insight spesifik berdasarkan nama file dan ukuran aktual. "
                    "Sebutkan nama file konkret yang bisa dihapus, bukan saran generik. "
                    "Format: pakai emoji, ringkas, actionable. Bahasa Indonesia."
                )
            },
            {
                "role": "user",
                "content": f"Analisis storage ini dan berikan rekomendasi pembersihan:\n{summary}"
            }
        ]
    )
    for chunk in stream:
        text = chunk.choices[0].delta.content or ""
        print(text, end="", flush=True)
        full_response += text

    print("\n" + "─" * 60)
    return full_response

# ── Interactive Chat ──────────────────────────────────────────────────────────

def chat_mode(scan_data: dict, dupes: dict, large: list, old: list):
    client = get_client()
    history = []

    # Build rich context including full file list
    all_files = [
        {
            'name': f['name'],
            'path': f['path'],
            'size': f['size'],
            'size_human': human_size(f['size']),
            'ext': f['ext'],
            'mtime': datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d'),
        }
        for f in sorted(scan_data['files'], key=lambda x: x['size'], reverse=True)[:200]
    ]
    dupe_files = [
        {'copies': [ff['path'] for ff in group], 'size_each': human_size(group[0]['size'])}
        for group in list(dupes.values())[:10]
    ]
    context = json.dumps({
        'root': scan_data['root'],
        'total_files': len(scan_data['files']),
        'total_size_human': human_size(sum(f['size'] for f in scan_data['files'])),
        'duplicate_groups': len(dupes),
        'large_files_count': len(large),
        'old_files_count': len(old),
        'duplicates': dupe_files,
        'large_files': [{'path': f['path'], 'size': human_size(f['size'])} for f in large[:20]],
        'old_files': [{'path': f['path'], 'last_access': datetime.fromtimestamp(f.get('atime', f['mtime'])).strftime('%Y-%m-%d')} for f in old[:20]],
        'all_files': all_files,
    }, ensure_ascii=False)

    system_msg = {
        "role": "system",
        "content": (
            "Kamu adalah AI storage cleaner expert. "
            "Kamu memiliki akses ke data storage NYATA user, termasuk daftar file lengkap. "
            "Saat user tanya nama file, sebutkan nama file yang ada di context. "
            "Berikan analisis spesifik, bukan saran generik. Bahasa Indonesia.\n\n"
            f"DATA STORAGE:\n{context}"
        )
    }

    print("\n💬 Chat Mode — Tanya apa saja tentang storage kamu!")
    print("   Ketik 'quit' atau 'exit' untuk keluar.\n")

    while True:
        try:
            user_input = input("Kamu: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input:
            continue
        if user_input.lower() in ('quit', 'exit', 'keluar'):
            print("👋 Sampai jumpa!")
            break

        history.append({"role": "user", "content": user_input})

        print("\nAI: ", end="", flush=True)
        stream = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            max_tokens=500,
            stream=True,
            messages=[system_msg] + history
        )
        response = ""
        for chunk in stream:
            text = chunk.choices[0].delta.content or ""
            print(text, end="", flush=True)
            response += text
        print("\n")

        history.append({"role": "assistant", "content": response})

        # Keep history compact
        if len(history) > 10:
            history = history[-10:]

# ── Actions ───────────────────────────────────────────────────────────────────

def action_menu(dupes: dict, large: list, old: list):
    while True:
        print("\n📋 Actions:")
        print("  1. Lihat detail duplikat")
        print("  2. Lihat detail file besar")
        print("  3. Lihat detail file lama")
        print("  4. Hapus duplikat (keep newest)")
        print("  5. Chat dengan AI")
        print("  6. Export report (JSON)")
        print("  0. Keluar")

        choice = input("\nPilih: ").strip()

        if choice == '1':
            show_duplicates(dupes)
        elif choice == '2':
            show_large(large)
        elif choice == '3':
            show_old(old)
        elif choice == '4':
            delete_duplicates(dupes)
        elif choice == '5':
            return 'chat'
        elif choice == '6':
            return 'export'
        elif choice == '0':
            return 'exit'

def show_duplicates(dupes: dict, limit=20):
    print(f"\n🔁 Duplicate Groups (showing max {limit}):\n")
    for i, (h, group) in enumerate(list(dupes.items())[:limit]):
        print(f"  Group {i+1} — {human_size(group[0]['size'])} each:")
        for f in group:
            mtime = datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d')
            print(f"    [{mtime}] {f['path']}")

def show_large(large: list, limit=20):
    print(f"\n📦 Large Files (top {min(limit, len(large))}):\n")
    for f in large[:limit]:
        mtime = datetime.fromtimestamp(f['mtime']).strftime('%Y-%m-%d')
        print(f"  {human_size(f['size']):>10}  [{mtime}]  {f['path']}")

def show_old(old: list, limit=20):
    print(f"\n⏰ Old Files (top {min(limit, len(old))}):\n")
    for f in old[:limit]:
        atime = datetime.fromtimestamp(f.get('atime', f['mtime'])).strftime('%Y-%m-%d')
        print(f"  {human_size(f['size']):>10}  [last: {atime}]  {f['path']}")

def delete_duplicates(dupes: dict):
    if not dupes:
        print("✅ Tidak ada duplikat.")
        return

    total_waste = sum(sum(f['size'] for f in g[1:]) for g in dupes.values())
    count = sum(len(g) - 1 for g in dupes.values())

    print(f"\n⚠️  Akan menghapus {count} file duplikat ({human_size(total_waste)})")
    print("   Strategy: keep file TERBARU, hapus sisanya.")
    confirm = input("   Lanjut? (ketik 'yes' untuk konfirmasi): ").strip()

    if confirm.lower() != 'yes':
        print("   ❌ Dibatalkan.")
        return

    deleted = 0
    freed = 0
    errors = 0

    for group in dupes.values():
        # Sort by mtime descending, keep first (newest)
        sorted_group = sorted(group, key=lambda x: x['mtime'], reverse=True)
        for f in sorted_group[1:]:
            try:
                os.remove(f['path'])
                freed += f['size']
                deleted += 1
            except Exception as e:
                print(f"   ⚠️ Gagal hapus {f['path']}: {e}")
                errors += 1

    print(f"\n   ✅ Dihapus: {deleted} file  |  Freed: {human_size(freed)}  |  Errors: {errors}")

def export_report(scan_data, dupes, large, old, disk):
    report = {
        'generated_at': datetime.now().isoformat(),
        'root': scan_data['root'],
        'disk': {k: human_size(v) if isinstance(v, int) else v for k, v in disk.items()},
        'total_files': len(scan_data['files']),
        'total_size': human_size(sum(f['size'] for f in scan_data['files'])),
        'duplicates': {
            'groups': len(dupes),
            'extra_copies': sum(len(g) - 1 for g in dupes.values()),
            'wasted': human_size(sum(sum(f['size'] for f in g[1:]) for g in dupes.values())),
        },
        'large_files': [{'path': f['path'], 'size': human_size(f['size'])} for f in large[:50]],
        'old_files': [{'path': f['path'], 'last_access': datetime.fromtimestamp(f.get('atime', f['mtime'])).isoformat()} for f in old[:50]],
    }

    out = Path.cwd() / 'storage_report.json'
    with open(out, 'w') as fp:
        json.dump(report, fp, indent=2, ensure_ascii=False)
    print(f"\n✅ Report disimpan: {out}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='🧹 AI Storage Cleaner Agent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Contoh:\n  python cleaner.py ~/Downloads\n  python cleaner.py /home --large 100 --old 365"
    )
    parser.add_argument('path', nargs='?', default='.', help='Direktori yang akan discan (default: .)')
    parser.add_argument('--large', type=int, default=LARGE_FILE_MB, help=f'Threshold file besar dalam MB (default: {LARGE_FILE_MB})')
    parser.add_argument('--old', type=int, default=OLD_FILE_DAYS, help=f'Threshold file lama dalam hari (default: {OLD_FILE_DAYS})')
    parser.add_argument('--max', type=int, default=10000, help='Max files di-scan (default: 10000)')
    parser.add_argument('--no-ai', action='store_true', help='Skip AI analysis')
    args = parser.parse_args()

    print("=" * 60)
    print("  🧹 AI Storage Cleaner Agent")
    print("=" * 60)

    # Disk usage
    disk = disk_usage(args.path)
    if disk:
        pct = disk['percent_used']
        icon = '🔴' if pct > 90 else '🟡' if pct > 70 else '🟢'
        print(f"\n{icon} Disk: {human_size(disk['used'])} / {human_size(disk['total'])} ({pct:.1f}% used)")
        print(f"   Free: {human_size(disk['free'])}")

    # Scan
    scan_data = scan_directory(args.path, max_files=args.max)

    if not scan_data['files']:
        print("\n⚠️  Tidak ada file ditemukan.")
        return

    # Analyze
    dupes, _ = find_duplicates(scan_data['files'])
    large = find_large_files(scan_data['files'], args.large)
    old = find_old_files(scan_data['files'], args.old)

    # AI Summary
    if not args.no_ai:
        try:
            ai_analyze(scan_data, dupes, large, old, disk or {
                'used': 0, 'total': 0, 'free': 0, 'percent_used': 0
            })
        except Exception as e:
            print(f"\n⚠️  AI analysis gagal: {e}")

    # Menu
    while True:
        result = action_menu(dupes, large, old)
        if result == 'chat':
            chat_mode(scan_data, dupes, large, old)
        elif result == 'export':
            export_report(scan_data, dupes, large, old, disk or {})
        elif result == 'exit':
            print("\n✨ Selesai. Semoga storage-mu makin lapang!\n")
            break

if __name__ == '__main__':
    main()