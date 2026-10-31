"""Local mod library, ordered composition, and immutable launch builds."""
from pathlib import Path
from compression import zstd
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile

from mod_overlay import read_table, write_table, merge_table, read_original, valid_path

TABLE = re.compile(r'System/Resource/ResourceSizeTable\.Product\.\d+(?:\.Nin_NX_NVN)?\.rsizetable\.zs$')
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)


def files_under(root):
    root = root.resolve()
    result = {}
    for file in sorted(root.rglob('*')):
        if file.is_symlink() or not file.resolve().is_relative_to(root):
            raise ValueError(f'Linked paths are not supported: {file}')
        if file.is_file():
            name = file.relative_to(root).as_posix()
            if not valid_path(name):
                raise ValueError(f'Invalid mod path: {name}')
            result[name] = file
    return result


def find_content(path):
    if path.is_file() and path.suffix.lower() == '.tkcl':
        return 'TKCL', path
    if path.is_file() and path.suffix.lower() == '.zip':
        return 'ZIP', path
    if path.is_dir():
        if path.name.lower() == 'romfs':
            return 'RomFS', path
        roots = [p for p in path.rglob('romfs') if p.is_dir()]
        if len(roots) == 1:
            return 'RomFS', roots[0]
        packages = list(path.rglob('*.tkcl'))
        if len(packages) == 1 and not roots:
            return 'TKCL', packages[0]
    raise ValueError('Expected one romfs folder or one .tkcl package. Unpack other archives first.')


def unpack_zip(path, dest):
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            name = member.filename.rstrip('/')
            if not valid_path(name) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f'Unsafe archive path: {member.filename}')
            target = dest / name
            if not target.resolve().is_relative_to(dest.resolve()):
                raise ValueError('Archive path escapes output')
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
    return find_content(dest)


def reject_code(root):
    for name in ('exefs', 'cheats', 'romfslite'):
        if (root.parent / name).exists():
            raise ValueError(f'{name} is not supported by the recompiled game. Use a RomFS-only mod.')
    if not files_under(root):
        raise ValueError('The mod has no RomFS files.')


def digest_file(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def patch_folder(game):
    config = {}
    for line in (game / 'totk.ini').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith(('#', ';')):
            k, v = line.split('=', 1)
            config[k.strip().lower()] = v.strip().strip('"')
    resolution = os.environ.get('TOTK_OUTPUT_RES', config.get('output_res', '1920x1080'))
    match = re.fullmatch(r'(\d+)x(\d+)', resolution)
    if match:
        w, h = map(int, match.groups())
        if 1280 <= w <= 7680 and 720 <= h <= 4320:
            w, h = w & ~1, h & ~1
            wide = game / f'romfs-patches-{w}x{h}'
            if not .99 <= (w / h) / (16 / 9) <= 1.01 and (wide / 'manifest.tsv').exists():
                return wide
    layout = os.environ.get('TOTK_PAD_LAYOUT', config.get('pad_layout', 'auto'))
    xbox = game / 'romfs-patches-xbox'
    if layout.lower() == 'xbox_prompts' and (xbox / 'manifest.tsv').exists():
        return xbox
    return game / 'romfs-patches'


class Library:
    def __init__(self, game, app=None):
        self.game = Path(game).resolve()
        self.app = Path(app or Path(__file__).parent).resolve()
        storage = self.app.parent if (self.app.parent / 'portable.json').exists() else self.game
        self.mods = storage / 'mods'
        self.output = storage / 'merged-mods'
        self.state_path = self.mods / 'load-order.json'
        self.mods.mkdir(exist_ok=True)
        self.output.mkdir(exist_ok=True)
        self.rows = []
        self.refresh()

    def refresh(self):
        saved = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {'mods': []}
        present = {p.name: p for p in self.mods.iterdir() if p.is_dir() or p.suffix.lower() in ('.tkcl', '.zip')}
        order = [row for row in saved['mods'] if row['name'] in present]
        known = {row['name'] for row in order}
        order += [{'name': name, 'enabled': False} for name in sorted(present, key=str.casefold) if name not in known]
        self.rows = []
        for row in order:
            row = {'name': row['name'], 'enabled': bool(row.get('enabled', False)), 'options': row.get('options', {})}
            try:
                kind, path = find_content(present[row['name']])
                if kind == 'RomFS':
                    reject_code(path)
                row.update(kind=kind, status='Ready')
            except ValueError as e:
                row.update(kind='Unsupported', status=str(e))
            self.rows.append(row)
        return self.rows

    def save(self):
        atomic_json(self.state_path, {'version': 1, 'mods': [
            {'name': row['name'], 'enabled': row['enabled'], 'options': row.get('options', {})} for row in self.rows]})

    def metadata(self, name):
        kind, source = find_content(self.mods / name)
        if kind != 'TKCL':
            return None
        cache = self.app / 'metadata'
        cache.mkdir(exist_ok=True)
        target = cache / (digest_file(source) + '.json')
        if not target.exists():
            with tempfile.TemporaryDirectory(dir=cache) as work:
                proc = subprocess.run([str(self.app / 'backend/RecompMods.Backend.exe'), '--inspect',
                    str(source), str(target), work, '-'], capture_output=True, encoding='utf-8', errors='replace',
                    creationflags=CREATE_NO_WINDOW)
                if proc.returncode:
                    raise ValueError(proc.stderr[-4000:])
        return json.loads(target.read_text(encoding='utf-8'))

    def version_warnings(self):
        install = self.game / 'totk-install.json'
        version = json.loads(install.read_text()).get('version', '') if install.exists() else ''
        warnings = []
        for row in self.rows:
            if not row['enabled']:
                continue
            info = self.metadata(row['name'])
            built = str(info.get('gameVersion', '')) if info else ''
            if built and built != version.replace('.', ''):
                warnings.append(f"{row['name']}: package built against {built}; installed game is {version or 'unknown'}. Compatibility is unverified.")
            elif not info:
                warnings.append(f"{row['name']}: no machine-readable game-version metadata. Compatibility is unverified.")
        return warnings

    def import_mod(self, path):
        source = Path(path).resolve(strict=True)
        find_content(source)
        dest = self.mods / source.name
        if source == dest:
            return
        if dest.exists():
            raise ValueError(f'A mod named {source.name} already exists.')
        if self.mods.is_relative_to(source):
            raise ValueError('Choose a mod folder, not the game or its parent.')
        if source.is_dir():
            files_under(source)
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)
        self.refresh()
        self.save()

    def signature(self, selected, patches):
        h = hashlib.sha256(b'RecompMods-v1')
        h.update(json.dumps([{'name': r['name'], 'options': r.get('options', {})} for r in self.rows if r['enabled']], sort_keys=True).encode())
        for file in (self.game / 'romfs-index.bin', self.game / 'totk-install.json'):
            if file.exists():
                h.update(file.read_bytes())
        image = (self.game / 'romfs/romfs.bin').stat()
        h.update(f'{image.st_size}:{image.st_mtime_ns}'.encode())
        for name in selected:
            h.update(name.encode())
            path = self.mods / name
            for rel, f in (files_under(path) if path.is_dir() else {name: path}).items():
                h.update(rel.encode())
                h.update(bytes.fromhex(digest_file(f)))
        h.update(patches.name.encode())
        for rel, f in files_under(patches).items():
            h.update(rel.encode())
            h.update(bytes.fromhex(digest_file(f)))
        for file in (self.app / 'manager_core.py', self.app / 'mod_overlay.py', self.app / 'backend/RecompMods.Backend.dll', self.app / 'backend/TkSharp.Merging.dll'):
            if file.exists():
                h.update(bytes.fromhex(digest_file(file)))
        return h.hexdigest()

    def merge(self, progress=lambda text: None):
        selected = [row['name'] for row in self.rows if row['enabled']]
        for name in selected:
            kind, source = find_content(self.mods / name)
            if kind == 'RomFS':
                reject_code(source)
        patches = patch_folder(self.game)
        progress('Checking selected mods and load order…')
        signature = self.signature(selected, patches)
        pointer = self.output / 'active.json'
        if pointer.exists():
            active = json.loads(pointer.read_text())
            build = self.output / active['build']
            if active['signature'] == signature and (build / patches.name / 'manifest.tsv').exists():
                progress('Merged files are up to date.')
                return build, json.loads((build / 'report.json').read_text())
        build = self.output / ('build-' + uuid.uuid4().hex[:12])
        build.mkdir()
        (build / '.recomp-mod-build').write_text('1')
        overlay = build / patches.name
        overlay.mkdir()
        report = {'mods': selected, 'patches': patches.name, 'conflicts': [], 'packages': [], 'tables': [], 'files': []}
        try:
            index = json.loads((self.game / 'romfs/index.json').read_text())
            if index['status'] != 'pass' or (self.game / 'romfs/romfs.bin').stat().st_size != index['romfs_size']:
                raise ValueError('The base game extraction is incomplete or has changed.')
            entries = {e['path']: e for e in index['files']}
            table_names = [p for p in entries if TABLE.fullmatch(p)]
            if len(table_names) != 1:
                raise ValueError('Cannot identify the installed game resource-size table.')
            table_name = table_names[0]
            owners = {}
            with (self.game / 'romfs/romfs.bin').open('rb') as image:
                sizes = read_table(zstd.decompress(read_original(image, entries[table_name])))
                # Only manifest-listed built-in assets belong in the runtime overlay.
                for line in (patches / 'manifest.tsv').read_text().splitlines():
                    if not line or line.startswith('#'):
                        continue
                    name, size, digest, original = line.split('\t')
                    if not valid_path(name):
                        raise ValueError('Invalid built-in patch path')
                    source = patches / name
                    if source.stat().st_size != int(size) or digest_file(source) != digest:
                        raise ValueError(f'Built-in patch is damaged: {name}')
                    dest = overlay / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    owners[name] = 'Built-in game patches'
                table_changed = False
                for number, name in enumerate(selected, 1):
                    progress(f'Merging {number}/{len(selected)} · {name}')
                    kind, source = find_content(self.mods / name)
                    with tempfile.TemporaryDirectory(prefix='work-', dir=build) as temp:
                        work = Path(temp)
                        if kind == 'ZIP':
                            kind, source = unpack_zip(source, work / 'unpacked')
                        semantic = kind == 'TKCL'
                        if semantic:
                            # Expose previous allocation requirements to the package merger.
                            table_dest = overlay / table_name
                            table_dest.parent.mkdir(parents=True, exist_ok=True)
                            table_dest.write_bytes(zstd.compress(write_table(*sizes), level=6))
                            output = work / 'package-output'
                            options_file = work / 'options.json'
                            options_file.write_text(json.dumps(next(r.get('options', {}) for r in self.rows if r['name'] == name)))
                            proc = subprocess.run([str(self.app / 'backend/RecompMods.Backend.exe'),
                                str(self.game), str(source), str(output), str(work / 'package'), str(overlay), str(options_file)],
                                capture_output=True, encoding='utf-8', errors='replace', creationflags=CREATE_NO_WINDOW)
                            if proc.returncode:
                                raise ValueError(f'{name}: TKMM merge failed.\n{proc.stderr[-6000:]}')
                            report['packages'].append(json.loads((output / 'package-info.json').read_text()))
                            source = output / 'romfs'
                        reject_code(source)
                        for rel, file in files_under(source).items():
                            if TABLE.fullmatch(rel):
                                changes = merge_table(sizes, read_table(zstd.decompress(file.read_bytes())))
                                table_changed = True
                                report['tables'].append({'mod': name, 'path': rel, 'changed_entries': changes})
                                continue
                            if rel == 'manifest.tsv':
                                raise ValueError('manifest.tsv is reserved by the runtime')
                            dest = overlay / rel
                            if rel in owners and digest_file(file) != digest_file(dest):
                                report['conflicts'].append({'path': rel, 'previous': owners[rel], 'winner': name,
                                    'action': 'TKMM changes applied to previous content' if semantic else 'Later file replaces earlier file'})
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(file, dest)
                            owners[rel] = name
                if table_changed:
                    dest = overlay / table_name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zstd.compress(write_table(*sizes), level=9))
                progress('Verifying merged files…')
                lines = ['# path\tsize\tsha256\toriginal_sha256']
                for rel, path in files_under(overlay).items():
                    original = hashlib.sha256(read_original(image, entries[rel])).hexdigest() if rel in entries else '-'
                    size, sha = path.stat().st_size, digest_file(path)
                    lines.append(f'{rel}\t{size}\t{sha}\t{original}')
                    report['files'].append({'path': rel, 'size': size, 'sha256': sha, 'source': owners.get(rel, 'Merged resource sizes')})
                (overlay / 'manifest.tsv').write_text('\n'.join(lines) + '\n', encoding='utf-8')
            # Runtime selects patches beside this byte-identical index; original files remain untouched.
            shutil.copy2(self.game / 'romfs-index.bin', build / 'romfs-index.bin')
            atomic_json(build / 'report.json', report)
            atomic_json(pointer, {'build': build.name, 'signature': signature, 'created': time.time()})
            progress(f"Ready · {len(selected)} mods · {len(report['conflicts'])} overlaps resolved")
            return build, report
        except BaseException:
            self.remove_build(build)
            raise

    def remove_build(self, path):
        path = path.resolve()
        if path.parent != self.output.resolve() or not path.name.startswith('build-') or not (path / '.recomp-mod-build').is_file():
            raise ValueError('Refusing to remove an unrecognized build folder')
        shutil.rmtree(path)

    def launch_environment(self, build):
        env = os.environ.copy()
        env['TOTK_ROMFS_INDEX'] = str(build / 'romfs-index.bin')
        env['TOTK_ROMFS_MODS'] = '0'
        env.pop('TOTK_ROMFS_PATCHES', None)
        env['TOTK_ROMFS'] = str(self.game / 'romfs')
        return env

    def launch(self, build, extra_args=()):
        return subprocess.Popen([str(self.game / 'totk.exe'), *extra_args], cwd=self.game,
                                env=self.launch_environment(build))
