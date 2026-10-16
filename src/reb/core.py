
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
from .auxiliary import find_weatherdata

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
    
    idf, grm = rebexcel_to_idf_and_grm(input_filepath, preprocess=preprocess)
    
    # specify weatherdata
    loc     = pd.read_excel(input_filepath, sheet_name="건물정보", header = 1).at[0,"주소"]
    simtype = os.path.basename(input_filepath).replace(".xlsx","").split("_")[2].replace("GR","").replace("preprocess","")
    weatherdata_filepath = find_weatherdata(loc, simtype)
    
    # run
    grr = GreenRetrofitResult(grm, idf.run(weatherdata_filepath))
        
    # save if required
    if save_grr:
        grr.write(output_grr_filepath)
        
    if save_idf:
        idf.write(output_idf_filepath)
        
    return grr, idf