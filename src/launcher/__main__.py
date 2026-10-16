
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
from .config import TEMPLATE_DIRNAME, COREMODULE_NAME
source = importlib.import_module(f".{COREMODULE_NAME}", package=__package__)

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
    app.run(debug=True, host="0.0.0.0", port=5000)