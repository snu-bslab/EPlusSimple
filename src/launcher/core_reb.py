
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
import os # v-070 수정사항
import shutil # v-070 수정사항
import datetime # v-070 수정사항
import traceback # v-070 수정사항
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from multiprocessing import Pool

# third-party modules
import pandas as pd
from flask import Flask, render_template, request, send_from_directory, abort # v-070 수정사항
from werkzeug.datastructures import FileStorage

# local modules
from epsimple import run_grexcel
from epsimple.debug import debug_excel, report_result, ReportCode
from reb import run_rebexcel
from reb.filename import read_filename # v-070 수정사항
from reb.weather import choose_pk, check_pk_address, sigungu_from_pk, describe_weatherdata, get_weatherdata # v-070 수정사항
from reb.report_excel import build_excel_report # v-070 수정사항

# ==============================================================================
# 2. Flask 앱 및 환경 설정
# ==============================================================================

# 업로드 폴더를 현재 파일 위치 기준으로 'uploads' 폴더로 지정
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
# 업로드 폴더가 없으면 생성
UPLOAD_FOLDER.mkdir(exist_ok=True)

# v-070 수정사항: 결과(보고서, grr, idf, 기상파일)는 배포 폴더의 '결과', 보고서 자료는 '보고서자료'
ROOT_DIR    = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT_DIR / "결과"
REPORT_DATA = ROOT_DIR / "보고서자료"

# Flask 앱 인스턴스 생성 및 설정
app = Flask(__name__, template_folder="./templates")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["JSON_AS_ASCII"] = False # 한글 깨짐 방지


# ==============================================================================
# 3. 공용 헬퍼 함수
# ==============================================================================

def handle_file_processing(
    file: Optional[FileStorage],
    handler_func: callable,
    failure_response: Dict[str, Any],
    **kwargs: Any,
) -> Any:
    """
    단일 파일 업로드를 안전하게 처리하고 지정된 핸들러 함수를 실행합니다.

    파일을 임시 폴더에 저장하고 핸들러 함수를 호출한 뒤, 성공/실패 여부와 관계없이
    파일을 삭제하여 서버에 불필요한 파일이 남지 않도록 합니다.

    Args:
        file: Flask request에서 받은 파일 스토리지 객체.
        handler_func: 저장된 파일 경로를 인자로 받아 처리할 함수(예: check_grexcel).
        failure_response: 파일이 없거나 이름이 없을 경우 반환할 딕셔너리.
        **kwargs: handler_func에 전달할 추가 인자.

    Returns:
        handler_func의 실행 결과 또는 실패 응답 딕셔너리.
    """
    if not file or not file.filename:
        return failure_response

    # 파일 경로를 pathlib.Path 객체로 관리
    filepath = UPLOAD_FOLDER / file.filename
    try:
        file.save(filepath)
        result = handler_func(str(filepath), **kwargs)
    finally:
        # 파일 처리 후 반드시 삭제
        if filepath.exists():
            filepath.unlink()
    return result


# ==============================================================================
# 4. 라우트 (웹페이지 기능)
# ==============================================================================

def getpost() -> str:
    """
    '비교 분석' 페이지를 렌더링하고, POST 요청 시 다음 로직에 따라 시뮬레이션을 실행합니다.

    1. **파일 저장**: '리모델링 전' 파일과 '리모델링 후' 파일(들)을 임시 저장합니다.
    2. **[수정] 선행 전처리**: '전처리' 옵션이 선택된 경우, 저장된 모든 파일에 대해 전처리를 먼저 수행합니다.
    3. **대상 파일 디버깅**: 전처리된 파일(또는 원본 파일)에 대해 `debug_excel`을 실행하여 오류를 확인합니다.
    4. **오류 분기**:
        - 'SEVERE' 오류가 발견되면, 시뮬레이션을 중단하고 오류 보고서만 표시합니다.
        - 오류가 없으면, 경고 보고서와 함께 시뮬레이션 결과를 모두 표시합니다.
    5. **파일 정리**: 작업 완료 후 원본 및 전처리된 모든 임시 파일을 삭제합니다.
    """
    result: Optional[Dict[str, Any]] = None
    # 임시 저장된 원본 파일 경로들을 관리 (key: 원본 파일명, value: Path 객체)
    saved_filepaths: Dict[str, Path] = {}
    # 전처리 후 생성된 파일 경로들을 관리 (정리용)
    preprocessed_filepaths: List[Path] = []

    if request.method == "POST":
        report_inputs: List[Path] = [] # v-070 수정사항
        file_table, debug_reports, out_dir = None, [], None # v-070 수정사항
        try:
            # 1. 사용자 입력 및 파일 가져오기
            file_before = request.files.get("file_before")
            file_after  = request.files.get("file_after")
            file_afterN = request.files.get("file_afterN")

            if not file_before or not file_before.filename:
                return render_template("index.html", result={"err": "'리모델링 전' 파일이 선택되지 않았습니다."}) # v-070 수정사항

            # v-070 수정사항: 기상청 API 키는 파일에 저장하지 않고 런처가 켜져 있는 동안만 쓴다
            kma_key = request.form.get("kma_key", "").strip()
            if kma_key:
                os.environ["KMA_API_KEY"] = kma_key

            all_files = [file_before, file_after, file_afterN]

            # 2. 모든 원본 파일 임시 저장
            for file_obj in all_files:
                if file_obj and file_obj.filename: # v-070 수정사항
                    filepath = UPLOAD_FOLDER / file_obj.filename
                    file_obj.save(filepath)
                    file_obj.seek(0)
                    saved_filepaths[file_obj.filename] = filepath

            # v-070 수정사항: 보고서 자료 (올린 파일이 없으면 보고서자료 폴더의 파일)
            comment = _report_input(request.files.get("comment"), "comment.csv", report_inputs)
            
            # 3. [수정] 전처리 옵션에 따라 디버깅 및 실행할 '대상 파일' 결정
            # v-070 수정사항: 원본을 그대로 쓴다. 전처리 파일은 실 탭의 용도프로필이 주용도로 바뀌어 있어
            # 용도프로필 탭이 시뮬레이션에 반영되지 않으므로, 전처리는 run_rebexcel(preprocess=True) 이 한다
            target_filepaths: Dict[str, Path] = dict(saved_filepaths)

            # v-070 수정사항: 파일명(PK)과 건물정보 탭으로 PK, 주소, 기상데이터를 먼저 확인
            slot_files = [
                ("GR이전", file_before.filename),
                ("GR이후", file_after.filename  if file_after  else ""),
                ("N년차" , file_afterN.filename if file_afterN else ""),
            ]
            file_table, has_file_error = _run_filecheck_phase(slot_files, target_filepaths)
            if has_file_error:
                result = {
                    "err": "파일 확인에서 오류가 나서 시뮬레이션을 취소했습니다. 아래 표의 '확인' 칸을 보세요.",
                    "file_table": file_table,
                }
                return render_template("index.html", result=result)

            # 4. [수정] 대상 파일(전처리됐거나 원본)에 대해 디버깅 실행
            debug_reports, has_severe_error, _ = _run_debugging_phase(target_filepaths)

            # 6. 분기: SEVERE 오류 여부에 따라 시뮬레이션 실행 또는 중단
            if has_severe_error:
                result = {
                    "err": "심각한 오류가 발견되어 시뮬레이션을 취소했습니다. 아래 보고서를 확인해주세요.",
                    "debug_reports": debug_reports,
                    "file_table": file_table, # v-070 수정사항
                }
            else:
                result = {
                    "debug_reports": [
                        report for report in debug_reports if report.get("warning_html")
                    ],
                    "file_table": file_table, # v-070 수정사항
                }

                # SEVERE 오류가 없을 경우 시뮬레이션 실행 (디버깅을 통과한 대상 파일 사용)
                out_dir = _new_output_dir(file_before.filename) # v-070 수정사항
                sim_data = _run_simulation_phase(
                    target_filepaths, # [수정]
                    file_before.filename,
                    file_after.filename  if file_after  else "", # v-070 수정사항
                    file_afterN.filename if file_afterN else "",
                    out_dir, # v-070 수정사항
                )
                result["sim_data"] = sim_data

                # v-070 수정사항: 쓴 기상파일과 개별 보고서를 결과 폴더에 모은다
                messages = []
                _copy_weatherdata(target_filepaths, out_dir)
                if request.form.get("make_report"):
                    messages = _run_report_phase(
                        target_filepaths, sim_data, out_dir, comment,
                        pdf=bool(request.form.get("make_pdf")),
                    )
                result["outputs"] = {
                    "run"     : out_dir.name,
                    "folder"  : str(out_dir),
                    "files"   : sorted(p.name for p in out_dir.iterdir() if p.suffix in (".xlsx", ".pdf")), # v-070 수정사항
                    "messages": messages,
                }

        except Exception as error: # v-070 수정사항: 실행 중 오류는 화면에 그대로 보여준다
            result = result or {
                "file_table"   : file_table,
                "debug_reports": [r for r in debug_reports if r.get("severe_html") or r.get("warning_html")],
            }
            result["run_error"] = f"실행 중 오류가 났습니다: {type(error).__name__}: {error}"
            result["traceback"] = traceback.format_exc()
            if out_dir and not any(out_dir.iterdir()):
                out_dir.rmdir()

        finally:
            # 7. [수정] 모든 임시 파일(원본 + 전처리된 파일) 정리
            all_files_to_delete = list(saved_filepaths.values()) + preprocessed_filepaths + report_inputs # v-070 수정사항
            deleted_count = 0
            for path in all_files_to_delete:
                if path.exists():
                    path.unlink()
                    deleted_count += 1
                    
    return render_template("index.html", result=result)


def _run_filecheck_phase(
    slot_files: List[Tuple[str, str]],
    filepaths: Dict[str, Path],
) -> Tuple[str, bool]:
    """
    v-070 수정사항
    파일명(GR준공연도_파일번호_PK코드_건물명_시점.xlsx)과 건물정보 탭을 읽어
    PK 시군구와 주소가 맞는지, 어떤 기상파일을 쓸지 실행 전에 표로 보여준다.
    """
    rows = []
    has_error = False

    for slot, filename in slot_files:
        if not filename:
            continue

        info     = read_filename(filename)
        building = pd.read_excel(filepaths[filename], sheet_name="건물정보", header=1).iloc[0]
        pk       = choose_pk(building.get("PK코드"), filename)
        notes    = []

        if info["시점"] is None:
            notes.append("파일명 형식이 아님 (GR준공연도_파일번호_PK코드_건물명_시점.xlsx)")
        elif info["시점"] != slot:
            notes.append(f"파일명의 시점이 {info['시점']}")

        try:
            check_pk_address(pk, building["주소"])
            weather = describe_weatherdata(building["주소"], building["기상데이터옵션"], building["기준년도"])
        except Exception as error:
            weather = "-"
            notes.append(f"[오류] {error}")
            has_error = True

        rows.append({
            "칸"        : slot,
            "파일"      : filename,
            "연도"      : info["연도"],
            "번호"      : info["번호"],
            "PK"        : pk,
            "PK 시군구" : sigungu_from_pk(pk),
            "건물명"    : info["건물명"] or building.get("건물명"),
            "주소"      : building["주소"],
            "기상데이터": weather,
            "확인"      : notes,
        })

    pks = {row["PK"] for row in rows if row["PK"]}
    if len(pks) > 1:
        for row in rows:
            row["확인"].append("파일마다 PK 가 다름")

    for row in rows:
        row["확인"] = " / ".join(row["확인"]) if row["확인"] else "OK"

    table = pd.DataFrame(rows).fillna("-")
    return table.to_html(classes="debug-table", index=False), has_error


def _run_debugging_phase(
    filepaths: Dict[str, Path]
) -> Tuple[List[Dict[str, Any]], bool, Optional[pd.DataFrame]]:
    """
    지정된 모든 파일 경로에 대해 디버깅을 수행하고 결과를 집계합니다.

    Args:
        filepaths: 파일명을 key로, 파일의 Path 객체를 value로 갖는 딕셔너리.

    Returns:
        - debug_reports (List): 각 파일의 디버그 결과를 담은 딕셔너리 리스트.
        - has_severe_error (bool): 'SEVERE' 등급의 오류가 있었는지 여부.
        - final_report_df (pd.DataFrame): 모든 보고서를 병합한 단일 데이터프레임.
    """
    debug_reports: List[Dict[str, Any]] = []
    all_report_dfs: List[pd.DataFrame] = []
    has_severe_error = False

    for filename, path in filepaths.items():
        exceptions, warnings = debug_excel(str(path), include_reb=True)
        code, report_df = report_result(exceptions, warnings)
        
        if code == ReportCode.SEVERE:
            has_severe_error = True
            
        report_data: Dict[str, Any] = {"filename": filename, "code": code.name}
        
        if not report_df.empty:
            # CSV 다운로드를 위해 원본 DataFrame에 파일명 열 추가
            report_df_with_filename = report_df.copy()
            report_df_with_filename.insert(0, "파일", filename)
            all_report_dfs.append(report_df_with_filename)
            
            # 중요도에 따라 HTML 테이블 분리
            severe_df = report_df[report_df["importance"] == "ERROR"]
            warning_df = report_df[report_df["importance"] == "WARNING"]
            
            if not severe_df.empty:
                report_data["severe_html"] = severe_df.to_html(classes="debug-table", index=False)
            if not warning_df.empty:
                report_data["warning_html"] = warning_df.to_html(classes="debug-table", index=False)

        debug_reports.append(report_data)

    final_report_df = pd.concat(all_report_dfs, ignore_index=True) if all_report_dfs else None
    
    return debug_reports, has_severe_error, final_report_df

def _execute_rebexcel_wrapper(task: Tuple[Path, Path]) -> Any:
    """
    최상위 수준에 정의되어야 multiprocessing에서 피클링이 가능합니다.
    """
    # v-070 수정사항: grr, idf 를 결과 폴더에 저장
    filepath, output_path = task
    result, _ = run_rebexcel(
        str(filepath),
        str(output_path.with_suffix(".grr")),
        str(output_path.with_suffix(".idf")),
        preprocess=True, # v-070 수정사항
    )
    return result

def _run_simulation_phase(
    filepaths: Dict[str, Path],
    file_before_name: str,
    file_after_name: str,
    file_afterN_name: str,
    out_dir: Path, # v-070 수정사항
) -> Dict[str, Any]:
    """
    [병렬화 버전] 최대 3개의 코어를 사용하여 시뮬레이션을 실행합니다.
    """
    
    # 1. 실행할 파일 이름 리스트 구성 (None 체크 및 중복 제거 전략)
    # 병렬 처리를 위해 일단 '실행해야 할 가능성이 있는' 이름들을 모읍니다.
    task_names = [file_before_name]
    if file_after_name:
        task_names.append(file_after_name)
    if file_afterN_name:
        task_names.append(file_afterN_name)

    # 실제 실행할 경로 리스트 (중복 제거를 통해 자원 낭비 방지)
    unique_names = list(dict.fromkeys(task_names)) 
    unique_tasks = [(filepaths[name], out_dir / Path(name).stem) for name in unique_names] # v-070 수정사항

    # 2. 병렬 실행 (최대 3코어 고정)
    num_cores = min(len(unique_tasks), 3)
    with Pool(processes=num_cores) as pool:
        executed_results = pool.map(_execute_rebexcel_wrapper, unique_tasks)

    # 3. 결과를 이름 기반 딕셔너리로 매핑
    result_map = dict(zip(unique_names, executed_results))

    # 4. 기존 로직에 따른 결과 할당 (후속 파일이 없을 시 이전 단계 결과 참조)
    result_before = result_map[file_before_name]
    
    if file_after_name:
        result_after = result_map[file_after_name]
    else:
        result_after = result_before

    if file_afterN_name:
        result_afterN = result_map[file_afterN_name]
    else:
        result_afterN = result_after

    return {
        "filename_before": file_before_name,
        "filename_after": file_after_name,
        "filename_afterN": file_afterN_name,
        "before": result_before.to_dict(),
        "after": result_after.to_dict(),
        "afterN": result_afterN.to_dict(),
    }

# ==============================================================================
# v-070 수정사항: 결과 폴더, 기상파일, 개별 보고서, 다운로드
# ==============================================================================

def _report_input(file: Optional[FileStorage], default_name: str, saved: List[Path]) -> Optional[str]:
    """올린 보고서 자료를 임시 저장한다. 안 올렸으면 보고서자료 폴더의 같은 이름 파일"""
    if file and file.filename:
        path = UPLOAD_FOLDER / f"보고서자료_{file.filename}"
        file.save(path)
        saved.append(path)
        return str(path)
    default = REPORT_DATA / default_name
    return str(default) if default.exists() else None


def _new_output_dir(filename: str) -> Path:
    """결과/번호_건물명_실행시각"""
    info = read_filename(filename)
    base = f"{info['번호']}_{info['건물명']}" if info["건물명"] else Path(filename).stem
    out_dir = OUTPUT_ROOT / f"{base}_{datetime.datetime.now():%y%m%d_%H%M%S}"
    out_dir.mkdir(parents=True)
    return out_dir


def _copy_weatherdata(filepaths: Dict[str, Path], out_dir: Path) -> None:
    """시뮬레이션에 쓴 epw (AMY 는 이때 이미 만들어져 있음) 를 결과 폴더에 복사"""
    for filename, path in filepaths.items():
        building = pd.read_excel(path, sheet_name="건물정보", header=1).iloc[0]
        pk = choose_pk(building.get("PK코드"), filename)
        epw = get_weatherdata(building["주소"], building["기상데이터옵션"], building["기준년도"], pk)
        target = out_dir / os.path.basename(epw)
        if not target.exists():
            shutil.copy(epw, target)


def _run_report_phase(
    filepaths: Dict[str, Path],
    sim_data: Dict[str, Any],
    out_dir: Path,
    comment: Optional[str],
    pdf: bool,
) -> List[str]:
    """개별 보고서(xlsx, pdf). 비어 있는 단계는 앞 단계 파일로 채운다"""
    before = sim_data["filename_before"]
    after  = sim_data["filename_after"] or before
    afterN = sim_data["filename_afterN"] or after
    excel_paths = {"GR이전": str(filepaths[before]), "GR이후": str(filepaths[after]), "N년차": str(filepaths[afterN])}
    grrs = {"GR이전": sim_data["before"], "GR이후": sim_data["after"], "N년차": sim_data["afterN"]}

    base = out_dir.name.rsplit("_", 2)[0]
    try:
        _, messages = build_excel_report(
            excel_paths, grrs, str(out_dir / f"{base}_보고서.xlsx"),
            comment=comment, pdf=pdf,
        )
    except Exception as error:
        messages = [f"보고서를 만들지 못했습니다: {type(error).__name__}: {error}", traceback.format_exc()]
    return messages


def _run_dir(run: str) -> Path:
    folder = (OUTPUT_ROOT / run).resolve()
    if folder.parent != OUTPUT_ROOT.resolve() or not folder.is_dir():
        abort(404)
    return folder


def download(run: str, name: str):
    return send_from_directory(_run_dir(run), name, as_attachment=True)


def open_folder(run: str):
    os.startfile(_run_dir(run))
    return ("", 204)


EXTRA_ROUTES = [
    ("/download/<run>/<path:name>", "download"   , download   ),
    ("/open/<run>"                 , "open_folder", open_folder),
]
