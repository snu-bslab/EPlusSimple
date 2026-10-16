import os
import shutil
import argparse
from pathlib import Path

def copy_flattened(
    source_dir: str,
    target_dir: str = None,
    *,
    max_depth: int = None,
    extensions: tuple[str, ...] = None,
    overwrite: bool = False
):
    """
    지정한 source_dir 아래 모든 하위 폴더의 파일들을 하나의 폴더로 복사(flatten)하는 함수.
    """
    src = Path(source_dir).resolve()
    if target_dir is None:
        target_dir = src / "flattened"
    tgt = Path(target_dir).resolve()
    tgt.mkdir(parents=True, exist_ok=True)

    src_depth = len(src.parts)
    count = 0

    for root, _, files in os.walk(src):
        current_depth = len(Path(root).parts) - src_depth
        if max_depth is not None and current_depth > max_depth:
            continue

        for file in files:
            if extensions and not file.lower().endswith(tuple(ext.lower() for ext in extensions)):
                continue

            src_file = Path(root) / file
            dst_file = tgt / file
            
            if tgt in src_file.parents:
                continue

            # 이름 충돌 방지
            if dst_file.exists() and not overwrite:
                stem, ext = dst_file.stem, dst_file.suffix
                i = 1
                while (tgt / f"{stem}_{i}{ext}").exists():
                    i += 1
                dst_file = tgt / f"{stem}_{i}{ext}"

            shutil.copy2(src_file, dst_file)
            count += 1
            
    print(f"완료: {count}개의 파일이 '{tgt}' 폴더로 복사되었습니다.")


def parse_arguments():
    """명령줄 인수(CLI Arguments)를 파싱하는 함수"""
    # RawTextHelpFormatter를 사용하여 help 텍스트의 줄바꿈을 유지합니다.
    parser = argparse.ArgumentParser(
        description="여러 하위 폴더의 파일들을 하나의 폴더로 모아서 복사(Flatten)합니다.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    
    parser.add_argument("source_dir", type=str, help="복사할 원본 파일들이 있는 최상위 폴더 경로")
    parser.add_argument("-t", "--target_dir", type=str, default=None, help="저장할 대상 폴더 경로 (기본값: source_dir/flattened)")
    parser.add_argument("-m", "--max_depth", type=int, default=None, help="탐색할 최대 하위 깊이")
    parser.add_argument("-e", "--extensions", type=str, nargs='*', default=None, help="포함할 확장자 지정 (예: .jpg .png)")
    parser.add_argument("-o", "--overwrite", action="store_true", help="이름이 같을 경우 덮어쓰기 허용")

    return parser.parse_args()


# ============================================================================ #
#                                    MAIN                                      #
# ============================================================================ #

if __name__ == "__main__":
    """
    [스크립트 사용법]
    터미널(CMD)에서 아래와 같은 형식으로 실행합니다.
    
    1. 기본 실행 (하위 폴더 결과를 원본_경로/flattened 에 저장):
       python flatten_files.py "원본_폴더_경로"
       
    2. 옵션 활용 실행 (특정 확장자만 골라서 다른 폴더에 저장):
       python flatten_files.py "C:\\Input" -t "D:\\Output" -e .xlsx .csv
       
    3. 전체 옵션 도움말 보기:
       python flatten_files.py --help
    """
    
    # 1. 인수 파싱
    args = parse_arguments()

    # 2. 확장자 전처리 (사용자가 'xlsx'라고 입력해도 '.xlsx'로 변환)
    exts = None
    if args.extensions:
        exts = tuple(ext if ext.startswith('.') else f'.{ext}' for ext in args.extensions)

    # 3. 메인 로직 실행
    copy_flattened(
        source_dir=args.source_dir,
        target_dir=args.target_dir,
        max_depth=args.max_depth,
        extensions=exts,
        overwrite=args.overwrite
    )