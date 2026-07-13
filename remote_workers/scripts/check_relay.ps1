param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8013
)

$ErrorActionPreference = "Stop"
Invoke-RestMethod -Uri "http://${HostName}:${Port}/health"

