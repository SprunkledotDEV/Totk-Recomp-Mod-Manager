# Credits

- **TotK Recomp — Valiantsin Dzerakh and contributors.** The native game runtime,
  indexed RomFS format, and verified overlay loader make this manager possible.
  Integrated against the user's supplied `totk-pc-recomp-main` source and 0.2.1
  release. Its MIT notice is retained in `licenses/TotK-Recomp.txt`. The Python
  `mod_overlay.py` utility was written during this manager's development against
  that interface; it is not an upstream TKMM utility.
- **[TKMM](https://github.com/TKMM-Team/Tkmm) — TKMM Team and contributors.**
  Reference mod manager, package workflow, and source used to understand TKCL.
  The desktop TKMM application itself is not bundled or copied into this UI.
- **[TkSharp](https://github.com/TKMM-Team/TkSharp) — TKMM Team and contributors.**
  The actual package reader, structured merge engine, model processing, resource
  calculations, and supporting data. Pinned to the revision in `UPSTREAM.json`.
  The local material-preservation patch is explicitly retained in `patches/`.
- **[Python](https://www.python.org/) / [Tcl and Tk](https://www.tcl-lang.org/).**
  Python 3.14 provides the application runtime and Zstandard support; Tkinter/ttk
  supplies the desktop UI. The development installation used the Python/Tk bundle
  included with the supplied TotK Setup distribution.
- **[.NET](https://github.com/dotnet/runtime) and [LLVM](https://llvm.org/).**
  .NET runs the C# backend; LLVM/MinGW Clang builds the small Windows launcher.
- **[TotkRSTB](https://github.com/VelouriasMoon/TotkRSTB) — VelouriasMoon.**
  Reference for the conservative maximum-allocation resource-table merge policy.
  No source code from that project was copied.
- **Transitive dependency authors.** BfresLibrary, BsDiff, CommunityToolkit,
  LanguageExt, MessageStudio, Newtonsoft.Json, Revrs, RstbLibrary, SarcLibrary,
  SharpCompress, SharpZipLib, Tkmm.BymlLibrary, Ulid, VYaml, ZstdSharp, and Microsoft
  runtime libraries. Exact versions, authors, project URLs and license declarations
  are recorded in `licenses/nuget-components.json`.
- **Mod authors whose packages were used for local testing.** Aster (Dark Mode UI)
  and legend5v (The Linkle Mod), as identified by their package metadata. OOT Hair
  Physics and Makeup for Link were also supplied as test mods; their authors were
  not identified in the supplied folder metadata. None of these mods is included
  in this source distribution, and these credits do not imply endorsement.

Implementation and investigation were assisted by OpenAI Codex. The repository
owner should choose their preferred project name, author attribution, and license
before publication.
