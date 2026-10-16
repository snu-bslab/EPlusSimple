
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
import os
import re
# third-party modules

import traceback
from datetime import datetime
# local modules
from reb import run_rebexcel
from reb.core import rebexcel_to_idf_and_grm
from epsimple.core.model import EnergyPlusError


# setting
working_dir = r"Z:\01 진행과제\(부동산원) GR정성평가\31 코드\run_REB_excel"

input_excel_dir = os.path.join(working_dir,"input_excel")
result_grr_dir  = os.path.join(working_dir, "result_grr")
result_idf_dir  = os.path.join(working_dir, "result_idf")
err_idf_dir     = os.path.join(working_dir, "err_idf")

error_log_path = os.path.join(working_dir, "error_log.txt")
# main

def leading_number(filename: str) -> int:
    match = re.match(r"(\d+)", filename)
    return int(match.group(1)) if match else float("inf")

filelist = sorted(
    [
        file
        for file in os.listdir(input_excel_dir)
        if not file.endswith("preprocess.xlsx")
    ],
    key=leading_number
)

def write_error_log(
    filename: str,
    error: Exception,
    error_type: str,
) -> None:
    """문제가 발생한 Excel 파일과 오류 상세 내용을 로그에 기록한다."""

    with open(error_log_path, "a", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write(f"발생 시각   : {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        f.write(f"Excel 파일 : {filename}\n")
        f.write(f"오류 구분   : {error_type}\n")
        f.write(f"오류 내용   : {error}\n")
        f.write("상세 오류:\n")
        f.write(traceback.format_exc())
        f.write("\n")
# filelist = [file for file in os.listdir(input_excel_dir) if not file.endswith("preprocess.xlsx")]
if __name__ == "__main__":
    
    for file in filelist:
        excel_path = os.path.join(input_excel_dir, file)
        workingnote_path = os.path.join(result_grr_dir, file.replace(r".xlsx",r".working"))
        grr_path    = os.path.join(result_grr_dir, file.replace(r".xlsx",r".grr"))
        idf_path    = os.path.join(result_idf_dir, file.replace(r".xlsx",r".idf"))
        erridf_path = os.path.join(err_idf_dir, file.replace(r".xlsx",r".idf"))
        
        if os.path.exists(grr_path) or os.path.exists(workingnote_path) or os.path.exists(erridf_path):
            continue
        
        print(f"도전: {file}")
        with open(workingnote_path, "w") as f:
            f.write("")
            
        try:    
            grr, idf = run_rebexcel(os.path.join(input_excel_dir,file), grr_path, idf_path)
            
        except EnergyPlusError as error:
            print(f"!!!!!!!!!!!!!!!EP에러로 실패: {file}")
            idf, grm = rebexcel_to_idf_and_grm(os.path.join(input_excel_dir,file))
            idf.write(erridf_path)
            write_error_log(
                filename=file,
                error=error,
                error_type="EnergyPlusError",
            )
            try:
                idf, grm = rebexcel_to_idf_and_grm(excel_path)
                idf.write(erridf_path)

                print(f"오류 IDF 저장: {erridf_path}")

            except Exception as conversion_error:
                print(f"오류 IDF 생성도 실패: {file}")
                print(f"오류 내용: {conversion_error}")

                write_error_log(
                    filename=file,
                    error=conversion_error,
                    error_type="Error while generating failed IDF",
                )

            # 다음 Excel로 이동
            continue
        except Exception as error:
                # EnergyPlusError 이외의 모든 오류
                print(f"일반 오류로 실패: {file}")
                print(f"오류 종류: {type(error).__name__}")
                print(f"오류 내용: {error}")

                write_error_log(
                    filename=file,
                    error=error,
                    error_type=type(error).__name__,
                )

                # 다음 Excel로 이동
                continue

            
        finally:
            os.remove(workingnote_path)
            

