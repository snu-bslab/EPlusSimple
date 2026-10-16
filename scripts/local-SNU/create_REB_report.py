
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from operator import contains
import os
import re

# third-party modules
import pandas as pd

# local modules
from reb.report import build_report, MetaData, escape_str


# ---------------------------------------------------------------------------- #
#                                   SETTINGS                                   #
# ---------------------------------------------------------------------------- #

rebexcel_dir  = r"Z:\01 진행과제\(부동산원) GR정성평가\31 코드\run_REB_excel\input_excel"
grr_dir       = r"Z:\01 진행과제\(부동산원) GR정성평가\31 코드\run_REB_excel\result_grr"
report_dir    = r"Z:\01 진행과제\(부동산원) GR정성평가\31 코드\run_REB_excel\report"
comment_path  = r"Z:\01 진행과제\(부동산원) GR정성평가\31 코드\run_REB_excel\comment.csv"
masterdb_path = r"Z:\01 진행과제\(부동산원) GR정성평가\31 코드\run_REB_excel\masterdb.xlsx"

# ---------------------------------------------------------------------------- #
#                                   MAIN FUNC                                  #
# ---------------------------------------------------------------------------- #

def find_building_sets(
    rebexcel_dir:str,
    grr_dir     :str,
    ) -> list[dict]:
    
    def create_new_data(name:str) -> dict:
        return {
            "name" : name ,
            "valid": False,
            "excel": {
                "GR이전":None,
                "GR이후":None,
                "N년차" :None,
            },
            "grr": {
                "GR이전":None,
                "GR이후":None,
                "N년차" :None,
            },
        }
        
    
    rebexcel_filelist = [file for file in os.listdir(rebexcel_dir) if file.endswith(".xlsx") and not file.startswith("~$")]
    grr_filelist      = [file for file in os.listdir(grr_dir) if file.endswith(".grr")]
    
    buildingdict = dict()
    
    # excel files
    for file in rebexcel_filelist:
        
        info = re.search(r"(?P<name>^\d{,3}_[^_]+)_(?P<type>[^_]+)(.xlsx|_운영)", file)
        
        if info is None:
            raise ValueError(f"parsing이 안됨: {file}")
        
        if (n:=info.group("name")) not in buildingdict.keys():
            buildingdict[n] = create_new_data(n)
            
        if (t:=info.group("type")) not in buildingdict[n]["excel"].keys():
            raise ValueError(f"keyword '{t}'는 좀 이상한듯 ('{file}'을 parsing함)")        
        
        buildingdict[n]["excel"][t] = os.path.join(rebexcel_dir, file)

    # grr files
    for file in grr_filelist:
        
        info = re.search(r"(?P<name>^\d{,3}_[^_]+)_(?P<type>[^_]+)(.grr|_운영)", file)
        
        if info is None:
            raise ValueError(f"parsing이 안됨: {file}")
        
        if (n:=info.group("name")) not in buildingdict.keys():
            buildingdict[n] = create_new_data(n)
        
        if (t:=info.group("type")) not in buildingdict[n]["grr"].keys():
            raise ValueError(f"keyword '{t}'는 좀 이상한듯 ('{file}'을 parsing함)")
        
        buildingdict[n]["grr"][t] = os.path.join(grr_dir, file)
    
    # validity
    for _, buildingdata in buildingdict.items():
        if all(v is not None for v in list(buildingdata["excel"].values())+list(buildingdata["grr"].values())):
            buildingdata["valid"] = True
    
    return [d for d in buildingdict.values() if d["valid"]], [d for d in buildingdict.values() if not d["valid"]] 

def find_comment(
    commentdf:pd.DataFrame,
    buildingfilename:str,
    ) -> dict:
    
    buildingid = int(buildingfilename[:3])
    buildingname = buildingfilename[4:]
    
    matched = commentdf[(commentdf["고유번호"] == buildingid) & (commentdf["건축물명"].map(lambda s: s.replace(" ","")) == buildingname.replace(" ",""))]
    if matched.empty:
        raise KeyError(f"comment.csv에 '{buildingid}_{buildingname}' 항목이 없습니다.")
    commentdict = matched.iloc[0,2:].to_dict()
    
    pointkeys = ["동절기 실내 온도", "동절기 실내 습도", "하절기 실내 온도", "하절기 실내 습도", "공기질", "음환경", "빛환경"]
    commentdict["point"] = sum(int(commentdict[key]) for key in pointkeys) / len(pointkeys)
    for key in pointkeys:
        commentdict[key] =  "★" * int(commentdict[key]) + "☆" * (7 - int(commentdict[key]))
    commentdict = {
        k: f"{v:.1f}" if not isinstance(v, str) else v.replace(r"\n","\\")
        for k, v in commentdict.items()
    }
    
    return commentdict


def get_master_df() -> pd.DataFrame:
    
    df =  pd.read_excel(masterdb_path, sheet_name="총괄리스트", header=[0,1,2,3])
    
    # multicolumn 정리
    df.columns = [
        "_".join([str(x).strip().replace("\n"," ") for x in col if "Unnamed" not in str(x) and str(x).strip() != "-"])
        for col in df.columns
    ]
    
    # 데이터 없는 열 삭제
    garbagecols = []
    for idx, col in enumerate(df.columns):
        if idx >=1 and col == df.columns[idx-1]:
            garbagecols.append(idx)            
    df = df.iloc[:, [i for i in range(len(df.columns)) if i not in garbagecols]]
    
    # 중복 열 (근거) 정리
    df.columns = [
        "_".join(df.columns[idx-1].split("_")[:2]) + "_근거" if re.match(r"(GR이전|GR이후|N년차)_근거", col) else col
        for idx, col in enumerate(df.columns)
    ]
    
    # 인덱스 정리
    df.index = df.loc[:,["임시 고유번호","건축물명"]].apply(lambda x: f"{int(x.iloc[0]):03d}_{x.iloc[1].strip()}".replace(" ", ""), axis=1)
    
    return df
    

def main(
    rebexcel_dir:str,
    grr_dir     :str,
    report_dir  :str,
    ) -> None:    
    
    commentdf = pd.read_csv(comment_path, encoding="cp949")
    masterdf  = get_master_df()

    
            # pk번호 이야기
    pk_column = "관리건축물대장PK"

    if pk_column not in masterdf.columns:
        raise KeyError(
            f"masterdb 총괄리스트에 '{pk_column}' 열이 없습니다. "
            f"PK 관련 열: {[col for col in masterdf.columns if 'PK' in col]}"
        )

    
    commentdf["건축물명"] = commentdf["건축물명"].map(lambda x: x.strip())
    validlist, invalidlist = find_building_sets(
        rebexcel_dir,
        grr_dir     ,
    )
    
    for idx, d in enumerate(validlist, start=1):

        pdfpath     = os.path.join(report_dir, f"{d["name"]}.pdf")
        workingpath = os.path.join(report_dir, f"{d["name"]}.working")
        if os.path.exists(pdfpath) or os.path.exists(workingpath):
            print(f"[{idx}/{len(validlist)}] {d['name']} : 이미 존재함, 건너뜀")
            continue
        else:
            with open(workingpath, "w") as f:
                f.write("")

        print(f"[{idx}/{len(validlist)}] {d['name']} : 리포트 생성 시작")

        try:
            commentdict = find_comment(commentdf, d["name"])
            masterdict  = masterdf.loc[d["name"].replace(" ", "")].to_dict()

            
            build_report(
                *d["excel"].values(),
                *d["grr"].values()  ,
                commentdict,
                masterdict ,
                pdfpath    ,
            )

        except Exception as error:
            print(f"[{idx}/{len(validlist)}] {d['name']} : 실패 - {type(error).__name__}: {error}")

        finally:
            if os.path.exists(workingpath):
                os.remove(workingpath)
# ---------------------------------------------------------------------------- #
#                                    SCRIPT                                    #
# ---------------------------------------------------------------------------- #

if __name__ == "__main__":
    
    main(
        rebexcel_dir,
        grr_dir     ,
        report_dir  ,
    )
