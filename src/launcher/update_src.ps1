# v-070 수정사항: GitHub REB 브랜치의 src 로 런처 코드를 바꾼다 (venv, runtime, 결과, 보고서자료는 그대로)
#   업데이트.bat 이 실행한다. -Zip 을 주면 내려받지 않고 그 파일을 쓴다 (시험용)
param(
    [string]$Root = (Get-Location).Path,
    [string]$Zip  = ""
)

$ErrorActionPreference = "Stop"
$Url  = "https://github.com/snu-bslab/EPlusSimple/archive/refs/heads/REB.zip"
$Work = Join-Path $env:TEMP "reb_update"

# git 으로 받은 폴더면 git pull
if (Test-Path (Join-Path $Root ".git")) {
    git -C $Root pull --ff-only origin REB
    exit $LASTEXITCODE
}

if (Test-Path $Work) { Remove-Item $Work -Recurse -Force }
New-Item -ItemType Directory $Work | Out-Null
if (-not $Zip) {
    Write-Host "GitHub 에서 최신 코드 받는 중"
    $Zip = Join-Path $Work "REB.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
}
Expand-Archive -Path $Zip -DestinationPath $Work
$NewSrc = Join-Path (Get-ChildItem $Work -Directory | Select-Object -First 1).FullName "src"

# 받은 코드가 이 런처 셸과 맞는지 확인
foreach ($name in "epsimple", "idragon", "reb", "launcher") {
    if (-not (Test-Path (Join-Path $NewSrc $name))) { throw "받은 코드에 src\$name 이 없습니다" }
}
$Found = Select-String -Path (Join-Path $NewSrc "launcher\config.py") -Pattern 'REQUIRED_PACK\s*=\s*(\d+)'
if (-not $Found) { throw "받은 코드에 REQUIRED_PACK 이 없습니다" }
$Need = [int]$Found.Matches[0].Groups[1].Value
$PackFile = Join-Path $Root "runtime\pack_version.txt"
$Have = 1
if (Test-Path $PackFile) { $Have = [int](Get-Content $PackFile -TotalCount 1) }
if ($Have -lt $Need) {
    Write-Host "새 코드는 런처 셸 $Need 버전이 필요합니다 (지금 $Have). 런처 폴더를 새로 받으세요. 코드는 바꾸지 않았습니다."
    Remove-Item $Work -Recurse -Force
    exit 1
}

# 지금 코드는 src_이전 으로 남기고 바꾼다
$Src = Join-Path $Root "src"
$Old = Join-Path $Root "src_이전"
if (Test-Path $Old) { Remove-Item $Old -Recurse -Force }
if (Test-Path $Src) { Rename-Item $Src "src_이전" }
Copy-Item $NewSrc $Src -Recurse
New-Item -ItemType Directory (Join-Path $Src "launcher\uploads") -Force | Out-Null
Remove-Item $Work -Recurse -Force
Write-Host "업데이트 완료. 이전 코드는 src_이전 폴더에 있습니다."
