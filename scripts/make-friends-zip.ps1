<#
  Builds the extension for sharing and zips it, ready to upload (for example
  to a GitHub Release) and link from the install page.

  The build contains the server's shared API key, read from a file OUTSIDE the
  repository, so the zip must never be committed. The key is never printed.

  Usage (from anywhere):
    powershell -ExecutionPolicy Bypass -File scripts\make-friends-zip.ps1
  Options:
    -KeyFile  path to the file holding the key   (default: ~\.visionlearn_key)
    -Backend  server address baked into the build (default: https://visionlearn.fyi)
    -Out      where to write the zip              (default: Desktop\VisionLearn-extension.zip)
#>
param(
  [string]$KeyFile = (Join-Path $HOME ".visionlearn_key"),
  [string]$Backend = "https://visionlearn.fyi",
  [string]$Out = (Join-Path $HOME "Desktop\VisionLearn-extension.zip")
)

$ErrorActionPreference = "Stop"

$extension = Join-Path (Split-Path $PSScriptRoot -Parent) "extension"
if (-not (Test-Path $KeyFile)) { throw "Key file not found: $KeyFile" }
$key = (Get-Content $KeyFile -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($key)) { throw "Key file is empty: $KeyFile" }

$stage = Join-Path ([System.IO.Path]::GetTempPath()) ("visionlearn-zip-" + [guid]::NewGuid().ToString("N"))
try {
  Push-Location $extension
  $env:VITE_BACKEND_URL = $Backend
  $env:VITE_LOCAL_API_KEY = $key
  npx vite build --outDir $stage --emptyOutDir | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "The build failed." }
}
finally {
  Remove-Item Env:VITE_LOCAL_API_KEY -ErrorAction SilentlyContinue
  Remove-Item Env:VITE_BACKEND_URL -ErrorAction SilentlyContinue
  Pop-Location
}

try {
  if (-not (Test-Path (Join-Path $stage "manifest.json"))) { throw "The build has no manifest.json." }
  if (Test-Path $Out) { Remove-Item $Out -Force }
  # Written entry by entry: Windows PowerShell 5.1's built-in zip tools (Compress-Archive
  # and ZipFile.CreateFromDirectory) store backslash paths, which break when the zip is
  # opened on a Mac. Entries here always use forward slashes.
  Add-Type -AssemblyName System.IO.Compression
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $stageFull = (Get-Item $stage).FullName.TrimEnd([char]92)
  $stream = [System.IO.File]::Open($Out, [System.IO.FileMode]::Create)
  $archive = New-Object System.IO.Compression.ZipArchive($stream, [System.IO.Compression.ZipArchiveMode]::Create)
  try {
    Get-ChildItem -LiteralPath $stageFull -Recurse -File | ForEach-Object {
      $entry = $_.FullName.Substring($stageFull.Length).TrimStart([char]92, [char]47).Replace([string][char]92, "/")
      [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $archive, $_.FullName, $entry, [System.IO.Compression.CompressionLevel]::Optimal)
    }
  }
  finally {
    $archive.Dispose()
    $stream.Dispose()
  }
  $mb = [math]::Round((Get-Item $Out).Length / 1MB, 2)
  Write-Host "Created $Out ($mb MB), built for $Backend."
  Write-Host "Upload it, then set EXTENSION_DOWNLOAD_URL in Render to its link. Do not commit this file."
}
finally {
  Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}
