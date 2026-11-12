"""
v-070 수정사항: 부동산원 전달용 REB 런처 폴더를 만든다

  venv\\python.exe scripts\\local-SNU\\make_reb_launcher.py [출력폴더]

만드는 것 (기본 dist\\REB_Launcher_V0.7.0)
  REB_Launcher.bat          더블클릭하면 브라우저에 런처가 열린다
  사용법.txt
  venv\\                    Python (flask, openpyxl, matplotlib 포함)
  src\\                     epsimple, idragon, reb, launcher
  runtime\\EnergyPlusV24-2-0 (배포에 필요 없는 파일은 뺀다)
  runtime\\Weather\\TMY, AMY
  결과\\                    실행할 때마다 보고서, grr, idf, 기상파일이 쌓인다
  보고서자료\\              comment.csv 를 넣어 두면 매번 올리지 않아도 된다

기상청 API 키, comment 는 넣지 않는다.
"""

import os
import sys
import glob
import shutil

ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VERSION = "0.7.0"
OUT     = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist", f"REB_Launcher_V{VERSION}")
PRUNE   = os.path.join(ROOT, "scripts", "release", "energyplus-release-prune.txt")
SKIP    = shutil.ignore_patterns("__pycache__", "*.pyc", "uploads", "~$*")

BAT = r"""@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ==============================================================
echo  REB GR launcher (EPlusSimple V{version})
echo  Browser : http://127.0.0.1:5000
echo  To stop : close this window
echo ==============================================================
start "" /min cmd /c "ping 127.0.0.1 -n 4 > nul & start http://127.0.0.1:5000"
.\venv\python.exe -m launcher
echo.
echo The launcher has stopped. If this was unexpected, check the messages above.
pause
"""

GUIDE = """GR 정성평가 REB 런처 (EPlusSimple V{version})

1. REB_Launcher.bat 을 더블클릭합니다. 검은 창이 뜨고 브라우저에 런처가 열립니다.
   (브라우저가 안 열리면 주소창에 http://127.0.0.1:5000 입력)
2. GR이전, GR이후, N년차 엑셀을 고르고 [시뮬레이션] 을 누릅니다.
   파일명 형식: GR준공연도_파일번호_PK코드_건물명_시점.xlsx  (예: 2020_191_30170-30467_OO보건소_GR이후.xlsx)
3. 화면 순서
   - 파일 인식 결과 : 파일명의 PK, 주소, 사용할 기상데이터(연도, 기상청 지점). [오류] 가 있으면 실행하지 않습니다.
   - 디버그 리포트  : 엑셀 입력 오류(SEVERE)와 경고(WARNING)
   - 실행 오류      : 실행 중 문제가 생기면 오류 내용. '자세한 오류 내용' 을 복사해 전달해 주세요.
   - 결과 파일      : 개별 보고서(xlsx, pdf) 다운로드. grr, idf, 사용한 기상파일(epw)은 [폴더 열기] 로 볼 수 있습니다.
4. 결과는 '결과' 폴더에 '번호_건물명_실행시각' 폴더로 쌓입니다.

개별 보고서
  - 주요 변화, 요소기술, 운영특성 표는 입력 엑셀(GR이전, GR이후, N년차)에서 만듭니다.
    엑셀에 없는 현장조사 항목(공사내역 일치 여부, 보육 시간대별 인원, 외근 등)은 (미기입)으로 나옵니다.
  - comment.csv 를 런처에서 올리거나 '보고서자료' 폴더에 넣어 두면 조사자 의견과 만족도를 채웁니다.
    없으면 (미기입).
  - PDF 는 Microsoft Excel 이 설치되어 있어야 만들어집니다. 없으면 엑셀 보고서만 만듭니다.
  - 양식: src\\reb\\data\\report_template.xlsx

기상데이터
  - 건물정보 탭의 기상데이터옵션이 실제기상(AMY)이면 runtime\\Weather\\AMY 의 '지점번호_연도.epw' 를 씁니다.
  - 그 파일이 없으면 기상청 API허브 자료로 새로 만듭니다. 이때만 런처의 '기상청 API 키' 칸에 키를 넣으세요.
    키는 파일에 저장하지 않고 런처 창을 닫으면 사라집니다. (인터넷 연결 필요)
  - 새로 만든 파일은 runtime\\Weather\\AMY 에 남아 다음부터는 키 없이 씁니다.
"""


def copy_tree(src, dst):
    print("복사:", os.path.relpath(src, ROOT))
    shutil.copytree(src, dst, ignore=SKIP)


def prune_energyplus(energyplus_dir):
    """release.ps1 과 같은 목록(prune ...)으로 EnergyPlus 의 필요 없는 파일을 지운다"""
    with open(PRUNE, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
    for line in lines:
        command, _, pattern = line.partition(" ")
        if command == "require":
            continue
        if command != "prune":
            pattern = line
        for path in glob.glob(os.path.join(energyplus_dir, pattern.strip().replace("/", os.sep).rstrip(os.sep))):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    for line in lines:
        command, _, name = line.partition(" ")
        if command == "require" and not os.path.exists(os.path.join(energyplus_dir, name.strip())):
            raise FileNotFoundError(f"EnergyPlus 필수 파일이 없습니다: {name}")


def main():
    if os.path.exists(OUT):
        if not os.path.abspath(OUT).startswith(os.path.join(ROOT, "dist")):
            raise SystemExit(f"{OUT} 이 이미 있습니다. dist 밖의 폴더는 지우지 않으니 다른 이름을 주세요.")
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    copy_tree(os.path.join(ROOT, "venv"), os.path.join(OUT, "venv"))
    for name in ["epsimple", "idragon", "reb", "launcher"]:
        copy_tree(os.path.join(ROOT, "src", name), os.path.join(OUT, "src", name))
    copy_tree(os.path.join(ROOT, "runtime", "EnergyPlusV24-2-0"), os.path.join(OUT, "runtime", "EnergyPlusV24-2-0"))
    prune_energyplus(os.path.join(OUT, "runtime", "EnergyPlusV24-2-0"))
    for name in ["TMY", "AMY"]:
        copy_tree(os.path.join(ROOT, "runtime", "Weather", name), os.path.join(OUT, "runtime", "Weather", name))

    os.makedirs(os.path.join(OUT, "결과"))
    os.makedirs(os.path.join(OUT, "보고서자료"))
    os.makedirs(os.path.join(OUT, "src", "launcher", "uploads"))
    with open(os.path.join(OUT, "REB_Launcher.bat"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(BAT.format(version=VERSION))
    with open(os.path.join(OUT, "사용법.txt"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(GUIDE.format(version=VERSION))

    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, files in os.walk(OUT) for f in files)
    print(f"완료: {OUT} ({size / 1024**3:.2f} GB)")


if __name__ == "__main__":
    main()
