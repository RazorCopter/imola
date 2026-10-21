param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "status", "psql")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"
$DataDirectory = if ($env:PGDATA) { $env:PGDATA } else { "C:\dev\pgdata" }
$Port = if ($env:PGPORT) { $env:PGPORT } else { "5433" }
$Database = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "supplier_ledger" }
$User = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "supplier_ledger" }

function Resolve-PostgresCommand([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $candidates = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\$Name.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    if ($candidates) { return $candidates[0].FullName }

    $portable = "C:\dev\pgsql\bin\$Name.exe"
    if (Test-Path $portable) { return $portable }

    throw "$Name non trovato. Installare PostgreSQL 16 o impostare il PATH."
}

$pgCtl = Resolve-PostgresCommand "pg_ctl"

switch ($Action) {
    "start" {
        if (-not (Test-Path $DataDirectory)) { throw "PGDATA non trovato: $DataDirectory" }
        & $pgCtl -D $DataDirectory -o "-p $Port" -w start
        exit $LASTEXITCODE
    }
    "stop" {
        if (-not (Test-Path $DataDirectory)) { throw "PGDATA non trovato: $DataDirectory" }
        & $pgCtl -D $DataDirectory -m fast -w stop
        exit $LASTEXITCODE
    }
    "status" {
        if (-not (Test-Path $DataDirectory)) {
            Write-Output "PGDATA non trovato: $DataDirectory"
            exit 3
        }
        & $pgCtl -D $DataDirectory status
        exit $LASTEXITCODE
    }
    "psql" {
        $psql = Resolve-PostgresCommand "psql"
        & $psql -h 127.0.0.1 -p $Port -U $User -d $Database
        exit $LASTEXITCODE
    }
}
