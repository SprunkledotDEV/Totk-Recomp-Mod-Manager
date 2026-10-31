"""Behavioral tests with synthetic data; no game assets required."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import zipfile
from compression import zstd

from manager_core import Library, unpack_zip, patch_folder
from mod_overlay import write_table


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.game = Path(self.temp.name) / 'game'
        (self.game / 'romfs').mkdir(parents=True)
        table = zstd.compress(write_table({1: 20}, {}))
        data = b'base' + table
        (self.game / 'romfs/romfs.bin').write_bytes(data)
        (self.game / 'romfs/index.json').write_text(json.dumps({'status': 'pass', 'romfs_size': len(data), 'files': [
            {'path': 'Model/test', 'offset': 0, 'size': 4},
            {'path': 'System/Resource/ResourceSizeTable.Product.121.rsizetable.zs', 'offset': 4, 'size': len(table)}]}))
        (self.game / 'romfs-index.bin').write_bytes(b'index')
        (self.game / 'totk.ini').write_text('[files]\n')
        (self.game / 'romfs-patches').mkdir()
        (self.game / 'romfs-patches/manifest.tsv').write_text('# empty synthetic base\n')
        self.lib = Library(self.game)
        for name, content in [('A', b'first'), ('B', b'second')]:
            folder = self.lib.mods / name / 'romfs/Model'
            folder.mkdir(parents=True)
            (folder / 'test').write_bytes(content)
        self.lib.refresh()
        for row in self.lib.rows:
            row['enabled'] = True
        self.lib.save()

    def tearDown(self):
        self.temp.cleanup()

    def test_priority_disable_remove_cache_and_no_mods(self):
        a, report = self.lib.merge()
        self.assertEqual((a / 'romfs-patches/Model/test').read_bytes(), b'second')
        self.assertEqual(report['conflicts'][0]['winner'], 'B')
        self.assertEqual(self.lib.merge()[0], a)
        self.lib.rows.reverse()
        self.lib.save()
        self.assertEqual(Library(self.game).rows[0]['name'], 'B')
        b, _ = self.lib.merge()
        self.assertEqual((b / 'romfs-patches/Model/test').read_bytes(), b'first')
        self.lib.rows[1]['enabled'] = False
        c, _ = self.lib.merge()
        self.assertEqual((c / 'romfs-patches/Model/test').read_bytes(), b'second')
        self.lib.rows[0]['enabled'] = False
        d, _ = self.lib.merge()
        self.assertFalse((d / 'romfs-patches/Model/test').exists())
        self.assertEqual((a / 'romfs-patches/Model/test').read_bytes(), b'second', 'old launch output remains immutable')

    def test_failed_merge_keeps_previous_output(self):
        build, _ = self.lib.merge()
        previous = (self.lib.output / 'active.json').read_bytes()
        (self.lib.mods / 'B/exefs').mkdir()
        with self.assertRaisesRegex(ValueError, 'exefs'):
            self.lib.merge()
        self.assertEqual((self.lib.output / 'active.json').read_bytes(), previous)
        self.assertTrue(build.exists())

    def test_new_files_zip_and_traversal(self):
        path = Path(self.temp.name) / 'mod.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('Wrapper/romfs/Model/new', b'new')
        self.lib.import_mod(path)
        self.lib.rows[-1]['enabled'] = True
        build, _ = self.lib.merge()
        line = next(l for l in (build / 'romfs-patches/manifest.tsv').read_text().splitlines() if l.startswith('Model/new\t'))
        self.assertTrue(line.endswith('\t-'))
        bad = Path(self.temp.name) / 'bad.zip'
        with zipfile.ZipFile(bad, 'w') as archive:
            archive.writestr('../escape.txt', b'bad')
        with self.assertRaises(ValueError):
            unpack_zip(bad, Path(self.temp.name) / 'extract')

    def test_mod_content_change_invalidates_cache(self):
        old, _ = self.lib.merge()
        (self.lib.mods / 'B/romfs/Model/test').write_bytes(b'updated')
        new, _ = self.lib.merge()
        self.assertNotEqual(old, new)
        self.assertEqual((new / 'romfs-patches/Model/test').read_bytes(), b'updated')

    def test_game_settings_select_builtin_patch_variant(self):
        xbox = self.game / 'romfs-patches-xbox'
        xbox.mkdir()
        (xbox / 'manifest.tsv').write_text('# test')
        (self.game / 'totk.ini').write_text('pad_layout = xbox_prompts\n')
        self.assertEqual(patch_folder(self.game), xbox)
        wide = self.game / 'romfs-patches-3440x1440'
        wide.mkdir()
        (wide / 'manifest.tsv').write_text('# test')
        (self.game / 'totk.ini').write_text('pad_layout = xbox_prompts\noutput_res = 3440x1440\n')
        self.assertEqual(patch_folder(self.game), wide)

    def test_output_cleanup_is_scoped(self):
        with self.assertRaises(ValueError):
            self.lib.remove_build(self.game)
        self.assertTrue((self.game / 'romfs/romfs.bin').is_file())

    def test_ui_toggle_reorder_and_persistence(self):
        from mod_manager import Manager
        ui = Manager(self.game)
        ui.withdraw()
        try:
            ui.update_idletasks()
            ui.tree.selection_set('A')
            ui.toggle()
            self.assertFalse(ui.library.rows[0]['enabled'])
            ui.move(1)
            self.assertEqual(ui.library.rows[1]['name'], 'A')
            self.assertEqual(Library(self.game).rows[1]['name'], 'A')
            self.assertEqual(len(ui.tree.get_children()), 2)
        finally:
            ui.close()

    def test_launch_controls_remain_visible_at_small_sizes_and_high_dpi(self):
        from unittest.mock import patch
        from mod_manager import Manager
        original_style = Manager.setup_style
        for scaling in (1.3333, 2.0, 2.6667):
            def scaled_style(ui):
                ui.tk.call('tk', 'scaling', scaling)
                original_style(ui)
            with patch.object(Manager, 'setup_style', scaled_style):
                ui = Manager(self.game)
            try:
                for geometry in ('1000x740', '840x640'):
                    ui.geometry(geometry)
                    ui.withdraw()
                    ui.update_idletasks()
                    ui.deiconify()
                    ui.update()
                    for button in (ui.merge_button, ui.launch_button):
                        x = button.winfo_rootx() - ui.winfo_rootx()
                        y = button.winfo_rooty() - ui.winfo_rooty()
                        with self.subTest(scaling=scaling, geometry=geometry, button=button['text']):
                            self.assertTrue(button.winfo_ismapped())
                            self.assertGreaterEqual(x, 0)
                            self.assertGreaterEqual(y, 0)
                            self.assertLessEqual(x + button.winfo_width(), ui.winfo_width())
                            self.assertLessEqual(y + button.winfo_height(), ui.winfo_height())
                            self.assertGreaterEqual(button.winfo_height(), button.winfo_reqheight())
            finally:
                ui.close()


if __name__ == '__main__':
    unittest.main()
