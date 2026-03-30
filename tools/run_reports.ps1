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

Add-Type -Namespace Win32 -Name Kernel32 -MemberDefinition @'
    [DllImport("kernel32.dll")] public static extern bool FreeConsole();
    [DllImport("kernel32.dll")] public static extern bool AttachConsole(uint dwProcessId);
    [DllImport("kernel32.dll")] public static extern bool SetConsoleCtrlHandler(IntPtr h, bool add);
    [DllImport("kernel32.dll")] public static extern bool GenerateConsoleCtrlEvent(uint dwCtrlEvent, uint dwProcessGroupId);
'@

function Send-CtrlC {
    param([System.Diagnostics.Process]$Process)
    [Win32.Kernel32]::FreeConsole()                                | Out-Null
    [Win32.Kernel32]::AttachConsole([uint32]$Process.Id)           | Out-Null
    [Win32.Kernel32]::SetConsoleCtrlHandler([IntPtr]::Zero, $true) | Out-Null
    [Win32.Kernel32]::GenerateConsoleCtrlEvent(0, 0)               | Out-Null
    Start-Sleep -Milliseconds 800
    [Win32.Kernel32]::FreeConsole()                                | Out-Null
    [Win32.Kernel32]::AttachConsole(0xFFFFFFFF)                    | Out-Null
    [Win32.Kernel32]::SetConsoleCtrlHandler([IntPtr]::Zero, $false)| Out-Null
}

$entities = Get-Content $ListFile | Where-Object { $_.Trim() -ne "" }
$total    = $entities.Count
$i        = 0
$start    = Get-Date

$interrupted = $false

try {
    foreach ($raw in $entities) {

        $i++
        $id = $raw.Trim()
        $currentProc = $null

        try {
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

            $line = $null
            while ($queue.TryDequeue([ref]$line)) {
                Write-Host "  $line"
            }

            Write-Host "EXIT CODE: $($proc.ExitCode)" -ForegroundColor Yellow
            if ($proc.ExitCode -ne 0) {
                Write-Host "FAILED: $id (exit $($proc.ExitCode))" -ForegroundColor Red
            }
        }
        catch {
            if ($_ -is [System.Management.Automation.PipelineStoppedException]) {
                $interrupted = $true
                Write-Host "`nInterruption — arrêt de Python ($id)..." -ForegroundColor Yellow
            } else {
                Write-Host "ERREUR PS sur $id : $_" -ForegroundColor Red
            }
            if ($null -ne $currentProc -and -not $currentProc.HasExited) {
                Send-CtrlC -Process $currentProc
                if (-not $currentProc.WaitForExit(10000)) {
                    Write-Host "Python ne répond pas après 10s — kill forcé." -ForegroundColor Red
                    $currentProc.Kill()
                } else {
                    Write-Host "Python s'est arrêté proprement (exit $($currentProc.ExitCode))." -ForegroundColor Cyan
                }
            }
        }
        finally {
            if ($null -ne $currentProc) {
                Get-EventSubscriber |
                    Where-Object { $_.SourceObject -eq $currentProc } |
                    Unregister-Event -Force
                $currentProc = $null
            }
        }

        if ($interrupted) { break }
    }
}
finally {
    Write-Progress -Activity "Telegram entity analysis" -Completed
    if ($interrupted) {
        Write-Host "Boucle arrêtée par l'utilisateur." -ForegroundColor Yellow
    }
}
