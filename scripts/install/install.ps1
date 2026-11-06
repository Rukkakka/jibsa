# jibsa 설치 스크립트 (Windows PowerShell 5.1 이상)
#
#   irm https://raw.githubusercontent.com/Rukkakka/jibsa/main/scripts/install/install.ps1 | iex
#
# 하는 일 (다시 실행하면 jibsa 를 최신 버전으로 올린다)
#   1. uv 가 없으면 설치한다 (https://docs.astral.sh/uv/)
#   2. uv 로 jibsa 를 설치하거나 최신 버전으로 올린다
#   3. jibsa 폴더를 사용자 PATH 에 등록하고, 지금 창에도 바로 넣는다
#   4. PYTHONUTF8=1 을 설정한다 (에이전트가 부를 때 한글이 깨지지 않게)
#   5. Codex·Claude Code 를 쓰고 있으면 지침 파일에 jibsa 사용 규칙 한 줄을 넣는다
#
# main 브랜치의 이 파일을 사용자가 바로 받아 실행하므로, 머지하는 즉시 모든 사용자에게 적용된다.
# irm | iex 는 사용자의 창 안에서 돌기 때문에 exit 를 쓰지 않고(창이 닫힌다), 설정도 블록 밖으로 새지 않게 한다.

& {
    $Issues = 'https://github.com/Rukkakka/jibsa/issues'
    $AgentLine = '집을 찾을 때는 jibsa CLI 를 쓴다. 처음 쓰기 전에 `jibsa guide` 를 실행해 읽고 그 규칙을 따른다.'

    function Write-Step([string]$Text) { Write-Host "`n==> $Text" -ForegroundColor Cyan }

    function Find-Uv {
        $cmd = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Path }
        foreach ($dir in @($env:UV_INSTALL_DIR, $env:XDG_BIN_HOME, (Join-Path $HOME '.local\bin'), (Join-Path $HOME '.cargo\bin'))) {
            if ($dir -and (Test-Path (Join-Path $dir 'uv.exe'))) { return (Join-Path $dir 'uv.exe') }
        }
        return $null
    }

    # 한국어 Windows 의 PowerShell 5.1 은 프로그램 출력을 cp949 로 읽어, UTF-8 로 나오는 한글 경로(사용자 폴더)가 깨진다
    function Invoke-Utf8([scriptblock]$Block) {
        $previous = $null
        try {
            $previous = [Console]::OutputEncoding
            [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
        } catch {
            $previous = $null  # 콘솔이 없는 창(ISE 등)은 인코딩을 못 바꾼다. 그대로 진행한다
        }
        try {
            & $Block
        } finally {
            if ($previous) { try { [Console]::OutputEncoding = $previous } catch { } }
        }
    }

    function Test-SameDir([string]$Left, [string]$Right) {
        $l = [Environment]::ExpandEnvironmentVariables($Left).TrimEnd('\')
        $r = [Environment]::ExpandEnvironmentVariables($Right).TrimEnd('\')
        return $l -ieq $r
    }

    # 사용자 PATH 에 폴더를 넣는다. %USERPROFILE% 같은 변수가 든 기존 항목이 풀리지 않게 레지스트리 값을 그대로 다룬다
    function Add-UserPath([string]$Dir) {
        $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
        try {
            $raw = [string]$key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
            $entries = @($raw -split ';' | Where-Object { $_ })
            foreach ($entry in $entries) {
                if (Test-SameDir $entry $Dir) { return $false }
            }
            $newPath = (@($Dir) + $entries) -join ';'
            $key.SetValue('Path', $newPath, [Microsoft.Win32.RegistryValueKind]::ExpandString)
            return $true
        } finally {
            $key.Close()
        }
    }

    function Add-AgentLine([string]$Name, [string]$Dir, [string]$FileName) {
        if (-not (Test-Path $Dir)) { return }
        $path = Join-Path $Dir $FileName
        $utf8 = New-Object System.Text.UTF8Encoding $false
        $text = ''
        if (Test-Path $path) { $text = [IO.File]::ReadAllText($path, $utf8) }
        if ($text.Contains('jibsa guide')) {
            Write-Host "$Name 지침 파일에 이미 jibsa 규칙이 있다: $path"
            return
        }
        $prefix = ''
        if ($text.Length -gt 0) {
            $prefix = "`r`n"
            if (-not $text.EndsWith("`n")) { $prefix = "`r`n`r`n" }
        }
        [IO.File]::AppendAllText($path, "$prefix$AgentLine`r`n", $utf8)
        Write-Host "$Name 지침 파일에 jibsa 규칙을 넣었다: $path"
    }

    try {
        Write-Step '1/5 uv 확인'
        $uv = Find-Uv
        if ($uv) {
            Write-Host "uv 가 이미 있다: $uv"
        } else {
            Write-Host 'uv 가 없어 설치한다'
            & powershell.exe -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
            $uv = Find-Uv
            if (-not $uv) { throw 'uv 설치가 끝나지 않았다. 위의 uv 설치 메시지를 확인한다' }
        }

        Write-Step '2/5 jibsa 설치 (이미 있으면 최신 버전으로 올린다)'
        & $uv tool install --upgrade jibsa
        if ($LASTEXITCODE -ne 0) {
            throw 'jibsa 를 설치하지 못했다. jibsa 를 쓰고 있는 창(에이전트 포함)이 있으면 닫고 다시 실행한다'
        }

        Write-Step '3/5 PATH 등록'
        $bin = Invoke-Utf8 { & $uv tool dir --bin } | Select-Object -Last 1
        if ($bin) { $bin = $bin.Trim() }
        if (-not $bin -or -not (Test-Path (Join-Path $bin 'jibsa.exe'))) { $bin = Join-Path $HOME '.local\bin' }
        $jibsa = Join-Path $bin 'jibsa.exe'
        if (-not (Test-Path $jibsa)) { throw "jibsa.exe 를 찾지 못했다: $jibsa" }
        if (Add-UserPath $bin) {
            Write-Host "사용자 PATH 에 넣었다: $bin"
        } else {
            Write-Host "사용자 PATH 에 이미 있다: $bin"
        }
        if (-not (@($env:Path -split ';') | Where-Object { $_ -and (Test-SameDir $_ $bin) })) {
            $env:Path = "$bin;$env:Path"
        }

        Write-Step '4/5 한글 출력 설정 (PYTHONUTF8=1)'
        # .NET 으로 사용자 환경 변수를 바꾸면 Windows 에 변경을 알려, 새로 여는 창이 위 PATH 도 함께 받는다
        [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'User')
        $env:PYTHONUTF8 = '1'
        Write-Host '설정했다'

        Write-Step '5/5 에이전트 지침'
        $codexHome = $env:CODEX_HOME
        if (-not $codexHome) { $codexHome = Join-Path $HOME '.codex' }
        $claudeHome = Join-Path $HOME '.claude'
        if (-not (Test-Path $codexHome) -and -not (Test-Path $claudeHome)) {
            Write-Host 'Codex·Claude Code 설정 폴더가 없어 건너뛴다. 다른 에이전트는 지침 파일에 아래 한 줄을 적는다'
            Write-Host "  $AgentLine"
        }
        Add-AgentLine 'Codex' $codexHome 'AGENTS.md'
        Add-AgentLine 'Claude Code' $claudeHome 'CLAUDE.md'

        Write-Step '설치 확인'
        & $jibsa --version
        if ($LASTEXITCODE -ne 0) { throw 'jibsa --version 이 실패했다' }

        Write-Host ''
        Write-Host '설치를 마쳤다. 이 창에서 바로 jibsa 를 쓸 수 있다.' -ForegroundColor Green
        Write-Host '- 해 보기: jibsa zigbang search listings room 강남역 --trade 월세 --limit 3'
        Write-Host '- 설치 전에 열려 있던 다른 창은 PATH 가 예전 그대로라 jibsa 를 못 찾는다. 닫고 새로 연다'
        Write-Host '- 에이전트(Codex 등)도 이 창이나 새로 연 창에서 켠다. 예전 창에서 켜면 jibsa 를 못 찾는다'
        Write-Host '- Codex 가 jibsa 를 못 찾거나 조회가 막히면 Codex 안에서 /permissions 로 Full Access 를 고른다 (기본 샌드박스가 사용자 폴더와 인터넷을 막는다)'
    } catch {
        Write-Host ''
        Write-Host "설치하지 못했다: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "해결되지 않으면 이 화면을 캡처해 이슈로 알려 준다: $Issues"
    }
}
