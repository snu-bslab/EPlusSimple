"""
v-070 수정사항: 엑셀 보고서 템플릿의 자리표를 채우고 PDF 로 내보낸다

자리표
  {{이름}}         값. 중첩은 점으로 (metadata.name, comment.occupant). 글자와 섞어도 됨
  {{table:이름}}   표. 이 셀부터 아래로 행을 쓴다 (열 폭은 바로 위 머리글 행의 병합)
  {{image:이름}}   그림. 이 셀에 PNG 를 넣는다
"""
import os
import re
import subprocess
import tempfile
from copy import copy

import pandas as pd
from openpyxl import load_workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.cell_range import CellRange
from openpyxl.formatting.formatting import ConditionalFormattingList

FONT       = "Malgun Gothic"
TEXT       = "3B3838"
CHANGED_BG = "FFF2CC"      # 전후 값이 바뀐 행 (템플릿에 조건부 서식이 없을 때)
ROW_H      = 16

PLACEHOLDER = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


# ---------------------------------------------------------------------------- #
#                                 RENDER REPORT                                #
# ---------------------------------------------------------------------------- #

def render_report(template_path, out_path, context, tables=None, images=None):
    tables = tables or {}
    images = images or {}
    flat   = flatten(context)

    wb = load_workbook(template_path)
    if "설명" in wb.sheetnames:                     # 양식 설명 시트는 결과물에서 뺀다
        wb.remove(wb["설명"])
    for ws in wb.worksheets:
        while True:
            cell = next_placeholder(ws)
            if cell is None:
                break
            text = cell.value.strip()

            if text.startswith("{{table:"):
                name = text[len("{{table:"):-2].strip()
                cell.value = None
                df, spans = tables[name] if isinstance(tables[name], tuple) else (tables[name], None)
                write_table(ws, cell.row, cell.column, df, spans)

            elif text.startswith("{{image:"):
                name = text[len("{{image:"):-2].strip()
                cell.value = None
                path, width = images[name]
                insert_image(ws, cell.coordinate, path, width)

            else:
                cell.value = fill_text(cell.value, flat)
                fit_text_height(ws, cell)

    wb.save(out_path)
    return out_path


def export_pdf(xlsx_path, pdf_path):
    """엑셀(COM)로 통합 문서 전체를 PDF 로 내보낸다"""
    xlsx_path = os.path.abspath(xlsx_path).replace("'", "''")
    pdf_path  = os.path.abspath(pdf_path).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$book = $excel.Workbooks.Open('{xlsx_path}')
$book.ExportAsFixedFormat(0, '{pdf_path}')
$book.Close($false)
$excel.Quit()
"""
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8-sig", delete=False) as f:
        f.write(script)
        ps1 = f.name
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1],
                                capture_output=True, text=True, encoding="cp949", errors="replace")
    finally:
        os.remove(ps1)
    if result.returncode != 0 or not os.path.exists(pdf_path.replace("''", "'")):
        raise RuntimeError("PDF 변환 실패: " + result.stderr.strip()[:300])
    return pdf_path


def next_placeholder(ws):
    """아직 채우지 않은 자리표 칸 하나"""
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and PLACEHOLDER.search(cell.value):
                return cell
    return None


def flatten(context, prefix=""):
    """{"a": {"b": 1}} -> {"a.b": 1}"""
    flat = {}
    for key, value in context.items():
        name = prefix + str(key)
        if isinstance(value, dict):
            flat.update(flatten(value, name + "."))
        else:
            flat[name] = value
    return flat


def fill_text(text, flat):
    """{{이름}} 을 값으로 바꾼다. 셀 전체가 자리표 하나면 값 자체(숫자 가능)를 돌려준다"""
    whole = PLACEHOLDER.fullmatch(text.strip())
    if whole is not None:
        return clean(flat.get(whole.group(1).strip(), ""))

    def replace(match):
        return str(clean(flat.get(match.group(1).strip(), "")))
    return PLACEHOLDER.sub(replace, text)


def clean(value):
    """빈 값은 빈 칸으로, LaTeX 용으로 들어간 기호는 걷어낸다"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, str):
        return value.replace("\\\\", "\n").replace("\\%", "%").replace("$", "").replace("~", "-")
    return value


def write_table(ws, row, col, df, spans=None):
    """템플릿에 미리 그려 둔 표에 값만 채운다. (row, col) 은 첫 데이터 행의 첫 칸.
    열 구성(병합 폭)은 바로 위 머리글 행에서 읽는다"""
    df = df.copy()
    merge_first_column = isinstance(df.index, pd.MultiIndex)
    if isinstance(df.index, pd.MultiIndex) or not isinstance(df.index, pd.RangeIndex):
        df = df.reset_index()

    if spans is None:
        spans = header_spans(ws, row - 1, col)
    starts = [col + sum(spans[:j]) for j in range(len(spans))]
    if len(starts) < len(df.columns):
        raise ValueError(f"템플릿 표의 열({len(starts)})이 데이터 열({len(df.columns)})보다 적습니다: {ws.title} {row}행")

    grid_rows = count_grid_rows(ws, row, starts, spans)
    sample_row = row + 1 if grid_rows >= 2 else row                  # 자리표 칸은 글꼴이 다를 수 있어 둘째 행을 본보기로
    for r in range(row + 1, row + grid_rows):                        # v-070 수정사항: 표 행의 병합을 머리글 열 구성에 맞춘다
        set_spans(ws, r, starts, spans)
    set_spans(ws, row, starts, spans, style_row=sample_row if sample_row != row else None)
    fonts   = [copy(ws.cell(sample_row, c).font) for c in starts]
    heights = [ws.row_dimensions[r].height or ROW_H for r in range(row, row + max(grid_rows, 1))]
    if len(df) > grid_rows:
        grow_grid(ws, row + max(grid_rows, 1) - 1, len(df) - max(grid_rows, 1), starts, spans)

    # 템플릿에 조건부 서식(값이 바뀌면 강조)이 있으면 그것을 쓰고, 없으면 바뀐 행을 칠한다
    own_highlight = not has_conditional_format(ws, row, row + max(len(df), 1) - 1, starts[0], starts[-1] + spans[-1] - 1)
    changed_rows  = changed(df) if own_highlight else [False] * len(df)

    for i, record in enumerate(df.itertuples(index=False)):
        for j, value in enumerate(record):
            cell = ws.cell(row + i, starts[j], clean(value))
            font = copy(fonts[j])
            if font.name in (None, "Calibri"):
                font = Font(name=FONT, size=9, color=TEXT)
            font = Font(name=font.name, size=font.sz, color=font.color, bold=font.b or changed_rows[i], italic=False)
            cell.font = font
            if isinstance(value, float):
                cell.number_format = "0.0"
            if changed_rows[i]:
                for c in range(starts[j], starts[j] + spans[j]):
                    ws.cell(row + i, c).fill = PatternFill("solid", fgColor=CHANGED_BG)
        base = heights[min(i, len(heights) - 1)]
        ws.row_dimensions[row + i].height = base * lines_for(ws, starts, spans, record, fonts)

    hide_unused_rows(ws, row + len(df), starts, spans)

    # MultiIndex 첫 열: 같은 값이 이어지면 세로로 병합 (예: 기술요소)
    if merge_first_column:
        values = df.iloc[:, 0].tolist()
        start = 0
        for i in range(1, len(values) + 1):
            if i == len(values) or values[i] != values[start]:
                if i - start > 1:
                    for r in range(row + start, row + i):
                        if spans[0] > 1:
                            ws.unmerge_cells(start_row=r, start_column=starts[0], end_row=r, end_column=starts[0] + spans[0] - 1)
                    ws.merge_cells(start_row=row + start, start_column=starts[0],
                                   end_row=row + i - 1, end_column=starts[0] + spans[0] - 1)
                start = i


def hide_unused_rows(ws, first_row, starts, spans):
    """템플릿에 미리 그려 둔 표 행이 남으면 숨긴다. 표 모양과 쪽 구성은 템플릿 그대로"""
    r = first_row
    while is_table_row(ws, r, starts, spans):
        ws.row_dimensions[r].hidden = True
        r += 1


def count_grid_rows(ws, first_row, starts, spans):
    """자리표 행부터 아래로 미리 그려 둔 표 행 수"""
    n = 0
    while is_table_row(ws, first_row + n, starts, spans):
        n += 1
    return n


def is_table_row(ws, r, starts, spans):
    """머리글과 같은 병합이 있으면 표 행. 병합할 열이 없는 표는 첫 칸의 위아래 선으로 본다"""
    wide = [(start, span) for start, span in zip(starts, spans) if span > 1]
    if wide:
        merged = {m.min_col: m.max_col - m.min_col + 1 for m in ws.merged_cells.ranges if m.min_row == r}
        if all(merged.get(start) == span for start, span in wide):
            return True
    return is_grid_cell(ws.cell(r, starts[0])) # v-070 수정사항: 병합이 달라도 위아래 선이 있으면 표 행


def set_spans(ws, r, starts, spans, style_row=None):
    """v-070 수정사항: 한 행의 병합을 머리글 열 구성으로 다시 잡는다.
    칸 서식은 원래 그 칸을 덮던 병합의 첫 칸에서, style_row 가 있으면 그 행 같은 열에서 가져온다"""
    first, last = starts[0], starts[-1] + spans[-1] - 1
    owner = {}
    for m in list(ws.merged_cells.ranges):
        if m.min_row == r == m.max_row and m.min_col >= first and m.max_col <= last:
            for c in range(m.min_col, m.max_col + 1):
                owner[c] = m.min_col
            ws.unmerge_cells(str(m))
    for c in range(first, last + 1):
        src = ws.cell(style_row, c) if style_row else ws.cell(r, owner.get(c, c))
        dst = ws.cell(r, c)
        if src is not dst:
            dst._style = copy(src._style)
    for start, span in zip(starts, spans):
        if span > 1:
            ws.merge_cells(start_row=r, start_column=start, end_row=r, end_column=start + span - 1)


def has_conditional_format(ws, r0, r1, c0, c1):
    """표 영역에 조건부 서식이 걸려 있는지"""
    for cf in ws.conditional_formatting:
        for rng in str(cf.sqref).split():
            cr = CellRange(rng)
            if cr.min_row <= r1 and cr.max_row >= r0 and cr.min_col <= c1 and cr.max_col >= c0:
                return True
    return False


def shift_conditional_formats(ws, idx, amount):
    """행을 끼운 만큼 조건부 서식 범위를 민다. 끼운 자리 바로 위에서 끝나는 범위는 아래로 늘린다"""
    items = [(str(cf.sqref), cf.rules) for cf in ws.conditional_formatting]
    ws.conditional_formatting = ConditionalFormattingList()
    for sqref, rules in items:
        ranges, moved = [], False
        for rng in sqref.split():
            cr = CellRange(rng)
            if cr.min_row >= idx:
                cr.shift(row_shift=amount)
                moved = True
            elif cr.max_row == idx - 1:
                cr.expand(down=amount)
            ranges.append(cr.coord)
        for rule in rules:
            if moved:
                rule.formula = [shift_formula_rows(f, amount) for f in rule.formula]
            ws.conditional_formatting.add(" ".join(ranges), rule)


def shift_formula_rows(formula, amount):
    """수식의 상대 행 번호($ 없는 행)를 amount 만큼 민다"""
    def move(m):
        return m.group(1) + m.group(2) + (m.group(3) if m.group(2) else str(int(m.group(3)) + amount))
    return re.sub(r"(\$?[A-Z]{1,3})(\$?)(\d+)", move, formula)


def grow_grid(ws, last_grid_row, n, starts, spans):
    """표의 마지막 행 아래에 같은 모양의 빈 행 n 개를 끼워 넣는다. 아래 내용은 그만큼 밀린다"""
    insert_rows_keep_layout(ws, last_grid_row + 1, n)
    for r in range(last_grid_row + 1, last_grid_row + 1 + n):
        ws.row_dimensions[r].height = ws.row_dimensions[last_grid_row].height
        for c in range(1, ws.max_column + 1):                         # 여백 열까지 배경색을 같이 복사
            src = ws.cell(last_grid_row, c)
            dst = ws.cell(r, c)
            dst.fill = copy(src.fill)
            dst.border = copy(src.border)
            dst.font = copy(src.font)
            dst.alignment = copy(src.alignment)
        for start, span in zip(starts, spans):
            if span > 1:
                ws.merge_cells(start_row=r, start_column=start, end_row=r, end_column=start + span - 1)


def insert_rows_keep_layout(ws, idx, amount):
    """openpyxl insert_rows 는 병합·그림·인쇄영역을 안 밀어 주므로 직접 옮긴다"""
    moved = []
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row >= idx:
            moved.append((rng.min_row, rng.min_col, rng.max_row, rng.max_col))
            ws.unmerge_cells(str(rng))
    heights = {r: ws.row_dimensions[r].height for r in range(idx, ws.max_row + 1)}

    ws.insert_rows(idx, amount)

    for r, h in heights.items():
        ws.row_dimensions[r + amount].height = h
    for r in range(idx, idx + amount):
        ws.row_dimensions[r].height = ROW_H
    for min_row, min_col, max_row, max_col in moved:
        ws.merge_cells(start_row=min_row + amount, start_column=min_col, end_row=max_row + amount, end_column=max_col)
    for image in ws._images:
        if image.anchor._from.row + 1 >= idx:
            image.anchor._from.row += amount
    shift_conditional_formats(ws, idx, amount)
    if ws.print_area:                                              # 템플릿의 인쇄 열 범위는 그대로, 끝 행만 늘린다
        area = ws.print_area[0] if isinstance(ws.print_area, list) else ws.print_area
        area = area.split("!")[-1].replace("$", "")
        cr = CellRange(area)
        cr.expand(down=amount)
        ws.print_area = cr.coord


def is_grid_cell(cell):
    """표 칸은 위아래 선이 모두 있다 (박스 테두리 칸은 좌우만)"""
    top, bottom = cell.border.top, cell.border.bottom
    return top is not None and top.style is not None and bottom is not None and bottom.style is not None


def header_spans(ws, header_row, col):
    """머리글 행의 병합 폭을 읽어 [열 수, ...] 로 돌려준다. 머리글 칸이 비면 끝"""
    merged = {}
    for rng in ws.merged_cells.ranges:
        if rng.min_row == header_row:
            merged[rng.min_col] = rng.max_col - rng.min_col + 1
    spans = []
    c = col
    while c <= ws.max_column and (ws.cell(header_row, c).value is not None or c in merged): # v-070 수정사항: 비어 있는 병합 머리글 칸도 열로 본다
        span = merged.get(c, 1)
        spans.append(span)
        c += span
    return spans


def text_width(text):
    """한글 2, 영문 1"""
    return sum(2 if ord(ch) > 127 else 1 for ch in str(text))


def column_width(ws, c):
    """열 폭. column_dimensions[...] 로 읽으면 없는 열 정보가 새로 생겨(폭 13) 저장되므로 읽기만 한다"""
    for dim in list(ws.column_dimensions.values()):
        if dim.min and dim.max and dim.min <= c <= dim.max and dim.width:
            return dim.width
    return ws.sheet_format.defaultColWidth or 8.43


def lines_for(ws, starts, spans, values, fonts):
    """실제 열 폭과 글자 크기로, 한 행에 필요한 줄 수 (최대 3)"""
    lines = 1
    for value, start, span, font in zip(values, starts, spans, fonts):
        size = font.sz or 9
        capacity = sum(column_width(ws, c) for c in range(start, start + span)) * 11 / size * 0.9
        shown = f"{value:.1f}" if isinstance(value, float) else str(clean(value))   # 실수는 화면 표시(0.0) 기준
        for part in shown.split("\n"):
            lines = max(lines, -(-text_width(part) // max(capacity, 1)))
    return min(int(lines), 3)


def fit_text_height(ws, cell):
    """글자가 칸(병합 포함)을 넘치면 그 칸의 마지막 행을 늘린다"""
    if not isinstance(cell.value, str) or not cell.alignment.wrap_text:
        return
    rng  = next((m for m in ws.merged_cells.ranges if cell.coordinate in m), None)
    cols = range(rng.min_col, rng.max_col + 1) if rng else [cell.column]
    rows = list(range(rng.min_row, rng.max_row + 1)) if rng else [cell.row]
    size = cell.font.sz or 11
    capacity = sum(column_width(ws, c) for c in cols) * 11 / size * 0.9
    lines = sum(max(1, -(-text_width(part) // capacity)) for part in cell.value.split("\n"))
    need  = lines * size * 1.5
    have  = sum(ws.row_dimensions[r].height or 15 for r in rows)
    if need > have:
        last = rows[-1]
        ws.row_dimensions[last].height = (ws.row_dimensions[last].height or 15) + need - have


def changed(df):
    """전후 비교 열이 있으면, 값이 하나라도 다른 행을 True 로"""
    cols = [c for c in ["그린리모델링 이전", "그린리모델링 이후", "운영특성 반영"] if c in df.columns]
    if len(cols) < 2:
        return [False] * len(df)
    flags = []
    for _, r in df.iterrows():
        values = {str(r[c]).strip() for c in cols}
        flags.append(len(values) > 1)
    return flags


def insert_image(ws, coordinate, path, width_px):
    image = Image(path)
    ratio = width_px / image.width
    image.width  = width_px
    image.height = image.height * ratio
    ws.add_image(image, coordinate)
