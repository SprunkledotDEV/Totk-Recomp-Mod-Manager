# Third-party notices

The backend references the separately fetched TkSharp project at the exact commit
in `UPSTREAM.json`. TkSharp itself carries the MIT license, retained in
`licenses/TkSharp.txt`. The patch in `patches/` changes only its material-cleanup
behavior and retains that upstream licensing.

The resolved NuGet dependencies have their own licenses. Consult
`licenses/nuget-components.json` and the `.nuspec` records and available notice
texts under `licenses/nuget/`. In particular, MessageStudio 1.1.1, SarcLibrary
3.3.4, and Tkmm.BymlLibrary 1.2.3 declare **AGPL-3.0-or-later**; do not describe the
entire backend as MIT-only. Other declared licenses and copyright holders are
recorded per component rather than replaced by a blanket project notice.

`licenses/TotK-Recomp.txt` preserves the supplied runtime project's attribution.
The .NET runtime license and third-party notices are retained in `licenses/`.
No Python, Tcl/Tk, .NET runtime, compiler, or compiled backend is committed here.
When packaging runtimes into a binary distribution, retain their accompanying
license and notice files. The build script copies the supplied Python directory
including its notices.

This source package does not assign a new license to the project's own code or
claim to settle binary-release licensing requirements. See the README's licensing
status and retain the upstream sources, modifications, and notices when preparing
a release under the applicable licenses.
