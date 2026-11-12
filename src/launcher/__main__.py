
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
import os
import importlib
from pathlib import Path

# third-party modules
from flask import Flask

# local modules
# DO NOT IMPORT RELATIVELY
from .config import TEMPLATE_DIRNAME, COREMODULE_NAME, REQUIRED_PACK # v-070 수정사항

# v-070 수정사항: 런처 셸 버전 확인 (runtime\pack_version.txt 가 없으면 1)
PACK_FILE = Path(__file__).resolve().parents[2] / "runtime" / "pack_version.txt"
PACK      = int(PACK_FILE.read_text().strip()) if PACK_FILE.exists() else 1
if PACK < REQUIRED_PACK:
    raise SystemExit(f"이 코드는 런처 셸 {REQUIRED_PACK} 버전이 필요합니다 (지금 {PACK}). 런처 폴더를 새로 받으세요.")

source =importlib.import_module(f".{COREMODULE_NAME}", package=__package__)

# ---------------------------------------------------------------------------- #
#                       APP DEFINITION AND INITIALIZATION                      #
# ---------------------------------------------------------------------------- #

def initizalize_app(
    *,
    upload_dirpath   = None,
    static_dirname   = None,
    template_dirname = None,
    ) -> Flask:
    
    # define and create upload direcotry
    if upload_dirpath is None:
        upload_dirpath = Path(__file__).parent / "uploads"
    if not os.path.exists(upload_dirpath):
        os.mkdir(upload_dirpath)
    
    # define static directory
    if static_dirname is None:
        static_dirname = "static"
    static_dirpath = f"./{static_dirname}"
    
    # define template directory
    if template_dirname is None:
        template_dirname = "templates_reb"
    template_dirpath = f"./{template_dirname}"
    
    # create a flask app 
    app = Flask(__name__,
        static_folder  =static_dirpath  ,
        template_folder=template_dirpath,
    )
    
    # and set default options
    app.config["UPLOAD_FOLDER"] = upload_dirpath
    app.config["JSON_AS_ASCII"] = False
    
    return app


# ---------------------------------------------------------------------------- #
#                                    SCRIPT                                    #
# ---------------------------------------------------------------------------- #

if __name__ == "__main__":
    
    app = initizalize_app(template_dirname=TEMPLATE_DIRNAME)
    app.add_url_rule("/", "main", source.getpost , methods=["GET","POST"])
    for rule, endpoint, func in getattr(source, "EXTRA_ROUTES", []): # v-070 수정사항
        app.add_url_rule(rule, endpoint, func)
    app.run(debug=False, host="127.0.0.1", port=5000) # v-070 수정사항: 배포용 (내 PC 에서만 접속, 디버그 콘솔 끔)