<#
================================================================================
  audit_J_drive.ps1  --  APEX Quant folder audit  (READ-ONLY / படிக்க மட்டும்)
================================================================================
  இந்த script எதையும் DELETE பண்ணாது / MOVE பண்ணாது.
  This script NEVER deletes or moves anything. It only reads and reports.

  என்ன செய்யும் / What it does:
    1. J: drive-ல உள்ள ஒவ்வொரு folder-ஓட size + file count காட்டும்.
    2. பழைய folder-ல உள்ள file எல்லாம் LIVE/BACKUP folder-ல இருக்கானு check பண்ணும்.
    3. "Unique" (வேற எங்கேயும் இல்லாத) file-ஐ list பண்ணும் -- delete பண்ணா இவை போயிடும்.
    4. எந்த folder safe-ஆ delete பண்ணலாம்னு verdict கொடுக்கும்.
    5. ஒரு report file-ஆ save பண்ணும்.

  Usage:
    Right-click -> "Run with PowerShell"   (அல்லது run_audit.bat-ஐ double-click)
    Optional exact check (slow):  powershell -File audit_J_drive.ps1 -Hash
================================================================================
#>

param(
    [string]   $Drive          = "J:",
    [string[]] $LiveFolders    = @("My_Trader", "APEX_KNOWLEDGE_LAKE"),
    [string[]] $BackupFolders  = @("My_Trader_BACKUP_2026-06-14"),
    [string[]] $OldCandidates  = @("APEX_AGI_Forex_Trading_Bot"),
    [switch]   $Hash   # SHA256 exact comparison (மிகவும் accurate, ஆனா மெதுவா)
)

$ErrorActionPreference = "Stop"
$report = New-Object System.Collections.Generic.List[string]

function Say {
    param([string]$Text, [string]$Color = "Gray")
    Write-Host $Text -ForegroundColor $Color
    $report.Add($Text)
}

function HR { Say ("-" * 78) "DarkGray" }

# ----------------------------------------------------------------------------
#  Helpers
# ----------------------------------------------------------------------------

function Get-FolderStats {
    param([string]$Path)
    $files = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue
    $sum   = ($files | Measure-Object Length -Sum).Sum
    if ($null -eq $sum) { $sum = 0 }
    [pscustomobject]@{
        Path  = $Path
        Files = @($files).Count
        Bytes = [int64]$sum
        GB    = [math]::Round(($sum / 1GB), 2)
    }
}

# Build a lookup of every file in a folder.
#   Default key = "filename|size"  (survives moves / restructuring).
#   With -Hash  key = "SHA256"      (exact content match).
function Index-Folder {
    param([string]$Path, [switch]$UseHash)
    $lookup = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $lookup }
    Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            if ($UseHash) {
                $key = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            } else {
                $key = ($_.Name.ToLower() + "|" + $_.Length)
            }
            if (-not $lookup.ContainsKey($key)) { $lookup[$key] = $_.FullName }
        } catch { }
    }
    return $lookup
}

function Get-FileKey {
    param($File, [switch]$UseHash)
    if ($UseHash) { return (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash }
    return ($File.Name.ToLower() + "|" + $File.Length)
}

# ----------------------------------------------------------------------------
#  Banner
# ----------------------------------------------------------------------------
Say ""
Say "================================================================" "Cyan"
Say "   APEX Quant -- J: Drive Folder Audit   (READ-ONLY report)"      "Cyan"
Say "   இந்த script எதையும் delete பண்ணாது. Report மட்டும்தான்."        "Cyan"
Say ("   Run time: " + (Get-Date))                                     "DarkCyan"
if ($Hash) { Say "   Mode: SHA256 exact match (slow but certain)"      "DarkCyan" }
else       { Say "   Mode: name+size match (fast). Exact-க்கு -Hash use பண்ணுங்க." "DarkCyan" }
Say "================================================================" "Cyan"

if (-not (Test-Path -LiteralPath ($Drive + "\"))) {
    Say ""
    Say ("!! Drive " + $Drive + " கிடைக்கல. Drive letter சரியா இருக்கானு பாருங்க.") "Red"
    Read-Host "Press Enter to exit"
    return
}

# ----------------------------------------------------------------------------
#  STEP 1 -- All top-level folders: size + count
# ----------------------------------------------------------------------------
Say ""
Say "STEP 1 -- $Drive ல உள்ள folders (size + file count)" "Yellow"
HR
$topFolders = Get-ChildItem -LiteralPath ($Drive + "\") -Directory -Force -ErrorAction SilentlyContinue
$stats = @{}
foreach ($d in $topFolders) {
    $s = Get-FolderStats -Path $d.FullName
    $stats[$d.Name] = $s
    Say ("  {0,-38} {1,8:N2} GB   {2,7} files" -f $d.Name, $s.GB, $s.Files)
}
if ($topFolders.Count -eq 0) { Say "  (folders எதுவும் இல்ல)" "DarkGray" }

# ----------------------------------------------------------------------------
#  STEP 2 -- Build reference index (LIVE + BACKUP)
# ----------------------------------------------------------------------------
Say ""
Say "STEP 2 -- LIVE + BACKUP folders-ஐ index பண்றேன் (reference set)" "Yellow"
HR
$reference   = @{}
$refSources  = @()
foreach ($name in ($LiveFolders + $BackupFolders)) {
    $path = Join-Path ($Drive + "\") $name
    if (Test-Path -LiteralPath $path) {
        Say ("  indexing: " + $name + " ...") "DarkGray"
        $idx = Index-Folder -Path $path -UseHash:$Hash
        foreach ($k in $idx.Keys) { if (-not $reference.ContainsKey($k)) { $reference[$k] = $idx[$k] } }
        $refSources += $name
    } else {
        Say ("  (இல்ல, skip: " + $name + ")") "DarkGray"
    }
}
Say ("  Reference set: " + $reference.Count + " unique files from [" + ($refSources -join ", ") + "]") "Gray"

# ----------------------------------------------------------------------------
#  STEP 3 -- Check each OLD candidate against the reference
# ----------------------------------------------------------------------------
Say ""
Say "STEP 3 -- பழைய folder(s) safe-ஆ delete பண்ணலாமானு check" "Yellow"
HR

$verdicts = @()
foreach ($name in $OldCandidates) {
    $path = Join-Path ($Drive + "\") $name
    if (-not (Test-Path -LiteralPath $path)) { Say ("  (இல்ல, skip: " + $name + ")") "DarkGray"; continue }

    Say ""
    Say ("  >> Folder: " + $name) "White"
    $files   = Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue
    $total   = @($files).Count
    $missing = New-Object System.Collections.Generic.List[string]

    foreach ($f in $files) {
        try {
            $key = Get-FileKey -File $f -UseHash:$Hash
            if (-not $reference.ContainsKey($key)) {
                $missing.Add($f.FullName.Substring($path.Length).TrimStart('\'))
            }
        } catch { $missing.Add("(read error) " + $f.FullName) }
    }

    $covered = $total - $missing.Count
    Say ("     மொத்த files: {0}   |   வேற folder-ல இருக்கு: {1}   |   unique (எங்கேயும் இல்ல): {2}" -f $total, $covered, $missing.Count)

    if ($missing.Count -eq 0 -and $total -gt 0) {
        Say "     ✅ VERDICT: SAFE TO DELETE -- இந்த folder-ல உள்ள எல்லா file-ம் ஏற்கனவே LIVE/BACKUP-ல இருக்கு." "Green"
        Say "        (ஆனா delete-க்கு முன்னாடி கீழே உள்ள Step 4 backup-ஐ பண்ணுங்க.)" "Green"
        $verdicts += [pscustomobject]@{ Folder = $name; Verdict = "SAFE TO DELETE (after backup)"; Unique = 0 }
    } elseif ($total -eq 0) {
        Say "     ⚪ VERDICT: காலியா இருக்கு / படிக்க முடியல." "DarkGray"
        $verdicts += [pscustomobject]@{ Folder = $name; Verdict = "EMPTY / unreadable"; Unique = 0 }
    } else {
        Say ("     ⚠️ VERDICT: இன்னும் DELETE பண்ணாதீங்க -- " + $missing.Count + " file வேற எங்கேயும் இல்ல:") "Red"
        $show = [math]::Min($missing.Count, 30)
        for ($i = 0; $i -lt $show; $i++) { Say ("        - " + $missing[$i]) "Red" }
        if ($missing.Count -gt $show) { Say ("        ... மேலும் " + ($missing.Count - $show) + " files (full list report file-ல)") "Red" }
        # full list to report only
        for ($i = $show; $i -lt $missing.Count; $i++) { $report.Add("        - " + $missing[$i]) }
        $verdicts += [pscustomobject]@{ Folder = $name; Verdict = "DO NOT DELETE -- has unique files"; Unique = $missing.Count }
    }
}

# ----------------------------------------------------------------------------
#  STEP 4 -- Next steps
# ----------------------------------------------------------------------------
Say ""
Say "STEP 4 -- அடுத்து என்ன பண்ணணும்" "Yellow"
HR
Say "  1. மேலே ✅ SAFE வந்த folder-ஐ மட்டும் delete பண்ணலாம் -- ஆனா முதல்ல harddisk-க்கு copy:" "Gray"
Say '       robocopy "J:\<FOLDER>" "E:\OLD_BOT_ARCHIVE\<FOLDER>" /E /COPY:DAT /R:2 /W:5 /LOG:E:\copy_log.txt' "White"
Say "       (E: = உங்க harddisk. copy_log.txt-ல '0 Failed' வந்தா copy perfect.)" "DarkGray"
Say "  2. Copy verify ஆனப்புறம் மட்டும்:  Remove-Item 'J:\<FOLDER>' -Recurse -Force" "Gray"
Say "  3. ⚠️ வந்த folder-ஐ delete பண்ணாதீங்க -- unique file-ஐ முதல்ல காப்பாத்துங்க." "Gray"
Say "  4. வச்சுக்கணும்:  My_Trader (live), APEX_KNOWLEDGE_LAKE, My_Trader_BACKUP_2026-06-14" "Gray"

# Summary table
Say ""
Say "SUMMARY" "Yellow"
HR
foreach ($v in $verdicts) { Say ("  {0,-38} -> {1}" -f $v.Folder, $v.Verdict) }

# ----------------------------------------------------------------------------
#  Save report
# ----------------------------------------------------------------------------
$stamp      = Get-Date -Format "yyyy-MM-dd_HHmm"
$reportPath = Join-Path ($Drive + "\") ("_AUDIT_REPORT_" + $stamp + ".txt")
try {
    $report | Out-File -LiteralPath $reportPath -Encoding UTF8
    Say ""
    Say ("Report saved: " + $reportPath) "Cyan"
} catch {
    Say ("Report save பண்ண முடியல: " + $_.Exception.Message) "DarkYellow"
}

Say ""
Say "முடிஞ்சது. இந்த script எதையும் delete பண்ணல -- நீங்கதான் முடிவு பண்ணணும். ✅" "Green"
Read-Host "Press Enter to exit"
