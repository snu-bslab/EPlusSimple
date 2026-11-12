
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
import os

# third-party modules
import pandas as pd

# local modules
from idragon import IDF
from epsimple import (
    GreenRetrofitModel ,
    GreenRetrofitResult,
)
from .preprocess import process_excel_file
from .postprocess import 용도프로필적용 # 기존 현장조사체크리스트에서 변경 (v0-7-0)
from .weather import get_weatherdata, choose_pk # v-070 수정사항

def rebexcel_to_idf_and_grm(
    input_filepath :str,
    *,
    preprocess:bool=True
    ) -> IDF:
    
    # preprocess
    if preprocess:
        processed_filepath = process_excel_file(input_filepath, verbose=False)
        target_file = processed_filepath
    else:
        processed_filepath = None
        target_file = input_filepath
    try:
        # read excel to model
        grm = GreenRetrofitModel.from_excel(target_file)
        
        # read excel to survey
        survey = 용도프로필적용.from_excel(input_filepath) # (v0-7-0)에서 변경
        
        # convert
        idf = survey.apply_to(grm)
    
    finally:
        # remove unused files
        if preprocess:
            os.remove(processed_filepath)
        
    return idf, grm
    

def run_rebexcel(
    input_filepath :str,
    output_grr_filepath:str|None=None,
    output_idf_filepath:str|None=None,
    *,
    save_grr  :bool=True,
    save_idf  :bool=True,
    preprocess:bool=True,
    ) -> tuple[GreenRetrofitResult, IDF]:
    
    # define output path
    if output_grr_filepath is None:
        output_grr_filepath = input_filepath.replace(r".xlsx",r".grr")
    if output_idf_filepath is None:
        output_idf_filepath = input_filepath.replace(r".xlsx",r".idf")
    
    # specify weatherdata (v-070 수정사항: 건물정보 탭의 주소, 기상데이터옵션, 기준년도로 결정. PK 가 주소와 다르면 변환 전에 멈춤)
    building = pd.read_excel(input_filepath, sheet_name="건물정보", header=1).iloc[0]
    pk = choose_pk(building.get("PK코드"), input_filepath)
    weatherdata_filepath = get_weatherdata(building["주소"], building["기상데이터옵션"], building["기준년도"], pk)
    
    idf, grm = rebexcel_to_idf_and_grm(input_filepath, preprocess=preprocess)
    
    # run
    grr = GreenRetrofitResult(grm, idf.run(weatherdata_filepath))
        
    # save if required
    if save_grr:
        grr.write(output_grr_filepath)
        
    if save_idf:
        idf.write(output_idf_filepath)
        
    return grr, idf