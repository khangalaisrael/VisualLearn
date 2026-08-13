# Starts the VisionLearn backend stack (db, redis, backend) in the background.
# Intended to run at Windows login via Task Scheduler — see backend/README.md's
# "Always-on local setup" section for how to register it.

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

docker compose up -d
