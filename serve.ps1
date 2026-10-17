# ============================================================================
#  Cybercab Forum - minimal static file server
#  ---------------------------------------------------------------------------
#  Uses System.Net.HttpListener, which ships with Windows. No Node, no Python,
#  no dependencies.
#
#  Usage:
#      powershell -ExecutionPolicy Bypass -File .\serve.ps1
#      powershell -ExecutionPolicy Bypass -File .\serve.ps1 -Port 9000
# ============================================================================

param(
  [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$prefix = "http://localhost:$Port/"

$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)

try {
  $listener.Start()
} catch {
  Write-Host ""
  Write-Host "Could not start a listener on $prefix" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  Write-Host ""
  Write-Host "Another process may already be using port $Port. Try -Port 9000."
  exit 1
}

$contentTypes = @{
  ".html" = "text/html; charset=utf-8"
  ".css"  = "text/css; charset=utf-8"
  ".js"   = "application/javascript; charset=utf-8"
  ".json" = "application/json; charset=utf-8"
  ".svg"  = "image/svg+xml"
  ".ico"  = "image/x-icon"
  ".png"  = "image/png"
  ".jpg"  = "image/jpeg"
  ".jpeg" = "image/jpeg"
  ".webp" = "image/webp"
  ".md"   = "text/plain; charset=utf-8"
  ".txt"  = "text/plain; charset=utf-8"
}

Write-Host ""
Write-Host "  Cybercab Forum" -ForegroundColor Yellow
Write-Host "  serving  $root"
Write-Host "  at       $prefix" -ForegroundColor Green
Write-Host ""
Write-Host "  Press Ctrl+C to stop."
Write-Host ""

function Send-Text {
  param($Response, [int]$StatusCode, [string]$Body)
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
  $Response.StatusCode = $StatusCode
  $Response.ContentType = "text/plain; charset=utf-8"
  $Response.ContentLength64 = $bytes.Length
  $Response.OutputStream.Write($bytes, 0, $bytes.Length)
}

while ($listener.IsListening) {

  try {
    $context  = $listener.GetContext()
    $request  = $context.Request
    $response = $context.Response

    $relative = [System.Uri]::UnescapeDataString($request.Url.LocalPath).TrimStart("/")
    if ([string]::IsNullOrWhiteSpace($relative)) { $relative = "index.html" }
    if ($relative.EndsWith("/")) { $relative = $relative + "index.html" }

    $candidate = Join-Path $root $relative

    # Resolve and confine to the project directory (no path traversal).
    $full = [System.IO.Path]::GetFullPath($candidate)
    if (-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
      Send-Text $response 403 "403 Forbidden"
    }
    elseif (Test-Path $full -PathType Container) {
      $nested = Join-Path $full "index.html"
      if (Test-Path $nested -PathType Leaf) {
        $bytes = [System.IO.File]::ReadAllBytes($nested)
        $response.ContentType = $contentTypes[".html"]
        $response.ContentLength64 = $bytes.Length
        $response.OutputStream.Write($bytes, 0, $bytes.Length)
      } else {
        Send-Text $response 404 "404 Not Found"
      }
    }
    elseif (Test-Path $full -PathType Leaf) {
      $extension = [System.IO.Path]::GetExtension($full).ToLowerInvariant()
      $type = if ($contentTypes.ContainsKey($extension)) { $contentTypes[$extension] } else { "application/octet-stream" }
      $bytes = [System.IO.File]::ReadAllBytes($full)
      $response.ContentType = $type
      $response.ContentLength64 = $bytes.Length
      $response.OutputStream.Write($bytes, 0, $bytes.Length)
    }
    else {
      Send-Text $response 404 "404 Not Found"
    }

    $response.OutputStream.Close()
  }
  catch {
    # A dropped connection or a malformed request should not kill the server.
    try { $context.Response.OutputStream.Close() } catch { }
  }
}
