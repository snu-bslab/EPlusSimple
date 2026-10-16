from epsimple.debug import debug_excel, report_result
import os
import pandas as pd
import tqdm
import multiprocessing as mp
import warnings

warnings.filterwarnings(
    "ignore",
    message="Data Validation extension is not supported and will be removed",
    category=UserWarning,
    module="openpyxl"
)


def process_file(args):
    try:
        inputexcel_dir, file = args
        exceptions, warnings = debug_excel(os.path.join(inputexcel_dir, file), include_reb=True)
        code, df = report_result(exceptions, warnings)

        if df is not None and not df.empty:
            df = df.copy()
            df.insert(0, "file_name", file)
            return df
        
    except Exception as e:
        print(f"Error occurred while processing {file}: {e}")
    


if __name__ == "__main__":
    
    inputexcel_dir = r"Z:\01 진행과제\(부동산원) GR정성평가\23 수신자료\260519 0515 데이터셋 수정 _ 1차 수정"
    
    target_files = os.listdir(inputexcel_dir)
    args_list = [(inputexcel_dir, file) for file in target_files]

    result_dfs = []

    with mp.Pool(processes=mp.cpu_count()) as pool:
        for df in tqdm.tqdm(
            pool.imap_unordered(process_file, args_list),
            total=len(args_list),
            ncols=150,
            desc='Debugging REB Excel Files'
        ):
            if df is not None:
                result_dfs.append(df)

    result_df = pd.concat(result_dfs, ignore_index=True)
    result_df.to_excel(os.path.join(inputexcel_dir, "debug_result.xlsx"), index=False)