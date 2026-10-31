param(
    [Parameter(Mandatory = $true)][string]$PythonRuntime,
    [string]$Dotnet = 'dotnet',
    [string]$Clang = 'clang'
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtime = (Resolve-Path -LiteralPath $PythonRuntime).Path
if (!(Test-Path -LiteralPath (Join-Path $runtime 'pythonw.exe'))) {
    throw 'PythonRuntime must be a portable Windows Python 3.14 directory with tkinter and pythonw.exe.'
}
function Run-Native {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
$upstream = Get-Content -LiteralPath (Join-Path $root 'UPSTREAM.json') -Raw | ConvertFrom-Json
$vendor = Join-Path $root 'vendor/TkSharp'
if (!(Test-Path -LiteralPath $vendor)) {
    Run-Native git @('clone', $upstream.TkSharp.repository, $vendor)
    Run-Native git @('-C', $vendor, 'checkout', '--detach', $upstream.TkSharp.commit)
}
$revision = & git -C $vendor rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $revision -ne $upstream.TkSharp.commit) { throw 'Unexpected TkSharp revision; use the pinned checkout.' }
$patch = Join-Path $root $upstream.TkSharp.patch
& git -C $vendor apply --reverse --check $patch 2>$null
if ($LASTEXITCODE -ne 0) {
    Run-Native git @('-C', $vendor, 'apply', '--check', $patch)
    Run-Native git @('-C', $vendor, 'apply', $patch)
}
$dist = Join-Path $root 'dist/Mod Manager'
$app = Join-Path $dist 'mod-manager'
New-Item -ItemType Directory -Path $app -Force | Out-Null
Run-Native $Dotnet @('publish', (Join-Path $root 'src/backend/RecompMods.Backend.csproj'), '-c', 'Release', '-r', 'win-x64', '--self-contained', 'true', '-o', (Join-Path $app 'backend'))
Copy-Item -Path (Join-Path $root 'src/app/*.py') -Destination $app -Force
New-Item -ItemType Directory -Path (Join-Path $app 'python') -Force | Out-Null
Copy-Item -Path (Join-Path $runtime '*') -Destination (Join-Path $app 'python') -Recurse -Force
$pth = Join-Path $app 'python/python314._pth'
if (Test-Path -LiteralPath $pth) {
    Set-Content -LiteralPath $pth -Value "python314.zip`n.`nLib/site-packages`n.." -Encoding ascii
}
if (!(Test-Path -LiteralPath (Join-Path $dist 'portable.json'))) {
    [IO.File]::WriteAllText((Join-Path $dist 'portable.json'), '{}')
}
Copy-Item -LiteralPath (Join-Path $root 'licenses') -Destination $app -Recurse -Force
Copy-Item -LiteralPath (Join-Path $root 'THIRD_PARTY_NOTICES.md') -Destination $app -Force
Copy-Item -LiteralPath (Join-Path $root 'README.md'), (Join-Path $root 'CREDITS.md') -Destination $dist -Force
Run-Native $Clang @('-O2', '-municode', '-mwindows', (Join-Path $root 'src/app/launcher.c'), '-o', (Join-Path $dist 'Mod Manager.exe'), '-lshell32', '-luser32')
# Run tests from source, outside the portable distribution and its user library.
Run-Native (Join-Path $app 'python/python.exe') @((Join-Path $root 'src/app/test_manager.py'))
Write-Host "Built: $dist"
