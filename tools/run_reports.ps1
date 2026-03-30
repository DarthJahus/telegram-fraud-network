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

$entities = Get-Content $ListFile | Where-Object { $_.Trim() -ne "" }
$total    = $entities.Count
$i        = 0
$start    = Get-Date

foreach ($raw in $entities) {

    $i++
    $id = $raw.Trim()

    $elapsed  = (Get-Date) - $start
    $rate     = $i / [math]::Max($elapsed.TotalSeconds, 1)
    $eta      = (Get-Date).AddSeconds(($total - $i) / $rate)
    $etaStr = if ($eta.Date -ne (Get-Date).Date) {
        $eta.ToString('dd/MM HH:mm')
    } else {
        $eta.ToString('HH:mm')
    }
    $rateMin  = "{0:N1}" -f ($rate * 60)
    $percent  = [int](($i / $total) * 100)

    Write-Host ("=" * 60)
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Entity: $id"
    Write-Host ("=" * 60)

    $queue = [System.Collections.Concurrent.ConcurrentQueue[string]]::new()

    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName               = "python"
    $psi.WorkingDirectory       = $PSScriptRoot
    $psi.Arguments              = "-u -m telegram_checker.main --md --no --llm-url `"http://10.0.0.11:1234/v1/chat/completions`" --llm-model `"openai/gpt-oss-20b`" --user `"$User`" --out-file `"reports/$id.log`" --report `"$id`" --update-file `"$UpdateFolder/tg_$id.md`""
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

    $proc.Start()           | Out-Null
    $proc.BeginOutputReadLine()
    $proc.BeginErrorReadLine()

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
}

Write-Progress -Activity "Telegram entity analysis" -Completed
