<#
.SYNOPSIS
    Verify the Toga person-list column widths on Windows across DPI/scaling settings.

.DESCRIPTION
    Launches the GEDCOM Navigator Toga app (WinForms backend) with a sample file
    auto-loaded and a diagnostic enabled, then:
      * reads back the REAL native column widths + Toga's dpi_scale (quantitative check),
      * captures a screenshot of the app window (visual check), labeled with the scale,
      * asserts the Born/Died columns scaled with DPI and that Name absorbs the slack.

    To test different scalings: change Settings > System > Display > "Scale", then re-run
    this script. Each run writes a screenshot + a line to results.txt labeled with the
    detected scale, so runs at 100/125/150/200% accumulate for comparison. Also try
    dragging the window between monitors of different scale before pressing capture.

.PARAMETER Repo
    Path to the gedcom-navigator checkout. Defaults to the script's parent directory.

.PARAMETER Python
    Python executable. Defaults to .\.venv\Scripts\python.exe if present, else "python".

.PARAMETER OutDir
    Where screenshots + results.txt are written. Defaults to <Repo>\dev\column-shots.

.PARAMETER Install
    Also run "pip install toga-winforms" before launching.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File dev\test-columns-windows.ps1
#>
[CmdletBinding()]
param(
    [string]$Repo,
    [string]$Python,
    [string]$OutDir,
    [switch]$Install
)

$ErrorActionPreference = "Stop"

# --- Make THIS process per-monitor DPI aware, so GetWindowRect + the screen capture
#     work in real physical pixels (otherwise Windows virtualizes coords and the shot
#     is blurry / wrong-sized). Must happen before any Graphics work. ------------------
Add-Type -Namespace Win -Name Dpi -MemberDefinition @"
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool SetProcessDpiAwarenessContext(System.IntPtr value);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool SetProcessDPIAware();
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern uint GetDpiForWindow(System.IntPtr hwnd);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool GetWindowRect(System.IntPtr hwnd, out RECT rect);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(System.IntPtr hwnd);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool ShowWindow(System.IntPtr hwnd, int nCmdShow);
    public struct RECT { public int Left, Top, Right, Bottom; }
"@
# -4 = DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2; fall back to system-aware on Win8.1-.
try { [void][Win.Dpi]::SetProcessDpiAwarenessContext([System.IntPtr](-4)) }
catch { try { [void][Win.Dpi]::SetProcessDPIAware() } catch {} }

# Helper to locate a native child control (the person-list is a SysListView32) by class,
# so the zoomed crop targets the list exactly regardless of window size / split / DPI.
Add-Type -Namespace Win -Name Child -MemberDefinition @"
    private delegate bool EnumProc(System.IntPtr h, System.IntPtr l);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool EnumChildWindows(System.IntPtr parent, EnumProc cb, System.IntPtr l);
    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet=System.Runtime.InteropServices.CharSet.Auto)]
    private static extern int GetClassName(System.IntPtr h, System.Text.StringBuilder s, int max);
    public static System.IntPtr FindByClass(System.IntPtr parent, string cls) {
        System.IntPtr found = System.IntPtr.Zero;
        EnumChildWindows(parent, delegate (System.IntPtr h, System.IntPtr l) {
            var sb = new System.Text.StringBuilder(256);
            GetClassName(h, sb, sb.Capacity);
            if (sb.ToString() == cls) { found = h; return false; }
            return true;
        }, System.IntPtr.Zero);
        return found;
    }
"@

Add-Type -AssemblyName System.Drawing

# --- Resolve paths --------------------------------------------------------------------
if (-not $Repo)   { $Repo = Split-Path -Parent $PSScriptRoot }
$Repo = (Resolve-Path $Repo).Path
if (-not $Python) {
    $venv = Join-Path $Repo ".venv\Scripts\python.exe"
    if (Test-Path $venv) { $Python = $venv } else { $Python = "python" }
}
if (-not $OutDir) { $OutDir = Join-Path $Repo "dev\column-shots" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$sample = Join-Path $Repo "samples\fictional_genealogy.ged"
if (-not (Test-Path $sample)) { throw "Sample GEDCOM not found: $sample" }

$env:PYTHONPATH = Join-Path $Repo "src"
$env:GEDCOM_DIAG = "1"

Write-Host "Repo   : $Repo"
Write-Host "Python : $Python"
Write-Host "Out    : $OutDir"

# --- Verify the WinForms backend is importable ---------------------------------------
if ($Install) { & $Python -m pip install toga-winforms }
& $Python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('toga_winforms') else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "toga_winforms not installed. Re-run with -Install, or: $Python -m pip install toga-winforms"
}

# --- Seed the recent-files list via the app's OWN ConfigManager, so the app
#     auto-opens the sample on launch (no manual File>Open needed). -------------------
& $Python -c "from gedcom_config import ConfigManager as C; c=C(C.default_path()); c.set_recent_files([r'$sample']); print('seeded', C.default_path())"

# --- Launch the app, capturing stdout (diagnostic line) + stderr ---------------------
$stdout = Join-Path $OutDir "app.stdout.log"
$stderr = Join-Path $OutDir "app.stderr.log"
Remove-Item $stdout,$stderr -ErrorAction SilentlyContinue
$proc = Start-Process -FilePath $Python -ArgumentList "-m","gedcom_toga" `
    -WorkingDirectory $Repo -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Write-Host "Launched pid $($proc.Id); waiting for window..."

# --- Wait for the window handle + the diagnostic line --------------------------------
$hwnd = [System.IntPtr]::Zero
$diag = $null
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    $p = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
    if (-not $p) { throw "App exited early. stderr:`n$(Get-Content $stderr -Raw)" }
    if ($p.MainWindowHandle -ne 0 -and $p.MainWindowTitle -like "*GEDCOM*") {
        $hwnd = $p.MainWindowHandle
    }
    $line = Select-String -Path $stdout -Pattern "GEDCOM_DIAG_COLUMNS" -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($line -and $hwnd -ne 0) {
        $diag = ($line.Line -replace "^.*GEDCOM_DIAG_COLUMNS\s*", "") | ConvertFrom-Json
        break
    }
}
if ($hwnd -eq 0) { $proc | Stop-Process -Force; throw "Timed out waiting for the app window." }

# --- Detect the window's DPI/scale and capture the window ----------------------------
[void][Win.Dpi]::ShowWindow($hwnd, 9)            # SW_RESTORE
[void][Win.Dpi]::SetForegroundWindow($hwnd)
Start-Sleep -Milliseconds 800                    # let it paint/foreground

$dpi = [Win.Dpi]::GetDpiForWindow($hwnd)
if ($dpi -eq 0) { $dpi = 96 }
$scale = [math]::Round($dpi / 96.0, 2)

$r = New-Object Win.Dpi+RECT
[void][Win.Dpi]::GetWindowRect($hwnd, [ref]$r)
$w = $r.Right - $r.Left; $h = $r.Bottom - $r.Top
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.Left, $r.Top, 0, 0, (New-Object System.Drawing.Size $w, $h))
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$png = Join-Path $OutDir ("gedcom-cols_scale-{0}_{1}x{2}_{3}.png" -f $scale, $w, $h, $stamp)
$bmp.Save($png, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()

# --- Zoomed crop of the person-list header (+ first rows), upscaled for a clear look
#     at the column widths. Targets the real SysListView32 rect; falls back to the
#     top-left region of the window if the control class can't be found. -------------
$pngZoom = Join-Path $OutDir ("gedcom-cols_scale-{0}_{1}_listzoom.png" -f $scale, $stamp)
$lv = [Win.Child]::FindByClass($hwnd, "SysListView32")
if ($lv -ne [System.IntPtr]::Zero) {
    $lr = New-Object Win.Dpi+RECT
    [void][Win.Dpi]::GetWindowRect($lv, [ref]$lr)
    $cropX = $lr.Left; $cropY = $lr.Top
    $cropW = $lr.Right - $lr.Left
    $cropH = [math]::Min($lr.Bottom - $lr.Top, [int][math]::Round(150 * $scale))
} else {
    Write-Host "(SysListView32 not found; cropping the top-left window region instead)"
    $cropX = $r.Left; $cropY = $r.Top + [int][math]::Round(40 * $scale)
    $cropW = [int][math]::Round($w * 0.45)
    $cropH = [int][math]::Round(150 * $scale)
}
$crop = New-Object System.Drawing.Bitmap $cropW, $cropH
$cg = [System.Drawing.Graphics]::FromImage($crop)
$cg.CopyFromScreen($cropX, $cropY, 0, 0, (New-Object System.Drawing.Size $cropW, $cropH))
$cg.Dispose()
$zoom = 2
$zbmp = New-Object System.Drawing.Bitmap ($cropW * $zoom), ($cropH * $zoom)
$zg = [System.Drawing.Graphics]::FromImage($zbmp)
$zg.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$zg.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
$zg.DrawImage($crop, (New-Object System.Drawing.Rectangle 0, 0, ($cropW * $zoom), ($cropH * $zoom)))
$zg.Dispose()
$zbmp.Save($pngZoom, [System.Drawing.Imaging.ImageFormat]::Png)
$zbmp.Dispose(); $crop.Dispose()

# --- Report + assert ------------------------------------------------------------------
"" ; Write-Host "==== RESULT (window DPI $dpi -> scale ${scale}x) ====" -ForegroundColor Cyan
Write-Host "Screenshot: $png"
Write-Host "List zoom : $pngZoom"
$verdict = "NO DIAG"
if ($diag) {
    $names = $diag.headings -join ", "
    $wid   = $diag.widths -join ", "
    Write-Host ("Backend    : {0}" -f $diag.backend)
    Write-Host ("Headings   : {0}" -f $names)
    Write-Host ("Widths(px) : {0}" -f $wid)
    Write-Host ("Toga scale : {0}   client width: {1}px" -f $diag.dpi_scale, $diag.client_width)

    $name = $diag.widths[0]; $born = $diag.widths[1]; $died = $diag.widths[2]
    $expect = [math]::Round(64 * $diag.dpi_scale)
    $bornOk = [math]::Abs($born - $expect) -le 3
    $diedOk = [math]::Abs($died - $expect) -le 3
    $nameOk = ($name -gt $born) -and ($name -gt $died)
    $scaleMatch = [math]::Abs([double]$diag.dpi_scale - $scale) -le 0.05
    Write-Host ("Born/Died  : {0}/{1}px  (expected ~{2}px at {3}x)  -> {4}" -f `
        $born, $died, $expect, $diag.dpi_scale, ($(if ($bornOk -and $diedOk) {"OK"} else {"MISMATCH"})))
    Write-Host ("Name wider : {0}" -f $(if ($nameOk) {"OK ($name px)"} else {"FAIL ($name px)"}))
    Write-Host ("Toga scale matches window DPI: {0}" -f $(if ($scaleMatch) {"OK"} else {"CHECK"}))
    $verdict = $(if ($bornOk -and $diedOk -and $nameOk) { "PASS" } else { "FAIL" })
}
Write-Host ("VERDICT    : {0}" -f $verdict) -ForegroundColor $(if ($verdict -eq "PASS") {"Green"} else {"Yellow"})

$resfile = Join-Path $OutDir "results.txt"
("[{0}] scale={1}x dpi={2} verdict={3} widths=[{4}] png={5}" -f `
    $stamp, $scale, $dpi, $verdict, ($diag.widths -join ","), (Split-Path -Leaf $png)) |
    Add-Content -Path $resfile

# --- Clean up -------------------------------------------------------------------------
$proc | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host "`nDone. Change Display scaling and re-run to test another setting; results accumulate in $resfile"
