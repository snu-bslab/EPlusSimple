
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from multiprocessing import Pool

# third-party modules
import pandas as pd
from flask import Flask, render_template, request
from werkzeug.datastructures import FileStorage

# local modules
from epsimple import run_grexcel
from epsimple.debug import debug_excel, report_result, ReportCode
from reb.preprocess import process_excel_file
from reb import run_rebexcel

# ==============================================================================
# 2. Flask 앱 및 환경 설정
# ==============================================================================

# 업로드 폴더를 현재 파일 위치 기준으로 'uploads' 폴더로 지정
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
# 업로드 폴더가 없으면 생성
UPLOAD_FOLDER.mkdir(exist_ok=True)

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
        try:
            # 1. 사용자 입력 및 파일 가져오기
            file_before = request.files.get("file_before")
            file_after  = request.files.get("file_after")
            file_afterN = request.files.get("file_afterN")
            
            if not file_before or not file_before.filename:
                return render_template("run.html", result={"err": "'리모델링 전' 파일이 선택되지 않았습니다."})
            
            all_files = [file_before, file_after, file_afterN]
            
            # 2. 모든 원본 파일 임시 저장
            for file_obj in all_files:
                if file_obj.filename:
                    filepath = UPLOAD_FOLDER / file_obj.filename
                    file_obj.save(filepath)
                    file_obj.seek(0)
                    saved_filepaths[file_obj.filename] = filepath
            
            # 3. [수정] 전처리 옵션에 따라 디버깅 및 실행할 '대상 파일' 결정
            target_filepaths: Dict[str, Path] = {}
            for filename, original_path in saved_filepaths.items():
                # 전처리를 실행하고 생성된 새 파일의 경로를 저장
                preprocessed_path_str = process_excel_file(str(original_path), verbose=False)
                preprocessed_path = Path(preprocessed_path_str)
                target_filepaths[filename] = preprocessed_path
                preprocessed_filepaths.append(preprocessed_path) # 정리 목록에 추가

            # 4. [수정] 대상 파일(전처리됐거나 원본)에 대해 디버깅 실행
            debug_reports, has_severe_error, _ = _run_debugging_phase(target_filepaths)

            # 6. 분기: SEVERE 오류 여부에 따라 시뮬레이션 실행 또는 중단
            if has_severe_error:
                result = {
                    "err": "심각한 오류가 발견되어 시뮬레이션을 취소했습니다. 아래 보고서를 확인해주세요.",
                    "debug_reports": debug_reports,
                }
            else:
                # SEVERE 오류가 없을 경우 시뮬레이션 실행 (디버깅을 통과한 대상 파일 사용)
                sim_data = _run_simulation_phase(
                    target_filepaths, # [수정]
                    file_before.filename,
                    file_after.filename ,
                    file_afterN.filename,
                )
                
                result = {
                    "debug_reports": [
                        report for report in debug_reports if report.get("warning_html")
                    ],
                    "sim_data": sim_data
                }

        finally:
            # 7. [수정] 모든 임시 파일(원본 + 전처리된 파일) 정리
            all_files_to_delete = list(saved_filepaths.values()) + preprocessed_filepaths
            deleted_count = 0
            for path in all_files_to_delete:
                if path.exists():
                    path.unlink()
                    deleted_count += 1
                    
    return render_template("index.html", result=result)


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

def _execute_rebexcel_wrapper(filepath: Path) -> Any:
    """
    최상위 수준에 정의되어야 multiprocessing에서 피클링이 가능합니다.
    """
    # run_rebexcel의 반환값 중 첫 번째(result 객체)만 사용
    result, _ = run_rebexcel(str(filepath), save_grr=False, save_idf=False, preprocess=False)
    return result

def _run_simulation_phase(
    filepaths: Dict[str, Path],
    file_before_name: str,
    file_after_name: str,
    file_afterN_name: str,
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
    unique_paths = [filepaths[name] for name in unique_names]

    # 2. 병렬 실행 (최대 3코어 고정)
    num_cores = min(len(unique_paths), 3)
    with Pool(processes=num_cores) as pool:
        executed_results = pool.map(_execute_rebexcel_wrapper, unique_paths)

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