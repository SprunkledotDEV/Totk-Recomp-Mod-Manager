# Building on Windows

Requirements:

- Git.
- .NET SDK 10.
- LLVM/MinGW Clang with Windows headers/libraries (`-municode` and `-mwindows`).
- A portable Windows Python 3.14 runtime with `tkinter`, Tcl/Tk, and
  `compression.zstd`. The standard minimal embedded Python download alone does
  not supply the full Tk runtime. The supplied TotK Setup Python bundle was used
  during development. Preserve its license files when redistributing it.

From PowerShell in this source folder:

```powershell
./build.ps1 -PythonRuntime 'C:/path/to/portable-python' `
  -Dotnet 'C:/path/to/dotnet.exe' -Clang 'C:/path/to/clang.exe'
```

The script fetches the pinned TkSharp commit into ignored `vendor/`, applies the
material-preservation patch, publishes a self-contained backend, packages Python
and the UI, compiles the launcher, and runs the synthetic tests. It does not
download or read game files. The result is `dist/Mod Manager/`.

`portable.json` is created empty on a fresh build, so first launch asks the user
to choose their game installation. Existing settings are retained when rebuilding
the same distribution. Do not distribute a personally used `dist/` directory
without excluding settings, mods, metadata cache, logs, and merged builds.

To run only the tests with a suitable Python:

```powershell
python src/app/test_manager.py
```

To start the UI directly from source, provide a game folder:

```powershell
python src/app/mod_manager.py --game 'C:/Games/TotkRecomp'
```

That developer mode defaults to a game-local mod library because there is no
portable marker. Use the packaged distribution for normal independent storage.
TKCL processing additionally requires the built backend beside the Python app.

The pinned upstream engine may emit a VYaml source-generator warning on a clean
build; it did so in development, while compilation and the exercised TKCL merges
succeeded. Do not treat compile success as a game compatibility test.

## Before uploading to GitHub

Commit the source files, patch, docs, and notices. Keep `vendor/`, `dist/`, compiler
outputs, game data, mods, caches, keys, and local settings excluded. `.gitignore`
provides the main exclusions; review the actual staged files before publishing.
No remote repository or upload is performed by this project or build script.
