from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import (
    WD_ALIGN_PARAGRAPH,
    WD_BREAK,
    WD_LINE_SPACING,
    WD_TAB_ALIGNMENT,
    WD_TAB_LEADER,
)
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT.parent / "output" / "paper"
ASSET_DIR = OUTPUT_DIR / "assets"
OUTPUT_PATH = OUTPUT_DIR / "work_ticket_traceable_ocr_llm_error_transition_paper_draft.docx"

# Base preset: narrative_proposal.
# Named override: academic_paper_cn (A4, Chinese academic typography, black hierarchy).
PAGE_WIDTH_DXA = 11906
CONTENT_WIDTH_DXA = 9072
TABLE_INDENT_DXA = 0
CELL_MARGIN_DXA = {"top": 80, "bottom": 80, "start": 100, "end": 100}

BLACK = RGBColor(0x00, 0x00, 0x00)
MUTED = RGBColor(0x66, 0x66, 0x66)
LIGHT_FILL = "F4F6F9"
GRID_COLOR = "8A8A8A"


def set_run_font(run, *, east_asia="宋体", ascii_font="Times New Roman", size=10.5,
                 bold=None, italic=None, color=BLACK):
    run.font.name = ascii_font
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), east_asia)
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), ascii_font)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), ascii_font)
    run.font.size = Pt(size)
    run.font.color.rgb = color
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_style_font(style, *, east_asia, ascii_font, size, bold=False, color=BLACK):
    style.font.name = ascii_font
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = color
    style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), east_asia)
    style._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), ascii_font)
    style._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), ascii_font)


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    fld_char1 = OxmlElement("w:fldChar")
    fld_char1.set(qn("w:fldCharType"), "begin")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = " PAGE "
    fld_char2 = OxmlElement("w:fldChar")
    fld_char2.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char1)
    run._r.append(instr_text)
    run._r.append(fld_char2)
    set_run_font(run, east_asia="宋体", size=9, color=MUTED)


def configure_styles(doc: Document):
    styles = doc.styles

    normal = styles["Normal"]
    set_style_font(normal, east_asia="宋体", ascii_font="Times New Roman", size=10.5)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.paragraph_format.first_line_indent = Pt(21)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.25
    normal.paragraph_format.widow_control = True

    h1 = styles["Heading 1"]
    set_style_font(h1, east_asia="黑体", ascii_font="Arial", size=14, bold=True)
    h1.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h1.paragraph_format.first_line_indent = Pt(0)
    h1.paragraph_format.space_before = Pt(12)
    h1.paragraph_format.space_after = Pt(6)
    h1.paragraph_format.line_spacing = 1.15
    h1.paragraph_format.keep_with_next = True

    h2 = styles["Heading 2"]
    set_style_font(h2, east_asia="黑体", ascii_font="Arial", size=12, bold=True)
    h2.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h2.paragraph_format.first_line_indent = Pt(0)
    h2.paragraph_format.space_before = Pt(9)
    h2.paragraph_format.space_after = Pt(4)
    h2.paragraph_format.line_spacing = 1.15
    h2.paragraph_format.keep_with_next = True

    h3 = styles["Heading 3"]
    set_style_font(h3, east_asia="黑体", ascii_font="Arial", size=10.5, bold=True)
    h3.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    h3.paragraph_format.first_line_indent = Pt(0)
    h3.paragraph_format.space_before = Pt(6)
    h3.paragraph_format.space_after = Pt(3)
    h3.paragraph_format.keep_with_next = True

    for name, east_asia, ascii_font, size, align, first_indent, after, line in [
        ("Abstract", "宋体", "Times New Roman", 9.5, WD_ALIGN_PARAGRAPH.JUSTIFY, Pt(0), Pt(2), 1.15),
        ("Keywords", "宋体", "Times New Roman", 9.5, WD_ALIGN_PARAGRAPH.LEFT, Pt(0), Pt(6), 1.15),
        ("Caption", "宋体", "Times New Roman", 9, WD_ALIGN_PARAGRAPH.CENTER, Pt(0), Pt(6), 1.0),
        ("TableText", "宋体", "Times New Roman", 8.5, WD_ALIGN_PARAGRAPH.LEFT, Pt(0), Pt(0), 1.05),
        ("Equation", "宋体", "Times New Roman", 10.5, WD_ALIGN_PARAGRAPH.CENTER, Pt(0), Pt(4), 1.0),
        ("Reference", "宋体", "Times New Roman", 8.5, WD_ALIGN_PARAGRAPH.LEFT, Pt(0), Pt(2), 1.0),
        ("DraftNote", "宋体", "Times New Roman", 9, WD_ALIGN_PARAGRAPH.JUSTIFY, Pt(0), Pt(8), 1.1),
    ]:
        style = styles[name] if name in styles else styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        set_style_font(style, east_asia=east_asia, ascii_font=ascii_font, size=size)
        style.paragraph_format.alignment = align
        style.paragraph_format.first_line_indent = first_indent
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = after
        style.paragraph_format.line_spacing = line

    styles["Reference"].paragraph_format.left_indent = Cm(0.6)
    styles["Reference"].paragraph_format.first_line_indent = Cm(-0.6)


def shade_paragraph(paragraph, fill=LIGHT_FILL):
    p_pr = paragraph._p.get_or_add_pPr()
    shd = p_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        p_pr.append(shd)
    shd.set(qn("w:fill"), fill)
    p_bdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "8")
    left.set(qn("w:color"), "5B6573")
    p_bdr.append(left)
    p_pr.append(p_bdr)


def add_body(doc: Document, text: str, *, style="Normal", bold_prefix: str | None = None):
    p = doc.add_paragraph(style=style)
    if bold_prefix and text.startswith(bold_prefix):
        r1 = p.add_run(bold_prefix)
        set_run_font(r1, east_asia="黑体", ascii_font="Arial", size=10.5, bold=True)
        r2 = p.add_run(text[len(bold_prefix):])
        set_run_font(r2)
    else:
        r = p.add_run(text)
        if style == "Abstract" or style == "Keywords":
            set_run_font(r, size=9.5)
        elif style == "DraftNote":
            set_run_font(r, size=9, color=RGBColor(0x33, 0x33, 0x33))
        else:
            set_run_font(r)
    return p


def add_heading(doc: Document, text: str, level: int):
    p = doc.add_paragraph(style=f"Heading {level}")
    r = p.add_run(text)
    if level == 1:
        set_run_font(r, east_asia="黑体", ascii_font="Arial", size=14, bold=True)
    elif level == 2:
        set_run_font(r, east_asia="黑体", ascii_font="Arial", size=12, bold=True)
    else:
        set_run_font(r, east_asia="黑体", ascii_font="Arial", size=10.5, bold=True)
    return p


def add_equation(doc: Document, text: str, number: int):
    p = doc.add_paragraph(style="Equation")
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.left_indent = Pt(0)
    p.paragraph_format.right_indent = Pt(0)
    p.paragraph_format.tab_stops.clear_all()
    p.paragraph_format.tab_stops.add_tab_stop(
        Cm(8.0), WD_TAB_ALIGNMENT.CENTER, WD_TAB_LEADER.SPACES
    )
    p.paragraph_format.tab_stops.add_tab_stop(
        Cm(15.8), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.SPACES
    )
    r = p.add_run(f"\t{text}")
    set_run_font(r, east_asia="宋体", ascii_font="Cambria Math", size=10.5)
    r2 = p.add_run(f"\t({number})")
    set_run_font(r2, east_asia="宋体", ascii_font="Times New Roman", size=10.5)


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_cell_margins(cell, **kwargs):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m in ["top", "start", "bottom", "end"]:
        if m in kwargs:
            node = tc_mar.find(qn(f"w:{m}"))
            if node is None:
                node = OxmlElement(f"w:{m}")
                tc_mar.append(node)
            node.set(qn("w:w"), str(kwargs.get(m)))
            node.set(qn("w:type"), "dxa")


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_table_geometry(table, widths: Sequence[int]):
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl = table._tbl
    tbl_pr = tbl.tblPr

    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")

    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(TABLE_INDENT_DXA))
    tbl_ind.set(qn("w:type"), "dxa")

    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")

    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), GRID_COLOR)

    grid = tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)

    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(widths[idx]))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell, **CELL_MARGIN_DXA)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def add_table(doc: Document, caption: str, headers: Sequence[str], rows: Sequence[Sequence[str]], widths: Sequence[int]):
    cap = doc.add_paragraph(style="Caption")
    cap.paragraph_format.keep_with_next = True
    run = cap.add_run(caption)
    set_run_font(run, east_asia="黑体", ascii_font="Arial", size=9, bold=True)

    table = doc.add_table(rows=1, cols=len(headers))
    set_repeat_table_header(table.rows[0])
    for idx, header in enumerate(headers):
        cell = table.rows[0].cells[idx]
        set_cell_shading(cell, LIGHT_FILL)
        p = cell.paragraphs[0]
        p.style = doc.styles["TableText"]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(header)
        set_run_font(r, east_asia="黑体", ascii_font="Arial", size=8.5, bold=True)

    for row_data in rows:
        row = table.add_row()
        for idx, value in enumerate(row_data):
            cell = row.cells[idx]
            p = cell.paragraphs[0]
            p.style = doc.styles["TableText"]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if len(str(value)) <= 14 else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(str(value))
            set_run_font(r, size=8.5)
    set_table_geometry(table, widths)
    after = doc.add_paragraph()
    after.paragraph_format.space_after = Pt(2)
    return table


def font(size, *, bold=False):
    path = Path(r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc")
    if not path.exists():
        path = Path(r"C:\Windows\Fonts\simhei.ttf" if bold else r"C:\Windows\Fonts\simsun.ttc")
    return ImageFont.truetype(str(path), size)


def rounded_box(draw, xy, text, *, fill, outline, text_fill=(20, 32, 45), width=3, radius=18):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    x1, y1, x2, y2 = xy
    f = font(29, bold=True)
    box = draw.multiline_textbbox((0, 0), text, font=f, spacing=6, align="center")
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.multiline_text(((x1 + x2 - tw) / 2, (y1 + y2 - th) / 2 - 2), text, font=f, fill=text_fill, spacing=6, align="center")


def arrow(draw, start, end, *, color=(70, 85, 100), width=5):
    draw.line([start, end], fill=color, width=width)
    x2, y2 = end
    x1, y1 = start
    import math
    angle = math.atan2(y2 - y1, x2 - x1)
    size = 16
    p1 = (x2 - size * math.cos(angle - 0.55), y2 - size * math.sin(angle - 0.55))
    p2 = (x2 - size * math.cos(angle + 0.55), y2 - size * math.sin(angle + 0.55))
    draw.polygon([end, p1, p2], fill=color)


def make_architecture_figure(path: Path):
    img = Image.new("RGB", (1800, 900), "white")
    draw = ImageDraw.Draw(img)
    title_font = font(42, bold=True)
    draw.text((70, 45), "EWT-Guard：可追溯工作票结构化抽取与风险校验框架", font=title_font, fill=(20, 36, 55))

    boxes = [
        ((70, 250, 310, 410), "工作票\n图像/PDF", (235, 243, 250), (60, 110, 150)),
        ((380, 250, 660, 410), "PPStructureV3\n版面与OCR", (236, 247, 242), (50, 120, 85)),
        ((730, 250, 1020, 410), "字段候选\n证据构建", (250, 245, 226), (150, 115, 35)),
        ((1090, 250, 1390, 410), "JSON Schema\n约束抽取", (242, 237, 250), (110, 80, 150)),
        ((1460, 250, 1730, 410), "安全规则\n一致性校验", (252, 237, 237), (155, 75, 75)),
    ]
    for xy, text, fill, outline in boxes:
        rounded_box(draw, xy, text, fill=fill, outline=outline)
    for a, b in zip(boxes[:-1], boxes[1:]):
        arrow(draw, (a[0][2] + 10, 330), (b[0][0] - 10, 330))

    rounded_box(draw, (1120, 590, 1445, 750), "视觉大模型\n复核", fill=(235, 245, 250), outline=(55, 105, 145))
    rounded_box(draw, (1500, 590, 1730, 750), "可信结果 /\n人工审核", fill=(237, 247, 239), outline=(55, 125, 70))
    draw.text((1145, 500), "低置信度或规则冲突", font=font(26), fill=(90, 90, 90))
    arrow(draw, (1595, 425), (1370, 575))
    arrow(draw, (1455, 670), (1490, 670))
    arrow(draw, (1595, 425), (1615, 575))
    draw.text((55, 825), "输出包含：字段值、证据文本、页码/坐标、置信度、规则状态及错误转移标签", font=font(25), fill=(70, 70, 70))
    img.save(path, quality=95)


def make_error_transition_figure(path: Path):
    img = Image.new("RGB", (1800, 980), "white")
    draw = ImageDraw.Draw(img)
    draw.text((70, 40), "人工真值—OCR—LLM逐字段错误转移评价", font=font(42, bold=True), fill=(20, 36, 55))

    inputs = [
        ((90, 170, 460, 330), "人工真值 G\n字段值 + 原文证据", (235, 243, 250), (60, 110, 150)),
        ((715, 170, 1085, 330), "OCR基线 O\nOCR + 规则字段值", (236, 247, 242), (50, 120, 85)),
        ((1340, 170, 1710, 330), "LLM结果 L\n字段值 + 证据坐标", (250, 245, 226), (150, 115, 35)),
    ]
    for xy, text, fill, outline in inputs:
        rounded_box(draw, xy, text, fill=fill, outline=outline)

    rounded_box(
        draw,
        (570, 410, 1230, 545),
        "规范化与逐字段对齐\n空值、格式、等价值统一",
        fill=(242, 237, 250),
        outline=(110, 80, 150),
    )
    for x in (275, 900, 1525):
        arrow(draw, (x, 345), (x + (900 - x) * 0.72, 395))

    labels = [
        ("正确保持", (60, 650, 315, 790), (232, 246, 235), (55, 125, 70)),
        ("成功修复", (345, 650, 600, 790), (228, 243, 250), (55, 105, 145)),
        ("修复失败", (630, 650, 885, 790), (252, 244, 226), (155, 115, 35)),
        ("新增错误", (915, 650, 1170, 790), (252, 237, 237), (155, 75, 75)),
        ("字段遗漏", (1200, 650, 1455, 790), (246, 239, 234), (150, 90, 55)),
        ("内容虚构", (1485, 650, 1740, 790), (247, 232, 240), (145, 65, 105)),
    ]
    for text, xy, fill, outline in labels:
        rounded_box(draw, xy, text, fill=fill, outline=outline)
        arrow(draw, (900, 560), ((xy[0] + xy[2]) / 2, 635), width=3)

    draw.text(
        (70, 890),
        "汇总指标：纠错率、破坏率、遗漏率、虚构率、关键字段加权纠错率与净纠错收益",
        font=font(27),
        fill=(70, 70, 70),
    )
    img.save(path, quality=95)


def make_pretest_figure(path: Path):
    img = Image.new("RGB", (1400, 760), "white")
    draw = ImageDraw.Draw(img)
    draw.text((70, 35), "开发阶段历史结果的结构稳定性", font=font(42, bold=True), fill=(20, 36, 55))
    chart_left, chart_top, chart_bottom = 170, 150, 640
    draw.line((chart_left, chart_top, chart_left, chart_bottom), fill=(70, 70, 70), width=3)
    draw.line((chart_left, chart_bottom, 1280, chart_bottom), fill=(70, 70, 70), width=3)
    for value in range(0, 101, 20):
        y = chart_bottom - int((chart_bottom - chart_top) * value / 100)
        draw.line((chart_left, y, 1280, y), fill=(225, 225, 225), width=2)
        draw.text((80, y - 18), str(value), font=font(24), fill=(80, 80, 80))
    data = [("JSON可解析率", 100, (61, 119, 180)), ("固定Schema完全遵循率", 50, (214, 92, 92))]
    xs = [380, 890]
    for x, (label, value, color) in zip(xs, data):
        bar_h = int((chart_bottom - chart_top) * value / 100)
        draw.rounded_rectangle((x, chart_bottom - bar_h, x + 250, chart_bottom), radius=8, fill=color)
        val = f"{value}%"
        val_box = draw.textbbox((0, 0), val, font=font(34, bold=True))
        draw.text((x + 125 - (val_box[2] - val_box[0]) / 2, chart_bottom - bar_h - 55), val, font=font(34, bold=True), fill=color)
        label_box = draw.textbbox((0, 0), label, font=font(26))
        draw.text((x + 125 - (label_box[2] - label_box[0]) / 2, chart_bottom + 28), label, font=font(26), fill=(35, 35, 35))
    draw.text((70, 708), "注：基于8份历史保存结果，仅用于识别问题，不作为正式主实验结论。", font=font(23), fill=(95, 95, 95))
    img.save(path, quality=95)


def add_figure(doc: Document, image_path: Path, caption: str, width_cm: float):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    inline = run.add_picture(str(image_path), width=Cm(width_cm))
    doc_pr = inline._inline.docPr
    doc_pr.set("descr", caption)
    cap = doc.add_paragraph(style="Caption")
    r = cap.add_run(caption)
    set_run_font(r, east_asia="宋体", ascii_font="Times New Roman", size=9)


def add_references(doc: Document, refs: Iterable[str]):
    for ref in refs:
        p = doc.add_paragraph(style="Reference")
        r = p.add_run(ref)
        set_run_font(r, size=8.5)


def build_document():
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    architecture_path = ASSET_DIR / "figure1_architecture.png"
    pretest_path = ASSET_DIR / "figure2_pretest.png"
    error_transition_path = ASSET_DIR / "figure3_error_transition.png"
    make_architecture_figure(architecture_path)
    make_pretest_figure(pretest_path)
    make_error_transition_figure(error_transition_path)

    doc = Document()
    configure_styles(doc)
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    section.header_distance = Cm(1.25)
    section.footer_distance = Cm(1.25)

    header = section.header
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = hp.add_run("面向电力工作票的可追溯OCR—大语言模型结构化抽取与错误转移评价（初稿）")
    set_run_font(hr, east_asia="宋体", ascii_font="Times New Roman", size=8, color=MUTED)
    footer = section.footer
    add_page_number(footer.paragraphs[0])

    # Compact academic adaptation of the editorial_cover title pattern.
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run("面向电力工作票的可追溯OCR—大语言模型\n结构化抽取与错误转移评价")
    set_run_font(r, east_asia="黑体", ascii_font="Arial", size=18, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(5)
    r = p.add_run("Traceable OCR–LLM Structured Extraction and Error-Transition Evaluation for Electrical Work Tickets")
    set_run_font(r, east_asia="宋体", ascii_font="Times New Roman", size=10.5, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("匿名审稿初稿 · 实验待补版 · 2026年7月")
    set_run_font(r, east_asia="宋体", ascii_font="Times New Roman", size=9, color=MUTED)

    note = add_body(
        doc,
        "初稿说明：本文基于现有工作票识别原型形成。当前开发目录中的38个上传文件经内容去重后仅对应7份不同样本，尚不足以支撑正式投稿。正文完整给出研究问题、方法和实验协议；开发阶段预实验采用真实历史记录，主实验结果不作虚构。投稿前应以脱敏后的独立数据集补齐第5节相关结果。",
        style="DraftNote",
    )
    shade_paragraph(note)

    p = doc.add_paragraph(style="Abstract")
    r = p.add_run("摘  要：")
    set_run_font(r, east_asia="黑体", ascii_font="Arial", size=9.5, bold=True)
    r = p.add_run(
        "针对电力工作票版式复杂、设备编号相似以及通用大模型抽取结果易发生字段漂移和无依据生成的问题，提出一种可追溯的OCR—大语言模型结构化抽取与错误转移评价方法。该方法利用PPStructureV3获取文本、表格与空间位置，以固定JSON Schema生成字段值、来源证据和不确定性标记，并通过时间顺序、人员数量、设备台账及安全措施对应关系等确定性规则实施风险校验。在评价层面，本文对人工真值、OCR基线字段与LLM字段进行逐字段对齐，构建正确保持、成功修复、修复失败、新增错误、字段遗漏和内容虚构六类错误转移矩阵，进一步设计纠错率、破坏率、虚构率、关键字段加权纠错率和净纠错收益，用于区分LLM的真实补偿作用与新增风险。开发阶段8份历史结果均可解析为JSON，但仅50%完全遵循固定字段schema，说明仅依赖提示词难以满足安全敏感业务的稳定性要求。本文给出可在独立脱敏数据集上复现的对比、消融和风险评价协议，主实验数值将在完成正式标注后补齐。"
    )
    set_run_font(r, size=9.5)

    p = doc.add_paragraph(style="Keywords")
    r = p.add_run("关键词：")
    set_run_font(r, east_asia="黑体", ascii_font="Arial", size=9.5, bold=True)
    r = p.add_run("电力工作票；OCR；大语言模型；错误转移；关键字段；风险评价")
    set_run_font(r, size=9.5)

    p = doc.add_paragraph(style="Abstract")
    r = p.add_run("Abstract: ")
    set_run_font(r, east_asia="宋体", ascii_font="Times New Roman", size=9.5, bold=True)
    r = p.add_run(
        "Electrical work tickets contain dense tables, similar device identifiers, long safety instructions, and strict cross-field dependencies. OCR errors may propagate into structured records, while large language models can both repair noisy text and introduce unsupported values. This paper proposes a traceable OCR–LLM extraction and error-transition evaluation method. PPStructureV3 obtains text, table, and spatial evidence; constrained generation produces normalized fields with evidence coordinates; and deterministic rules verify temporal order, personnel counts, device ledgers, and safety-measure consistency. Human ground truth, OCR baseline fields, and LLM outputs are aligned at field level to form six mutually exclusive transitions: correct preservation, successful repair, repair failure, introduced error, omission, and hallucination. Repair, damage, omission, hallucination, critical-field-weighted repair, and net correction gain are defined to quantify both benefit and risk. In eight historical development outputs, all responses were JSON-parseable while only 50% fully conformed to the fixed schema. The paper therefore presents a reproducible protocol whose formal numerical results will be completed on an independently annotated, de-identified dataset."
    )
    set_run_font(r, size=9.5)

    p = doc.add_paragraph(style="Keywords")
    r = p.add_run("Keywords: ")
    set_run_font(r, east_asia="宋体", ascii_font="Times New Roman", size=9.5, bold=True)
    r = p.add_run("electrical work ticket; optical character recognition; large language model; error transition; critical field; risk evaluation")
    set_run_font(r, size=9.5)

    add_heading(doc, "1 引言", 1)
    for text in [
        "工作票是发电厂、变电站和输配电检修作业中组织措施与安全措施的重要载体。票面通常同时包含人员、时间、工作地点、设备双重编号、停电范围、接地措施、许可与终结签名等内容，各字段之间存在严格的业务逻辑。依据电力安全工作规程，工作许可、工作间断、延期和终结等环节需要保持可追溯的一致性[24]。因此，工作票数字化不仅要求识别文字，还要求恢复表格关系、保留证据来源并识别潜在冲突。",
        "传统OCR系统在规则清晰、版式固定的文档上具有较高效率。PP-OCR系列通过轻量化检测与识别网络降低了部署成本[1-2]，版面分析工具能够进一步恢复标题、文本块和表格区域。然而，工作票常见跨栏表格、红黑双色文字、扫描噪声、印章、空白签名线及相似设备编号，单纯依赖OCR字符结果和正则规则容易产生字段错位。尤其是安全措施往往跨越多个表格行，脱离版面关系后难以判断措施对象与执行状态。",
        "LayoutLM、LayoutLMv2和LayoutLMv3将文本、视觉与二维位置联合建模[3-5]，DocFormer、StrucTexT和Donut等模型进一步推动了多模态文档理解[6-8]。这些方法在公开表单、票据和问答数据集上取得了良好效果，但通常依赖大规模标注数据或固定任务训练。对模板类型多、样本受隐私限制且业务规则强的电力工作票而言，直接训练专用模型的成本较高。",
        "大语言模型具备较强的语义归纳和少样本抽取能力[16-20]，可以将OCR结果整理为结构化字段，但提示词并不能保证输出始终符合固定schema。当输入包含OCR错误或证据缺失时，模型还可能根据常识补全不存在的信息。开发阶段历史记录印证了这一问题：8份输出均能被JSON解析，但仅4份完整遵守当前25字段结构。由于这些输出来自不同开发阶段和提示词版本，该比例不能作为模型能力的最终评价，却足以说明工程链路缺少确定性的结构约束。更重要的是，仅比较OCR置信度与最终准确率的相关性，不能直接证明LLM修复了多少OCR错误；必须观察同一字段从OCR阶段到LLM阶段的状态变化。",
        "为此，本文提出EWT-Guard框架，将工作票识别重新定义为“证据支持的结构化抽取、一致性校验与错误转移评价”问题。方法不直接要求模型从完整OCR文本中自由生成答案，而是先围绕目标字段构建候选证据，再进行受约束的结构化生成，并利用电力规则计算可信度和拒答条件；评价模块进一步对人工真值、OCR基线和LLM结果进行逐字段对齐，分别记录被修复的错误和由LLM新引入的风险。",
        "本文主要贡献如下。第一，构建面向电力工作票的统一字段schema与证据表示，使人员、时间、设备、安全措施和签名等结果可以追溯到原始页面位置。第二，提出人工真值—OCR—LLM三层对齐及六类错误转移矩阵，定量区分正确保持、成功修复、修复失败、新增错误、字段遗漏和内容虚构。第三，面向设备编号、安全措施等安全关键字段设计风险权重、加权纠错率与净纠错收益，并结合确定性业务规则和人工复核机制评价系统的可用边界。",
    ]:
        add_body(doc, text)

    add_heading(doc, "2 相关工作", 1)
    add_heading(doc, "2.1 OCR与文档版面分析", 2)
    for text in [
        "现代OCR通常由文本检测、方向校正、文字识别和后处理组成。PP-OCR及其后续版本通过可微分二值化、轻量骨干网络和数据增强等策略兼顾速度与精度[1-2]。在复杂文档场景中，仅获得按行排列的文字仍不足以支撑字段抽取。PubLayNet等数据集推动了标题、正文、列表、表格和图像区域的版面检测研究[9]，PubTables-1M及CascadeTabNet则聚焦表格检测和结构恢复[13-14]。工作票与普通票据的差异在于表格单元格跨度大、操作项具有顺序关系，并且空白与签名线本身也具有业务含义。",
    ]:
        add_body(doc, text)
    add_heading(doc, "2.2 多模态文档信息抽取", 2)
    for text in [
        "FUNSD、CORD和DocVQA等数据集分别覆盖表单语义实体、票据解析与视觉问答[10-12]。LayoutLM将二维坐标引入预训练语言模型[3]，LayoutLMv2和LayoutLMv3进一步融合图像特征并统一文本与图像掩码学习[4-5]。DocFormer通过多模态自注意力联合编码视觉、文本和空间特征[6]，StrucTexT强调实体与结构之间的关联[7]。Donut采用无OCR的端到端Transformer生成文档结构[8]，Nougat则展示了生成式文档理解在复杂学术页面中的能力[15]。这些方法为工作票理解提供了技术基础，但公开数据集与电力工作票在字段语义、风险等级和业务约束上存在明显域差异。",
    ]:
        add_body(doc, text)
    add_heading(doc, "2.3 大语言模型结构化抽取与可信性", 2)
    for text in [
        "统一信息抽取方法通过结构生成将实体、关系和事件任务转化为统一输出[16]。大规模预训练语言模型表现出少样本和指令跟随能力[17-19]，思维链和自一致性策略可增强复杂推理[20-21]。但生成式模型存在事实性错误和幻觉问题，SelfCheckGPT等工作尝试通过采样一致性检测无依据生成[22]。在安全敏感文档中，仅报告平均准确率不足以说明系统可用性，还需要考虑概率校准、选择性预测和拒答机制[23,25]。",
        "Wen将PaddleOCR与DeepSeek结合用于植物标本标签抽取，并以OCR置信度与最终准确率的弱相关性解释LLM的补偿作用[26]。该工作证明了OCR—LLM串联流程的应用潜力，但相关性不能直接区分LLM成功修复、保持错误或新增错误。对于设备编号、安全措施等错误代价不对称的工作票字段，需要建立逐字段错误转移和风险加权评价。",
        "现有研究往往将OCR、文档抽取和规则校验视为独立环节，也较少同时报告LLM的纠错收益与新增风险。本文的核心区别在于：抽取结果必须携带可定位证据，结构约束与业务规则同时参与结果判定，并通过人工真值—OCR—LLM三层对齐量化系统在每个字段上的状态转移。",
    ]:
        add_body(doc, text)

    add_heading(doc, "3 EWT-Guard方法", 1)
    add_heading(doc, "3.1 问题定义", 2)
    for text in [
        "给定工作票文档D，OCR与版面分析模块输出元素集合O={o_i}。每个元素o_i由文本t_i、边界框b_i、页码p_i、版面类型l_i和OCR置信度c_i组成。目标字段集合记为F={f_j}，包含人员、时间、设备、工作内容、安全措施和流程签名等类别。系统需要为每个字段生成规范化取值v_j、证据集合E_j、不确定度u_j和校验状态r_j。",
        "与普通键值抽取不同，本文要求满足两个条件：其一，非空字段必须能够映射到原文证据；其二，字段组合必须通过schema约束和业务规则。若证据不足或规则冲突，系统输出不确定标记，而不是根据语言常识补全。",
    ]:
        add_body(doc, text)
    add_equation(doc, "y_j = (v_j, E_j, u_j, r_j),  E_j ⊆ O", 1)

    add_heading(doc, "3.2 总体框架", 2)
    add_body(doc, "如图1所示，EWT-Guard由版面与OCR解析、字段候选证据构建、Schema约束抽取、安全规则校验以及低置信度复核五部分组成。主路径优先利用OCR结构以降低视觉模型调用成本；当证据冲突、OCR置信度过低或规则校验失败时，系统将原始图像及局部区域发送给视觉大模型复核，仍不能确认的字段进入人工审核。")
    add_figure(doc, architecture_path, "图1  EWT-Guard总体框架", 15.8)

    add_heading(doc, "3.3 工作票领域schema与证据表示", 2)
    add_body(doc, "结合当前原型，领域schema包含25个顶层字段。为避免不同模型产生中文字段、驼峰字段或自定义字段，所有响应均先通过JSON Schema和Pydantic模型校验。字段值采用统一的数据类型，时间字段规范为ISO 8601或明确的中文标准格式，人员与措施采用数组，缺失信息使用null而非空字符串。")
    add_table(
        doc,
        "表1  工作票核心字段及证据约束示例",
        ["字段类别", "代表字段", "类型", "证据要求", "主要校验规则"],
        [
            ["票面标识", "ticket_type、ticket_no", "字符串", "标题区、编号区", "编号格式与票种匹配"],
            ["人员组织", "work_leader、work_members", "字符串/数组", "人员栏及签名栏", "名单数量与总人数一致"],
            ["时间流程", "planned_start_time等", "时间", "计划、许可、终结区域", "开始≤许可≤终结"],
            ["任务设备", "work_location、work_content", "字符串", "任务栏、地点栏", "电压等级和设备编号一致"],
            ["安全措施", "safety_measures、grounding_measures", "数组", "措施表格及执行栏", "应执行项与已执行项对应"],
            ["签名许可", "issuer、permit_person、signatures", "对象/数组", "签名线与时间邻域", "流程角色和阶段完整"],
            ["可信信息", "uncertain_fields、source_evidence", "数组/对象", "页码、bbox、OCR原文", "非空结果必须有证据"],
        ],
        [1050, 1800, 900, 2600, 2722],
    )
    add_body(doc, "证据对象至少包含page、bbox、text、ocr_confidence和source_type。对于表格字段，还需保存row、column和table_id；对于跨行安全措施，允许一个字段对应多个证据片段。证据表示既用于模型输入，也用于结果审计和人工复核。")

    add_heading(doc, "3.4 字段候选证据构建", 2)
    for text in [
        "当前原型将Markdown和截断后的JSON整体拼接给模型，长表格可能导致关键证据被无差别淹没。本文改为以字段定义为查询，综合语义相似度、版面邻近度和领域词典匹配度检索候选区域。对字段f_j与候选证据e_i，其综合得分定义为：",
    ]:
        add_body(doc, text)
    add_equation(doc, "S(e_i,f_j)=λ₁S_sem+λ₂S_layout+λ₃S_lex+λ₄S_conf", 2)
    add_body(doc, "其中S_sem表示字段描述与证据文本的语义相关度，S_layout表示候选区域与字段标签的空间关系，S_lex表示设备编号、时间词和角色词典匹配度，S_conf为OCR置信度。权重λ在验证集上确定。每个字段保留前K个候选片段，并将相邻的表格单元格、行标题及页码信息一并提供给模型。")

    add_heading(doc, "3.5 Schema约束结构化生成", 2)
    for text in [
        "约束生成模块的输入由任务说明、字段定义、候选证据和JSON Schema组成。模型只能从候选证据复制或规范化字段值，不允许输出schema之外的键。生成后首先进行语法解析和类型检查；失败时采用同一证据执行有限次数的修复提示，而不是重新读取完整文档。",
        "对时间、人数和设备编号采用确定性后处理。时间规范化保留原文与标准值，避免将缺失年份擅自补齐；设备编号保留大小写和连字符，同时输出去空格后的比较形式；人员字段通过中文姓名边界和签名邻域判断，禁止把说明文字识别为人员。",
    ]:
        add_body(doc, text)

    add_heading(doc, "3.6 规则校验、置信度与选择性复核", 2)
    for text in [
        "业务规则分为字段级、跨字段和流程级三类。字段级规则验证类型、格式和证据存在性；跨字段规则检查工作负责人是否出现在相关签名区域、人员数量是否与名单一致、工作地点与工作内容中的设备信息是否冲突；流程级规则检查计划、许可、终结时间顺序以及应执行措施与已执行措施之间的对应关系。规则应由电力专业人员确认，模型不得自行创造安全规则。",
        "字段综合置信度由OCR质量、语义匹配、规则通过情况和OCR—视觉模型一致性共同决定：",
    ]:
        add_body(doc, text)
    add_equation(doc, "C_j=αC_ocr+βC_sem+γC_rule+δC_agree", 3)
    add_body(doc, "当C_j低于阈值τ，或出现高风险规则冲突时，系统触发局部视觉复核；若复核结果与OCR证据仍不一致，则保留两个候选值并标记为需要人工审核。该机制将系统目标从“强制给出答案”调整为“在可验证时自动确认”。")

    add_heading(doc, "3.7 可追溯错误转移评价", 2)
    for text in [
        "为避免以OCR内部置信度替代真实识别质量，本文对每个目标字段同时保存人工真值g_j、OCR加规则得到的基线字段o_j和LLM结构化字段l_j。比较前先执行全半角、空格、日期格式、人员分隔符和设备编号连接符等确定性规范化；对于安全措施等列表字段，按条目匹配而非整段字符串匹配。每个非空结果还需关联页码、边界框和原文片段，从而支持回看原图。",
        "六类状态采用固定优先级判定，以保证同一字段只进入一个类别：当真值为空而LLM非空时记为内容虚构；当真值非空而LLM为空时记为字段遗漏；其余情况下，OCR与LLM均正确记为正确保持，OCR错误而LLM正确记为成功修复，OCR正确而LLM错误记为新增错误，二者均错误记为修复失败。真值和LLM均为空时记录为空字段正确保持，不计入六类风险转移。",
    ]:
        add_body(doc, text)
    add_figure(doc, error_transition_path, "图2  人工真值—OCR—LLM逐字段错误转移评价流程", 15.8)
    add_table(
        doc,
        "表2  六类错误转移的判定规则",
        ["类别", "人工真值G", "OCR基线O", "LLM结果L", "含义"],
        [
            ["正确保持", "存在", "正确", "正确", "LLM保持OCR已正确字段"],
            ["成功修复", "存在", "错误/缺失", "正确", "LLM恢复真实字段值"],
            ["修复失败", "存在", "错误", "错误且非空", "LLM未消除OCR错误"],
            ["新增错误", "存在", "正确", "错误且非空", "LLM破坏原本正确结果"],
            ["字段遗漏", "存在", "任意", "空", "LLM未输出应有字段"],
            ["内容虚构", "不存在", "任意", "非空", "LLM生成无原文依据内容"],
        ],
        [1350, 1400, 1700, 1700, 2922],
    )
    add_body(doc, "设N_rep、N_new、N_omit和N_hall分别表示成功修复、新增错误、字段遗漏和内容虚构数量，则普通纠错率以OCR阶段错误字段为分母，破坏率以OCR阶段正确字段为分母；遗漏率和虚构率分别以真值存在字段及真值为空字段为分母。与单一最终准确率相比，这组指标能够同时呈现LLM带来的收益和风险。")
    add_equation(doc, "RR = N_rep / N_OCR_error,   DR = N_new / N_OCR_correct", 4)
    add_body(doc, "考虑错误后果不对称，本文将设备编号、安全措施和工作地点设为高风险字段，权重为3；人员与时间设为中风险字段，权重为2；一般描述性字段权重为1。权重由业务规范和专家确认，并使用1:2:3与1:3:5两组方案开展敏感性分析。关键字段加权纠错率WCR和净纠错收益WNG定义为：")
    add_equation(doc, "WCR = Σ_j w_j I(O_j错误,L_j正确) / Σ_j w_j I(O_j错误)", 5)
    add_equation(doc, "WNG = Σ_j w_j [I(L_j正确)-I(O_j正确)] / Σ_j w_j", 6)
    add_body(doc, "WNG大于0表示LLM带来的加权修复收益超过其新增错误，等于0表示收益与损失相抵，小于0则说明在当前字段权重下引入LLM反而增加了总体风险。由于该指标依赖权重设定，论文应同时报告未加权结果和权重敏感性分析，避免用主观权重制造结论。")

    add_heading(doc, "4 原型系统实现", 1)
    add_heading(doc, "4.1 系统架构", 2)
    for text in [
        "现有原型采用FastAPI提供后端服务，前端支持结构化识别和图片直传两种模式。结构化识别路径调用PPStructureV3生成JSON与Markdown，再由文本大模型整理为固定字段；图片直传路径将图像编码为Data URL并调用视觉大模型。系统通过Server-Sent Events返回文件接收、OCR、首字等待和模型生成等阶段事件。",
        "原型保留每次任务的输入文件、OCR中间结果、模型原始输出、解析后的JSON和时延信息，为实验复现与错误分析提供基础。当前实现已经证明完整链路可运行，但证据对象、强制schema和规则引擎尚需按照第3节方案补充。",
    ]:
        add_body(doc, text)
    add_heading(doc, "4.2 开发环境与模型配置", 2)
    add_table(
        doc,
        "表3  当前原型开发环境",
        ["组件", "版本或配置", "用途"],
        [
            ["操作系统", "Windows 11", "开发与测试"],
            ["Python", "3.13.5", "后端运行环境"],
            ["FastAPI / httpx", "0.115.6 / 0.28.1", "接口与异步模型调用"],
            ["PaddleOCR / PaddlePaddle", "3.7.0 / 3.0.0（CPU）", "PPStructureV3版面与OCR"],
            ["文本模型", "DeepSeek V4 Flash，temperature=0.1", "OCR结果结构化"],
            ["视觉模型", "Qwen 3.7 Plus", "原图识别与后续复核"],
            ["GPU", "NVIDIA GeForce GTX 1650 4 GB", "当前OCR未使用GPU版本"],
        ],
        [1800, 3300, 3972],
    )
    add_body(doc, "正式实验应冻结操作系统、模型版本、提示词版本和依赖文件，并在同一硬件环境重复运行。远程大模型需要记录接口日期、温度、最大输出长度和失败重试次数。对于随机性实验，建议在固定测试子集上重复3次并报告均值和标准差。")
    add_heading(doc, "4.3 工程可靠性与隐私", 2)
    add_body(doc, "工作票包含人员姓名、设备位置和运行信息，数据收集、日志和论文样例均需脱敏。正式系统应限制文件大小和扩展名，避免在健康接口中返回密钥片段，禁止将完整异常堆栈发送给前端，并对上传文件设置访问控制和保留期限。网络调用应采用连接复用、超时分类、指数退避重试和结果缓存。上述措施不直接构成算法创新，但决定了系统能否在真实业务环境中安全使用。")

    add_heading(doc, "5 实验设计与开发阶段预实验", 1)
    add_heading(doc, "5.1 数据集与标注协议", 2)
    for text in [
        "考虑一个月研究周期，正式研究以200至300份脱敏工作票为可执行目标，覆盖不少于4类模板，并有意识纳入清晰印刷、印刷与手写混合、倾斜模糊和低对比度样本。先以20%的开发集确定字段规范、提示词和校验规则，其余80%锁定为独立测试集；同一票据的副本或增强版本不得跨集合分配。若样本允许，可从测试集中单列未见模板子集评价跨模板泛化。",
        "标注对象聚焦票号、人员、工作地点、设备编号、计划起止时间、工作内容和安全措施等8至10个核心字段，并保存字段原始证据、页码与边界框。随机选择至少20%的样本由第二名标注人员独立复核，单值字段报告一致率，人员和安全措施等列表字段报告条目级F1或Cohen's Kappa。分歧由具备电力业务知识的人员确认。相较一次性标注全部25个字段，该方案更适合在有限周期内获得可靠真值。",
    ]:
        add_body(doc, text)
    add_table(
        doc,
        "表4  正式数据集统计表（主实验完成后填写）",
        ["数据子集", "独立票据数", "页数", "模板数", "低质量图像占比", "用途"],
        [
            ["开发集", "—", "—", "—", "—", "提示词、规则与权重开发"],
            ["测试集", "—", "—", "—", "—", "总体性能评价"],
            ["未见模板子集", "—", "—", "—", "—", "测试集内的跨模板泛化"],
        ],
        [1450, 1250, 900, 900, 1700, 2872],
    )

    add_heading(doc, "5.2 对比方法与评价指标", 2)
    add_body(doc, "为控制一个月内的实现范围，对比方法设置为：B1为PPStructureV3加关键词与正则规则，作为传统基线；B2为PPStructureV3加普通LLM提示词；B3为OCR—LLM加确定性校验规则，即本文完整方法；B4在50份困难样本上以人工校正文本输入LLM，作为解析能力上限。OCR+NER需要额外序列标注和模型训练，本研究将其作为相关工作而不纳入主实验。所有方法使用相同测试票据和字段规范。")
    add_table(
        doc,
        "表5  评价指标及其含义",
        ["评价层面", "指标", "说明"],
        [
            ["OCR质量", "CER", "字符级编辑距离，评估文字识别误差"],
            ["单值字段", "Normalized EM、字符F1", "时间、姓名和编号规范化后评价"],
            ["列表字段", "Precision、Recall、F1", "人员与安全措施按条目匹配"],
            ["总体抽取", "Micro-F1、Macro-F1", "兼顾高频与低频字段"],
            ["结构稳定性", "Schema合法率", "是否完全满足字段和类型约束"],
            ["可信性", "证据支持率、幻觉率", "值能否被原始证据支持"],
            ["错误补偿", "纠错率、破坏率", "LLM修复OCR错误及新增错误的比例"],
            ["关键字段风险", "WCR、WNG", "按字段风险权重汇总纠错收益与损失"],
            ["规则能力", "冲突检测F1", "业务矛盾识别准确性"],
            ["效率", "P50/P95时延、成本/页", "分别报告冷启动和预热结果"],
        ],
        [1500, 2500, 5072],
    )

    add_heading(doc, "5.3 开发阶段预实验", 2)
    for text in [
        "截至2026年7月20日，开发目录包含38个上传文件。按文件内容哈希去重后，仅有7份不同内容，其中包括复杂双页第一种工作票、单页第二种工作票、密集安全措施表格以及小型测试图像。系统保存了8份可解析的LLM结构化结果。",
        "对历史结果的schema键进行检查发现，8份结果均可解析为JSON，4份完整包含当前定义的25个顶层字段，另外4份分别采用中文字段、自定义英文下划线字段或驼峰字段。需要强调的是，这些结果可能来自不同提示词版本，因此不能将50%的完全遵循率解释为某一固定模型的统计性能；其作用是证明现有原型缺少阻止schema漂移的硬约束。",
    ]:
        add_body(doc, text)
    add_figure(doc, pretest_path, "图3  开发阶段历史结果的结构稳定性", 14.8)
    add_table(
        doc,
        "表6  一次冷启动任务的阶段耗时",
        ["阶段", "耗时/ms", "占总时延比例", "说明"],
        [
            ["文件接收", "31.64", "0.02%", "上传保存"],
            ["OCR流水线加载", "124630.67", "61.87%", "首次加载模型"],
            ["OCR预测", "61649.26", "30.61%", "单页预测"],
            ["LLM首字等待", "10333.17", "5.13%", "网络与推理等待"],
            ["LLM流式生成", "4474.92", "2.22%", "收到首字后的生成"],
            ["端到端总耗时", "201427.90", "100%", "约201.43秒"],
        ],
        [1850, 1550, 1700, 3972],
    )
    add_body(doc, "该记录表明冷启动的主要瓶颈来自OCR流水线加载，而不是LLM生成。正式实验应先执行固定次数预热，再分别报告冷启动与热启动时延，并对模型下载、磁盘缓存和网络波动进行隔离。单次时延不能用于显著性结论。")

    add_heading(doc, "5.4 主实验与消融实验报告方案", 2)
    add_body(doc, "主实验完成后，应在同一测试集和字段规范下填充表7。每个模型使用相同OCR结果或明确说明输入差异。除了总体F1，还需同时报告Schema合法率、证据支持率、幻觉率、加权纠错率和净纠错收益，防止高平均准确率掩盖少量高风险错误。")
    add_table(
        doc,
        "表7  主实验结果表（正式投稿前填写）",
        ["方法", "Macro-F1", "Micro-F1", "Schema合法率", "纠错率", "破坏率", "WNG"],
        [
            ["B1 OCR+规则", "—", "—", "—", "—", "—", "—"],
            ["B2 OCR+普通LLM", "—", "—", "—", "—", "—", "—"],
            ["B3 OCR+LLM+校验规则", "—", "—", "—", "—", "—", "—"],
            ["B4 人工文本+LLM（困难子集）", "—", "—", "—", "—", "—", "—"],
        ],
        [1750, 1050, 1050, 1350, 1350, 1200, 1322],
    )
    add_body(doc, "消融实验优先比较普通提示词、增加JSON Schema、增加原文证据、增加确定性业务规则四种设置。预计Schema约束主要影响结构合法率，证据约束主要影响内容虚构和字段错位，规则校验主要降低跨字段矛盾。上述判断属于待检验假设，不能在正式结果产生前写成已验证结论。")
    add_body(doc, "鲁棒性实验可对独立测试样本施加高斯模糊、±5°旋转、低亮度、低对比度和JPEG压缩。增强图像只用于同一原图上的性能退化曲线，不能计入独立样本数量。统计检验采用配对bootstrap获得95%置信区间；对字段正确/错误的配对结果，可使用McNemar检验分析差异显著性。")

    add_heading(doc, "5.5 错误转移与关键字段风险分析", 2)
    add_body(doc, "主实验应将每个测试字段映射到第3.7节的唯一状态，并按字段类别汇总。表8既报告数量，也报告以对应机会数为分母的比例，避免把大量正确保持样本混入纠错率分母。设备编号、安全措施和工作地点应单独列出，因为这些字段的平均数量可能不高，但错误后果显著高于一般描述字段。")
    add_table(
        doc,
        "表8  关键字段错误转移结果表（主实验完成后填写）",
        ["字段", "样本字段数", "成功修复", "修复失败", "新增错误", "字段遗漏", "内容虚构", "WNG"],
        [
            ["工作票号", "—", "—", "—", "—", "—", "—", "—"],
            ["人员", "—", "—", "—", "—", "—", "—", "—"],
            ["工作时间", "—", "—", "—", "—", "—", "—", "—"],
            ["工作地点", "—", "—", "—", "—", "—", "—", "—"],
            ["设备编号", "—", "—", "—", "—", "—", "—", "—"],
            ["安全措施", "—", "—", "—", "—", "—", "—", "—"],
        ],
        [1450, 1150, 1050, 1050, 1050, 1050, 1050, 1222],
    )
    add_body(doc, "若OCR置信度与最终准确率相关性较弱，只能说明二者线性关联有限，不能直接据此认定LLM具有补偿作用。本文以成功修复数量和加权净收益作为直接证据，并同时披露新增错误、遗漏和虚构。若LLM在低OCR质量组的成功修复率显著提高且破坏率保持较低，才能支持其具有稳健补偿能力的结论。")

    add_heading(doc, "5.6 有效性威胁", 2)
    for text in [
        "首先，工作票数据涉及隐私和运行安全，样本可能来自有限地区或有限模板，从而产生来源偏差。应报告模板、年份、成像方式和票种分布，并设置未见模板测试。其次，远程大模型会随服务版本更新，导致实验难以完全复现。应保存原始输入输出、模型标识、调用日期和参数。再次，业务规则依赖专家知识，规则本身可能不完整或存在地区差异，应对规则来源和适用范围进行说明。最后，开发阶段历史结果数量很少且提示词版本不统一，因此本文初稿仅将其用于问题发现，主结论必须建立在冻结版本后的独立主实验上。",
    ]:
        add_body(doc, text)

    add_heading(doc, "6 结论", 1)
    for text in [
        "本文面向电力工作票的可信结构化抽取需求，提出可追溯的OCR—大语言模型协同框架EWT-Guard。该方法通过字段证据、固定JSON Schema、业务规则校验与选择性复核，将传统“从OCR文本生成答案”的流程转化为“基于可定位证据生成并验证字段”的流程；同时通过人工真值—OCR—LLM三层对齐和六类错误转移矩阵，直接区分LLM的成功修复、修复失败、新增错误、遗漏与虚构。",
        "针对设备编号、安全措施等错误代价不对称的字段，本文进一步提出关键字段加权纠错率和净纠错收益，使评价目标从单纯追求平均准确率扩展为同时衡量纠错收益与安全风险。开发阶段历史结果揭示了现有提示词方案的schema漂移和冷启动开销问题，为方法设计提供了直接动机。",
        "当前稿件已经完成研究问题、方法框架、原型系统和实验协议设计，但正式结论仍需建立在独立脱敏数据集上。后续应完成核心字段与证据双层标注，冻结OCR、提示词、规则和模型版本，并依据统一测试集补齐基线、错误转移、权重敏感性、消融和鲁棒性实验。只有当成功修复率和加权净收益显著为正，且新增错误与内容虚构保持在可接受范围内，才能据此判断LLM是否适合进入工作票辅助审核流程。",
    ]:
        add_body(doc, text)

    add_heading(doc, "参考文献", 1)
    refs = [
        "[1] DU Y, LI C, GUO R, et al. PP-OCR: A Practical Ultra Lightweight OCR System[EB/OL]. arXiv:2009.09941, 2020.",
        "[2] TANG J, QIAO S, CUI B, et al. PP-OCRv3: More Attempts for the Improvement of Ultra Lightweight OCR System[EB/OL]. arXiv:2206.03001, 2022.",
        "[3] XU Y, LI M, CUI L, et al. LayoutLM: Pre-training of Text and Layout for Document Image Understanding[C]//Proceedings of KDD. 2020: 1192-1200.",
        "[4] XU Y, XU Y, LV T, et al. LayoutLMv2: Multi-modal Pre-training for Visually-rich Document Understanding[C]//Proceedings of ACL-IJCNLP. 2021: 2579-2591.",
        "[5] HUANG Y, LV T, CUI L, et al. LayoutLMv3: Pre-training for Document AI with Unified Text and Image Masking[C]//Proceedings of ACM Multimedia. 2022: 4083-4091.",
        "[6] APPALARAJU S, JASANI B, KOTA B U, et al. DocFormer: End-to-End Transformer for Document Understanding[C]//Proceedings of ICCV. 2021: 993-1003.",
        "[7] LI Y, QIAN Y, YU Y, et al. StrucTexT: Structured Text Understanding with Multi-Modal Transformers[C]//Proceedings of ACM Multimedia. 2021: 1912-1920.",
        "[8] KIM G, HONG T, YIM M, et al. OCR-free Document Understanding Transformer[C]//Proceedings of ECCV. 2022: 498-517.",
        "[9] ZHONG X, TANG J, YEPES A J. PubLayNet: Largest Dataset Ever for Document Layout Analysis[C]//Proceedings of ICDAR. 2019: 1015-1022.",
        "[10] JAUME G, EKENEL H K, THIRAN J P. FUNSD: A Dataset for Form Understanding in Noisy Scanned Documents[C]//Proceedings of ICDAR Workshops. 2019: 1-6.",
        "[11] PARK S, SHIN S, LEE B, et al. CORD: A Consolidated Receipt Dataset for Post-OCR Parsing[C]//Proceedings of ICDAR Workshops. 2019: 1-6.",
        "[12] MATHEW M, KARATZAS D, JAWAHAR C V. DocVQA: A Dataset for VQA on Document Images[C]//Proceedings of WACV. 2021: 2200-2209.",
        "[13] SMOCK B, PESALA R, ABRAHAM R. PubTables-1M: Towards Comprehensive Table Extraction from Unstructured Documents[C]//Proceedings of CVPR. 2022: 4634-4642.",
        "[14] PRASAD D, GADPAL A, KAPADNI K, et al. CascadeTabNet: An Approach for End to End Table Detection and Structure Recognition from Image-based Documents[C]//Proceedings of CVPR Workshops. 2020: 572-573.",
        "[15] BLECHER L, CUCURULL G, SCIALOM T, STOJNIC R. Nougat: Neural Optical Understanding for Academic Documents[C]//Proceedings of ICLR. 2024.",
        "[16] LU Y, LIU Q, DAI D, et al. Unified Structure Generation for Universal Information Extraction[C]//Proceedings of ACL. 2022: 5755-5772.",
        "[17] BROWN T, MANN B, RYDER N, et al. Language Models are Few-Shot Learners[C]//Advances in Neural Information Processing Systems. 2020, 33: 1877-1901.",
        "[18] OUYANG L, WU J, JIANG X, et al. Training Language Models to Follow Instructions with Human Feedback[C]//Advances in Neural Information Processing Systems. 2022, 35: 27730-27744.",
        "[19] OPENAI. GPT-4 Technical Report[EB/OL]. arXiv:2303.08774, 2023.",
        "[20] WEI J, WANG X, SCHUURMANS D, et al. Chain-of-Thought Prompting Elicits Reasoning in Large Language Models[C]//Advances in Neural Information Processing Systems. 2022, 35: 24824-24837.",
        "[21] WANG X, WEI J, SCHUURMANS D, et al. Self-Consistency Improves Chain of Thought Reasoning in Language Models[C]//Proceedings of ICLR. 2023.",
        "[22] MANAKUL P, Liusie A, Gales M J F. SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for Generative Large Language Models[C]//Proceedings of EMNLP. 2023.",
        "[23] GUO C, PLEISS G, SUN Y, WEINBERGER K Q. On Calibration of Modern Neural Networks[C]//Proceedings of ICML. 2017: 1321-1330.",
        "[24] 中华人民共和国国家质量监督检验检疫总局, 中国国家标准化管理委员会. GB 26860—2011 电力安全工作规程 发电厂和变电站电气部分[S]. 北京: 中国标准出版社, 2011.",
        "[25] GEIFMAN Y, EL-YANIV R. SelectiveNet: A Deep Neural Network with an Integrated Reject Option[C]//Proceedings of ICML. 2019: 2151-2159.",
        "[26] WEN J. Automated information extraction from plant specimen labels using OCR and large language models[J]. Biodiversity Data Journal, 2026, 14: e177202.",
    ]
    add_references(doc, refs)

    doc.add_page_break()
    add_heading(doc, "附录A  投稿前实验补全清单（投稿时删除）", 1)
    for text in [
        "A.1 数据：完成独立票据去重、脱敏、模板统计、训练/验证/测试划分和双人标注一致性分析。",
        "A.2 方法：冻结字段schema、证据格式、提示词、模型版本、规则库和置信度阈值。",
        "A.3 实验：补齐表4、表7和表8，完成总体对比、错误转移、权重敏感性、至少3项消融、图像退化及冷/热启动效率实验。",
        "A.4 写作：根据真实结果重写中英文摘要、5.4至5.5节和结论；核对2023—2026年相关文献及目标会议/期刊格式；删除初稿说明和本附录。",
        "A.5 合规：确认数据授权与脱敏，检查示例图片、设备位置和人员信息，补充伦理与数据可用性声明。",
    ]:
        add_body(doc, text)

    props = doc.core_properties
    props.title = "面向电力工作票的可追溯OCR—大语言模型结构化抽取与错误转移评价"
    props.subject = "匿名审稿初稿，实验待补版"
    props.author = "Anonymous"
    props.keywords = "工作票, OCR, 大语言模型, 错误转移, 关键字段, 风险评价"
    props.comments = "Generated as an evidence-based draft; formal experimental results are intentionally not fabricated."

    doc.save(OUTPUT_PATH)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    build_document()
