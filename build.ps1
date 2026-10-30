param(
    [switch]$Install
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root "extension"
$dist = Join-Path $root "dist"
$stage = Join-Path $dist "stage"
$output = Join-Path $dist "LibreOfficeAI.oxt"

if (-not (Test-Path -LiteralPath (Join-Path $source "description.xml"))) {
    throw "No se encontró extension\description.xml"
}

if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Path $stage -Force | Out-Null

Get-ChildItem -LiteralPath $source -Recurse -Force | ForEach-Object {
    $relative = $_.FullName.Substring($source.Length).TrimStart("\")
    if ($relative -match "(^|\\)__pycache__(\\|$)") { return }
    if ($_.Name -like "*.pyc") { return }
    if ($_.Name -like "*.pyo") { return }

    $target = Join-Path $stage $relative
    if ($_.PSIsContainer) {
        New-Item -ItemType Directory -Path $target -Force | Out-Null
    } else {
        $parent = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $parent)) {
            New-Item -ItemType Directory -Path $parent -Force | Out-Null
        }
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

if (Test-Path -LiteralPath $output) {
    Remove-Item -LiteralPath $output -Force
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open(
    $output,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    Get-ChildItem -LiteralPath $stage -Recurse -File | ForEach-Object {
        $entryName = $_.FullName.Substring($stage.Length).TrimStart("\").Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $_.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
} finally {
    $archive.Dispose()
}

Remove-Item -LiteralPath $stage -Recurse -Force
Write-Host "Extensión creada: $output"

if ($Install) {
    $unopkg = "C:\Program Files\LibreOffice\program\unopkg.com"
    if (-not (Test-Path -LiteralPath $unopkg)) {
        throw "No se encontró unopkg.com. Instala la extensión manualmente."
    }
    & $unopkg add -f --suppress-license $output
    Write-Host "Extensión instalada. Reinicia LibreOffice."
}
