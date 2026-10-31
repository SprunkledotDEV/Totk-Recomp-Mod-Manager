"""Prepare unpacked RomFS mods for the existing TotK Recomp overlay loader.

Requires Python 3.14 (compression.zstd). No game executable or base data is modified.
Overlapping files must be merged externally (for example with TKMM) first.
"""
import argparse
from compression import zstd
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile


TABLE = re.compile(r'System/Resource/ResourceSizeTable\.Product\.\d+\.rsizetable\.zs$')


def read_table(data):
    """Read little-endian RESTBL; older mod tools write zero header fields."""
    if len(data) < 22 or data[:6] != b'RESTBL':
        raise ValueError('Invalid RESTBL header')
    version, width, count, named_count = struct.unpack_from('<4I', data, 6)
    if version not in (0, 1) or width > 4096:
        raise ValueError('Unsupported RESTBL version or name width')
    width = width or 160
    if len(data) != 22 + count * 8 + named_count * (width + 4):
        raise ValueError('Invalid RESTBL length')
    hashes = dict(struct.iter_unpack('<II', data[22:22 + count * 8]))
    names = {}
    for off in range(22 + count * 8, len(data), width + 4):
        raw = data[off:off + width]
        if b'\0' not in raw:
            raise ValueError('Unterminated RESTBL name')
        name = bytes(raw.split(b'\0', 1)[0])
        if not name or name in names:
            raise ValueError('Invalid or duplicate RESTBL name')
        names[name] = struct.unpack_from('<I', data, off + width)[0]
    if len(hashes) != count:
        raise ValueError('Duplicate RESTBL hash')
    return hashes, names


def write_table(hashes, names):
    width = max(160, max((len(name) + 1 for name in names), default=0))
    if width > 4096:
        raise ValueError('RESTBL name too long')
    data = bytearray(b'RESTBL' + struct.pack('<4I', 1, width, len(hashes), len(names)))
    for key, size in sorted(hashes.items()):
        data.extend(struct.pack('<II', key, size))
    for name, size in sorted(names.items()):
        data.extend(name.ljust(width, b'\0') + struct.pack('<I', size))
    return bytes(data)


def merge_table(base, mod):
    """Keep all installed entries and never decrease an allocation requirement.

    This conservative merge also retains unrelated entries in full legacy tables.
    It is not a version conversion for the mod's actors or other assets.
    """
    changed = 0
    for dest, source in zip(base, mod):
        for key, size in source.items():
            if key not in dest or size > dest[key]:
                dest[key] = size
                changed += 1
    return changed


def valid_path(name):
    return (name and not any(c in name for c in '\\:\t\r\n\0')
            and all(p not in ('', '.', '..') for p in name.split('/')))


def collect(mods):
    files, tables = {}, []
    for mod in mods:
        mod = mod.resolve(strict=True)
        root = mod if mod.name.lower() == 'romfs' else mod / 'romfs'
        container = root.parent
        for unsupported in ('exefs', 'cheats', 'romfslite'):
            if (container / unsupported).exists():
                raise ValueError(f'{container}: {unsupported} is unsupported; export full RomFS-only output')
        if not root.is_dir():
            raise ValueError(f'{mod}: expected a romfs folder')
        found = False
        for path in sorted(root.rglob('*')):
            if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
                raise ValueError(f'Mod contains a link outside its tree: {path}')
            if not path.is_file():
                continue
            found = True
            name = path.relative_to(root).as_posix()
            if not valid_path(name) or name == 'manifest.tsv':
                raise ValueError(f'Invalid mod path: {name}')
            if TABLE.fullmatch(name):
                tables.append(path)
            elif name in files:
                if path.read_bytes() != files[name].read_bytes():
                    raise ValueError(f'File conflict: {name}\nMerge these mods in TKMM first.')
            else:
                files[name] = path
        if not found:
            raise ValueError(f'Empty mod: {root}')
    return files, tables


def read_original(image, entry):
    image.seek(entry['offset'])
    data = image.read(entry['size'])
    if len(data) != entry['size']:
        raise ValueError('Truncated RomFS image')
    return data


def build(game, mods, out):
    game, out = game.resolve(strict=True), out.resolve()
    if out.exists():
        raise ValueError(f'Output already exists: {out}. Choose a new output folder.')
    files, tables = collect(mods)
    if out == game or out.is_relative_to(game / 'romfs') or any(out.is_relative_to(m.resolve()) for m in mods):
        raise ValueError('Output must be separate from game data and input mods')
    index = json.loads((game / 'romfs/index.json').read_text(encoding='utf-8'))
    image_path = game / 'romfs/romfs.bin'
    if index.get('status') != 'pass' or image_path.stat().st_size != index['romfs_size']:
        raise ValueError('Game extraction is not verified or has the wrong size')
    entries = {e['path']: e for e in index['files']}
    # Runtime refuses collisions with its built-in overlays. Check every installed variant,
    # so changing resolution or controller prompts cannot create a latent conflict.
    protected = set()
    for manifest in game.glob('romfs-patches*/manifest.tsv'):
        protected.update(line.split('\t')[0] for line in manifest.read_text().splitlines()
                         if line and not line.startswith('#'))
    table_paths = [name for name in entries if TABLE.fullmatch(name)]
    if tables and len(table_paths) != 1:
        raise ValueError('Expected exactly one resource-size table in installed game')
    targets = set(files) | (set(table_paths) if tables else set())
    if targets & protected:
        raise ValueError('Conflict with built-in runtime patches: ' + ', '.join(sorted(targets & protected)))
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.mod-overlay-', dir=out.parent))
    report = {'game': str(game), 'mods': [str(m.resolve()) for m in mods], 'files': [], 'tables': []}
    try:
        with image_path.open('rb') as image:
            generated = {}
            if tables:
                target = table_paths[0]
                base = read_table(zstd.decompress(read_original(image, entries[target])))
                for table in tables:
                    changes = merge_table(base, read_table(zstd.decompress(table.read_bytes())))
                    report['tables'].append({'source': str(table), 'target': target, 'entries_increased_or_added': changes})
                generated[target] = zstd.compress(write_table(*base), level=9)
            lines = ['# path\tsize\tsha256\toriginal_sha256']
            for name in sorted(targets):
                data = generated[name] if name in generated else files[name].read_bytes()
                original = hashlib.sha256(read_original(image, entries[name])).hexdigest() if name in entries else '-'
                digest = hashlib.sha256(data).hexdigest()
                dest = stage / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                lines.append(f'{name}\t{len(data)}\t{digest}\t{original}')
                report['files'].append({'path': name, 'size': len(data), 'sha256': digest, 'original_sha256': original})
        (stage / 'manifest.tsv').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        (stage / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        stage.rename(out)
    except BaseException:
        shutil.rmtree(stage)
        raise
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--game', type=Path, required=True)
    ap.add_argument('--mod', type=Path, action='append', required=True, help='Repeat for multiple non-conflicting mods')
    ap.add_argument('--out', type=Path, required=True, help='New overlay folder; existing folders are never replaced')
    args = ap.parse_args()
    try:
        report = build(args.game, args.mod, args.out)
    except (ValueError, OSError, KeyError, zstd.ZstdError) as error:
        ap.exit(1, f'mod_overlay: {error}\n')
    print(f"Prepared {len(report['files'])} files in {args.out.resolve()}")
    for table in report['tables']:
        print(f"Resource sizes: {table['entries_increased_or_added']} entries increased/added -> {table['target']}")
    print('Launch with TOTK_ROMFS_MODS set to this folder, or set [files] romfs_mods in totk.ini.')


if __name__ == '__main__':
    main()
