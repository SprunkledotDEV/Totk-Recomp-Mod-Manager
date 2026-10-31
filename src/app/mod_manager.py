"""Small desktop mod manager for a local TotK Recomp installation."""
from pathlib import Path
import argparse
import ctypes
import json
import os
import queue
import subprocess
import threading
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from manager_core import Library, CREATE_NO_WINDOW


class Manager(tk.Tk):
    def __init__(self, game):
        super().__init__()
        self.title('TotK Recomp · Mod Manager')
        self.geometry('1000x740')
        self.minsize(840, 640)
        self.configure(bg='#121b23')
        self.library = Library(game)
        self.events = queue.Queue()
        self.busy = False
        self.game_process = None
        self.report = None
        self.widgets = []
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.setup_style()
        self.create_ui()
        if (Path(__file__).resolve().parent.parent / 'portable.json').exists():
            menu = tk.Menu(self)
            menu.add_command(label='Change game folder…', command=self.change_game_folder)
            self.configure(menu=menu)
        self.draw_rows()
        self.poll_id = self.after(100, self.poll)

    def change_game_folder(self):
        if self.busy:
            return
        path = filedialog.askdirectory(parent=self, title='Choose the compiled game folder', initialdir=self.library.game)
        if not path:
            return
        game = Path(path)
        if not (game / 'totk.exe').is_file() or not (game / 'romfs/index.json').is_file():
            messagebox.showerror('Invalid game folder', 'This folder must contain totk.exe and romfs/index.json.', parent=self)
            return
        self.library.save()
        self.library = Library(game)
        (Path(__file__).resolve().parent.parent / 'portable.json').write_text(json.dumps({'game': str(game)}, indent=2), encoding='utf-8')
        self.report = None
        self.draw_rows()
        self.status.configure(text=f'Game folder: {game}')

    def setup_style(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#121b23', foreground='#e6edf3')
        style.configure('TFrame', background='#121b23')
        style.configure('TLabel', background='#121b23')
        style.configure('Muted.TLabel', foreground='#9eafbd')
        style.configure('Title.TLabel', font=('Segoe UI Semibold', 24))
        style.configure('TButton', padding=(13, 9), background='#263747', borderwidth=0)
        style.map('TButton', background=[('active', '#364d60'), ('disabled', '#202b34')], foreground=[('disabled', '#70818e')])
        style.configure('Accent.TButton', background='#80d7b0', foreground='#10271e', font=('Segoe UI Semibold', 11))
        style.map('Accent.TButton', background=[('active', '#a2e6c9'), ('disabled', '#334b43')])
        style.configure('Treeview', background='#1b2833', fieldbackground='#1b2833', foreground='#e6edf3',
                        rowheight=43, borderwidth=0, font=('Segoe UI', 11))
        style.configure('Treeview.Heading', background='#263747', foreground='#b7c8d5', padding=(8, 10), borderwidth=0)
        style.map('Treeview', background=[('selected', '#34544f')], foreground=[('selected', '#ffffff')])
        style.configure('Horizontal.TProgressbar', background='#80d7b0', troughcolor='#263747', borderwidth=0)

    def button(self, parent, label, command, **kwargs):
        widget = ttk.Button(parent, text=label, command=command, **kwargs)
        self.widgets.append(widget)
        return widget

    def create_ui(self):
        # Reserve the action dock before allocating space to the mod list. Packing
        # it after the list lets Tk clip it when fonts or display scaling grow.
        dock = ttk.Frame(self, padding=(26, 12, 26, 16))
        dock.pack(side='bottom', fill='x')
        dock.columnconfigure(0, weight=1)
        self.status = ttk.Label(dock, text='Ready', style='Muted.TLabel', width=1, wraplength=400)
        self.status.grid(row=0, column=0, sticky='ew', padx=(0, 16))
        self.merge_button = self.button(dock, 'Merge', lambda: self.start_merge(False))
        self.merge_button.grid(row=0, column=1, padx=(0, 8))
        self.launch_button = self.button(dock, 'Launch game', lambda: self.start_merge(True), style='Accent.TButton')
        self.launch_button.grid(row=0, column=2)
        self.progress = ttk.Progressbar(dock, mode='indeterminate')
        self.progress.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(12, 0))
        outer = ttk.Frame(self, padding=26)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(4, weight=1)
        ttk.Label(outer, text='TEARS OF THE KINGDOM  /  RECOMP', style='Muted.TLabel', font=('Segoe UI', 9)).grid(row=0, column=0, sticky='w')
        heading = ttk.Frame(outer)
        heading.grid(row=1, column=0, sticky='ew', pady=(6, 2))
        ttk.Label(heading, text='Mod Manager', style='Title.TLabel').pack(side='left')
        self.count = ttk.Label(heading, style='Muted.TLabel')
        self.count.pack(side='right', pady=12)
        ttk.Label(outer, text='Tick your mods. Set their order. Merge and play.', style='Muted.TLabel').grid(row=2, column=0, sticky='w', pady=(0, 20))

        toolbar = ttk.Frame(outer)
        toolbar.grid(row=3, column=0, sticky='ew', pady=(0, 14))
        self.button(toolbar, 'Import folder', self.import_folder).pack(side='left', padx=(0, 7))
        self.button(toolbar, 'Import file…', self.import_file).pack(side='left', padx=(0, 7))
        self.button(toolbar, 'Open mods folder', lambda: os.startfile(self.library.mods)).pack(side='left')
        self.button(toolbar, 'Refresh', self.refresh).pack(side='right')
        self.button(toolbar, 'Details / options', self.package_options).pack(side='right', padx=7)

        table_frame = ttk.Frame(outer)
        table_frame.grid(row=4, column=0, sticky='nsew')
        self.tree = ttk.Treeview(table_frame, columns=('enabled', 'order', 'name', 'format'), show='headings', selectmode='browse', height=7)
        for key, title, width, anchor in [('enabled', 'ON', 55, 'center'), ('order', '#', 48, 'center'),
                ('name', 'MOD', 570, 'w'), ('format', 'FORMAT', 120, 'w')]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=anchor, stretch=key == 'name')
        self.tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<ButtonRelease-1>', self.table_click)
        self.tree.bind('<space>', lambda event: self.toggle())
        self.tree.bind('<<TreeviewSelect>>', lambda event: self.show_details())
        self.tree.tag_configure('unsupported', foreground='#f1b2a8')

        order_bar = ttk.Frame(outer)
        order_bar.grid(row=5, column=0, sticky='ew', pady=(12, 15))
        self.button(order_bar, '↑ Move up', lambda: self.move(-1)).pack(side='left', padx=(0, 7))
        self.button(order_bar, '↓ Move down', lambda: self.move(1)).pack(side='left', padx=(0, 7))
        self.button(order_bar, 'Toggle selected', self.toggle).pack(side='left')
        ttk.Label(order_bar, text='Loads top to bottom · lower mods take priority', style='Muted.TLabel').pack(side='right')

        self.detail_title = ttk.Label(outer, text='Load order & conflicts', font=('Segoe UI Semibold', 11))
        self.detail_title.grid(row=6, column=0, sticky='w', pady=(0, 7))
        self.details = tk.Text(outer, height=4, width=1, wrap='word', bg='#1b2833', fg='#b7c8d5', relief='flat',
                               padx=12, pady=10, font=('Segoe UI', 10), insertbackground='white')
        self.details.grid(row=7, column=0, sticky='ew')
        self.set_details('Mods at the bottom win whole-file conflicts. TKCL packages apply their changes to earlier content.\n'
                         'Resource-size tables are combined automatically. Your original game files stay untouched.\n'
                         'Import unpacked mods, ZIP archives, or TKCL packages. New mods start disabled.')

    def package_options(self):
        name = self.selected()
        if not name or self.busy:
            return
        try:
            info = self.library.metadata(name)
        except Exception as error:
            messagebox.showerror('Package could not be read', str(error), parent=self)
            return
        if not info:
            messagebox.showinfo('Folder mod', 'This mod has no TKCL package metadata or options.', parent=self)
            return
        row = next(r for r in self.library.rows if r['name'] == name)
        dialog = tk.Toplevel(self)
        dialog.title(info['name'])
        dialog.geometry('720x600')
        footer = ttk.Frame(dialog, padding=12)
        footer.pack(side='bottom', fill='x')
        canvas = tk.Canvas(dialog, highlightthickness=0, background='#121b23')
        scroll = ttk.Scrollbar(dialog, command=canvas.yview)
        scroll.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        content = ttk.Frame(canvas, padding=18)
        window = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        ttk.Label(content, text=f"{info['name']}  {info['version']}\nBy {info['author']} · Package game version: {info['gameVersion']}", wraplength=650).pack(anchor='w')
        ttk.Label(content, text=info['description'], wraplength=650).pack(anchor='w', pady=12)
        controls = {}
        for group in info['groups']:
            key = str(group['index'])
            selected = row.get('options', {}).get(key, group['defaults'])
            ttk.Label(content, text=group['name'] + ' (' + group['type'] + ')', font=('Segoe UI Semibold', 11)).pack(anchor='w', pady=(12, 4))
            ttk.Label(content, text=group['description'], wraplength=650).pack(anchor='w')
            values = {}
            for option in group['options']:
                variable = tk.BooleanVar(value=option['id'] in selected)
                values[option['id']] = variable
                ttk.Checkbutton(content, text=option['name'], variable=variable).pack(anchor='w')
                if option['description']:
                    ttk.Label(content, text=option['description'], wraplength=620).pack(anchor='w', padx=20)
            controls[key] = values
        def save():
            selections = {key: [oid for oid, var in values.items() if var.get()] for key, values in controls.items()}
            for group in info['groups']:
                count = len(selections[str(group['index'])])
                if ('Single' in group['type'] and count > 1) or ('Required' in group['type'] and count == 0):
                    messagebox.showerror('Invalid selection', f"Check the selection for {group['name']} ({group['type']}).", parent=dialog)
                    return
            row['options'] = selections
            self.changed(name)
            dialog.destroy()
        ttk.Button(footer, text='Save options', command=save).pack(side='right')
        ttk.Button(footer, text='Cancel', command=dialog.destroy).pack(side='right', padx=8)
        dialog.transient(self)
        dialog.grab_set()

    def set_details(self, text):
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', text)
        self.details.configure(state='disabled')

    def selected(self):
        selection = self.tree.selection()
        return selection[0] if selection else None

    def draw_rows(self, selection=None):
        selection = selection or self.selected()
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.library.rows, 1):
            self.tree.insert('', 'end', iid=row['name'], values=(
                '☑' if row['enabled'] else '☐', i, row['name'], row['kind']),
                tags=('unsupported',) if row['kind'] == 'Unsupported' else ())
        if selection and self.tree.exists(selection):
            self.tree.selection_set(selection)
            self.tree.see(selection)
        self.count.configure(text=f"{sum(r['enabled'] for r in self.library.rows)} enabled  /  {len(self.library.rows)} installed")

    def show_details(self):
        name = self.selected()
        if not name:
            return
        row = next(r for r in self.library.rows if r['name'] == name)
        text = f"{name}\n{row['status']} · {'Enabled' if row['enabled'] else 'Disabled'}"
        if row['kind'] == 'TKCL':
            text += '\nUses TKMM merging with the package’s default options.'
        if self.report:
            conflicts = [c for c in self.report['conflicts'] if name in (c['previous'], c['winner'])]
            for c in conflicts:
                text += f"\n{c['path']}\n  {c['previous']} → {c['winner']} · {c['action']}"
            if not conflicts:
                text += '\nNo overlaps for this mod in the last merge.'
        self.set_details(text)

    def changed(self, selection):
        self.library.save()
        self.report = None
        self.status.configure(text='Selection saved. Merge or launch to apply.')
        self.draw_rows(selection)
        self.show_details()

    def table_click(self, event):
        if self.tree.identify_column(event.x) == '#1' and self.tree.identify_row(event.y):
            self.toggle()

    def toggle(self):
        name = self.selected()
        if self.busy or not name:
            return
        row = next(r for r in self.library.rows if r['name'] == name)
        if row['kind'] == 'Unsupported' and not row['enabled']:
            messagebox.showerror('Unsupported mod', row['status'], parent=self)
            return
        row['enabled'] = not row['enabled']
        self.changed(name)

    def move(self, delta):
        name = self.selected()
        if self.busy or not name:
            return
        i = next(i for i, r in enumerate(self.library.rows) if r['name'] == name)
        j = i + delta
        if 0 <= j < len(self.library.rows):
            self.library.rows[i], self.library.rows[j] = self.library.rows[j], self.library.rows[i]
            self.changed(name)

    def refresh(self):
        try:
            self.library.save()
            self.library.refresh()
            self.library.save()
            self.draw_rows()
            self.status.configure(text='Mod library refreshed.')
        except Exception as e:
            messagebox.showerror('Refresh failed', str(e), parent=self)

    def import_folder(self):
        path = filedialog.askdirectory(title='Select a mod folder containing romfs', parent=self)
        if path:
            self.import_path(path)

    def import_file(self):
        paths = filedialog.askopenfilenames(title='Import mod packages', parent=self,
            filetypes=[('Mod packages', '*.tkcl *.zip'), ('TKMM package', '*.tkcl'), ('ZIP archive', '*.zip')])
        for path in paths:
            self.import_path(path)

    def import_path(self, path):
        try:
            self.library.save()
            self.library.import_mod(path)
            self.draw_rows(Path(path).name)
            self.status.configure(text='Imported. Tick the mod to enable it.')
        except Exception as e:
            messagebox.showerror('Import failed', str(e), parent=self)

    def start_merge(self, launch):
        if self.busy:
            return
        try:
            warnings = self.library.version_warnings()
        except Exception as error:
            messagebox.showerror('Could not inspect mods', str(error), parent=self)
            return
        if warnings and not messagebox.askyesno('Mod version compatibility', '\n\n'.join(warnings) + '\n\nContinue with these mods?', parent=self):
            return
        if launch:
            result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq totk.exe', '/FO', 'CSV', '/NH'],
                                    capture_output=True, creationflags=CREATE_NO_WINDOW)
            if b'"totk.exe"' in result.stdout.lower():
                messagebox.showinfo('Game is running', 'Close the running game before launching another session.', parent=self)
                return
        self.library.save()
        self.busy = True
        for widget in self.widgets:
            widget.state(['disabled'])
        self.progress.start(15)
        def work():
            try:
                build, report = self.library.merge(lambda text: self.events.put(('status', text)))
                self.events.put(('done', (build, report, launch)))
            except Exception as e:
                self.events.put(('error', str(e)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'status':
                self.status.configure(text=value)
                continue
            self.busy = False
            self.progress.stop()
            for widget in self.widgets:
                widget.state(['!disabled'])
            if kind == 'error':
                self.status.configure(text='Merge failed. Previous output was kept.')
                self.set_details(value)
                messagebox.showerror('Could not merge mods', value, parent=self)
            else:
                build, self.report, launch = value
                overlaps = self.report['conflicts']
                self.set_details(f"Merged {len(self.report['mods'])} mods into {len(self.report['files'])} files.\n"
                    + ('\n'.join(f"{c['path']}\n  {c['previous']} → {c['winner']}" for c in overlaps)
                       if overlaps else 'No overlapping files.')
                    + f'\nOutput: {build}')
                if launch:
                    try:
                        self.game_process = self.library.launch(build)
                        self.status.configure(text='Game launched with the selected mods.')
                    except Exception as e:
                        messagebox.showerror('Launch failed', str(e), parent=self)
        self.poll_id = self.after(100, self.poll)

    def close(self):
        if self.busy:
            self.status.configure(text='Please wait for the current merge to finish.')
            return
        self.library.save()
        self.after_cancel(self.poll_id)
        self.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--merge-only', action='store_true')
    parser.add_argument('--probe', action='store_true')
    args = parser.parse_args()
    portable = Path(__file__).resolve().parent.parent / 'portable.json'
    if portable.exists():
        config = json.loads(portable.read_text(encoding='utf-8'))
        selected = config.get('game', '')
        if not selected or not (Path(selected) / 'totk.exe').is_file():
            picker = tk.Tk()
            picker.withdraw()
            selected = filedialog.askdirectory(parent=picker, title='Choose your compiled game folder (containing totk.exe)')
            picker.destroy()
            if not selected:
                return
            if not (Path(selected) / 'totk.exe').is_file() or not (Path(selected) / 'romfs/index.json').is_file():
                ctypes.windll.user32.MessageBoxW(None, 'Choose a compiled TotK installation containing totk.exe and romfs/index.json.', 'Invalid game folder', 0x10)
                return
            config['game'] = selected
            portable.write_text(json.dumps(config, indent=2), encoding='utf-8')
        args.game = Path(selected)
    if args.merge_only or args.probe:
        library = Library(args.game)
        build, report = library.merge(print)
        if args.probe:
            with (build / 'probe-fs.txt').open('w') as log:
                result = subprocess.run([str(library.game / 'totk.exe'), '--profile', str(build / 'probe-profile'), '--probe-fs'],
                    cwd=library.game, env=library.launch_environment(build), stdout=log, stderr=subprocess.STDOUT)
            print('Filesystem probe exit code:', result.returncode)
            raise SystemExit(result.returncode)
        print(build)
    else:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
        lock = None
        try:
            import msvcrt
            lock = (Path(__file__).resolve().parent / 'instance.lock').open('a+b')
            if lock.tell() == 0:
                lock.write(b'0')
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                ctypes.windll.user32.MessageBoxW(None, 'The mod manager is already open.', 'TotK Mod Manager', 0x40)
                return
            Manager(args.game).mainloop()
        except Exception:
            error = traceback.format_exc()
            (Path(__file__).parent / 'startup-error.txt').write_text(error, encoding='utf-8')
            ctypes.windll.user32.MessageBoxW(None, error, 'Mod Manager could not start', 0x10)
        finally:
            if lock:
                lock.close()


if __name__ == '__main__':
    main()
