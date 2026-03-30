param(
    [Parameter(Mandatory=$true)]
    [string]$ListFile,
    [Parameter(Mandatory=$true)]
    [string]$User,
    [Parameter(Mandatory=$true)]
    [string]$UpdateFolder
)

if (-not (Test-Path $ListFile)) {
    Write-Error "Fichier introuvable : $ListFile"
    exit 1
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8
$PSStyle.Progress.View    = 'Classic'

New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "reports") | Out-Null

# ── P/Invoke Kernel32 pour CTRL+C ──────────────────────────────────────────
Add-Type -Namespace Win32 -Name Kernel32 -MemberDefinition @'
    [DllImport("kernel32.dll")] public static extern bool FreeConsole();
    [DllImport("kernel32.dll")] public static extern bool AttachConsole(uint dwProcessId);
    [DllImport("kernel32.dll")] public static extern bool SetConsoleCtrlHandler(IntPtr h, bool add);
    [DllImport("kernel32.dll")] public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
'@

function Send-CtrlC {
    param([System.Diagnostics.Process]$Process)
    # Détache PS de sa console courante
    [Win32.Kernel32]::FreeConsole()                               | Out-Null
    # S'attache à la console du process cible
    [Win32.Kernel32]::AttachConsole([uint32]$Process.Id)          | Out-Null
    # Ignore le CTRL+C dans ce thread PS (sinon on se tue aussi)
    [Win32.Kernel32]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)| Out-Null
    # Envoie CTRL+C à tous les process du groupe console attaché
    [Win32.Kernel32]::GenerateConsoleCtrlEvent(0, 0)              | Out-Null
    Start-Sleep -Milliseconds 800
    # Retour à la console parent de PowerShell
    [Win32.Kernel32]::FreeConsole()                               | Out-Null
    [Win32.Kernel32]::AttachConsole(0xFFFFFFFF)                   | Out-Null  # ATTACH_PARENT_PROCESS
    [Win32.Kernel32]::SetConsoleCtrlHandler([IntPtr]::Zero, $false)| Out-Null
}
# ───────────────────────────────────────────────────────────────────────────

$entities = Get-Content $ListFile | Where-Object { $_.Trim() -ne "" }
$total    = $entities.Count
$i        = 0
$start    = Get-Date

$currentProc = $null

try {
    foreach ($raw in $entities) {

        $i++
        $id = $raw.Trim()

        $elapsed = (Get-Date) - $start
        $rate    = $i / [math]::Max($elapsed.TotalSeconds, 1)
        $eta     = (Get-Date).AddSeconds(($total - $i) / $rate)
        $etaStr  = if ($eta.Date -ne (Get-Date).Date) {
            $eta.ToString('dd/MM HH:mm')
        } else {
            $eta.ToString('HH:mm')
        }
        $rateMin = "{0:N1}" -f ($rate * 60)
        $percent = [int](($i / $total) * 100)

        Write-Host ("=" * 60)
        Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Entity: $id"
        Write-Host ("=" * 60)

        $queue = [System.Collections.Concurrent.ConcurrentQueue[string]]::new()

        $psi = [System.Diagnostics.ProcessStartInfo]::new()
        $psi.FileName               = "python"
        $psi.WorkingDirectory       = $PSScriptRoot
        $psi.Arguments              = "-u -m telegram_checker.main --md --no --llm-url `"http://127.0.0.1:1234/api/v1/chat/`" --llm-model `"openai/gpt-oss-20b`" --user `"$User`" --out-file `"reports/$User/$id.log`" --report `"$id`" --update-file `"$UpdateFolder/tg_$id.md`""
        $psi.UseShellExecute        = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true
        $psi.CreateNoWindow         = $true
        $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $psi.StandardErrorEncoding  = [System.Text.Encoding]::UTF8
        $psi.Environment["PYTHONIOENCODING"] = "utf-8"

        $proc = [System.Diagnostics.Process]::new()
        $proc.StartInfo = $psi

        $handler = {
            if ($null -ne $EventArgs.Data) {
                $Event.MessageData.Enqueue($EventArgs.Data)
            }
        }

        Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action $handler -MessageData $queue | Out-Null
        Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived  -Action $handler -MessageData $queue | Out-Null

        $proc.Start()            | Out-Null
        $proc.BeginOutputReadLine()
        $proc.BeginErrorReadLine()

        # Expose le process courant au bloc finally
        $currentProc = $proc

        $spinner = @("|", "/", "-", "\")
        $s       = 0

        while (-not $proc.HasExited) {
            $line = $null
            while ($queue.TryDequeue([ref]$line)) {
                Write-Host "  $line"
                Write-Progress `
                    -Activity "Telegram entity analysis" `
                    -Status "$i/$total  |  $rateMin ent/min  |  ETA $etaStr  $($spinner[$s])" `
                    -CurrentOperation $id `
                    -PercentComplete $percent
            }
            $s = ($s + 1) % $spinner.Length
            Write-Progress `
                -Activity "Telegram entity analysis" `
                -Status "$i/$total  |  $rateMin ent/min  |  ETA $etaStr  $($spinner[$s])" `
                -CurrentOperation $id `
                -PercentComplete $percent
            Start-Sleep -Milliseconds 150
        }

        # Vider le reste de la queue après exit
        $line = $null
        while ($queue.TryDequeue([ref]$line)) {
            Write-Host "  $line"
        }

        Write-Host "EXIT CODE: $($proc.ExitCode)" -ForegroundColor Yellow
        if ($proc.ExitCode -ne 0) {
            Write-Host "FAILED: $id (exit $($proc.ExitCode))" -ForegroundColor Red
        }

        Get-EventSubscriber | Where-Object { $_.SourceObject -eq $proc } | Unregister-Event -Force
        $currentProc = $null   # itération terminée proprement
    }
}
finally {
    if ($null -ne $currentProc -and -not $currentProc.HasExited) {
        Write-Host "`nInterruption — envoi CTRL+C au processus Python ($($currentProc.Id))..." -ForegroundColor Yellow
        Send-CtrlC -Process $currentProc
        if (-not $currentProc.WaitForExit(5000)) {
            Write-Host "Python ne répond pas après 5s — kill forcé." -ForegroundColor Red
            $currentProc.Kill()
        } else {
            Write-Host "Python s'est arrêté proprement (exit $($currentProc.ExitCode))." -ForegroundColor Cyan
        }
        Get-EventSubscriber | Where-Object { $_.SourceObject -eq $currentProc } | Unregister-Event -Force
    }
    Write-Progress -Activity "Telegram entity analysis" -Completed
}
