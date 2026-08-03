from __future__ import annotations

from docx.document import Document as DocumentObject
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from docx.table import Table, _Cell, _Row

DARK_BLUE = "1F4E78"
MID_BLUE = "D9EAF7"
LIGHT_BLUE = "EDF5FA"
LIGHT_GREY = "F2F4F5"
WARNING = "FFF2CC"
DANGER = "FCE4D6"
WHITE = "FFFFFF"


def configure_document(document: DocumentObject, page_size: str) -> None:
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    if page_size == "A3":
        section.page_width = Mm(420)
        section.page_height = Mm(297)
    else:
        section.page_width = Mm(297)
        section.page_height = Mm(210)
    section.top_margin = Mm(10)
    section.bottom_margin = Mm(10)
    section.left_margin = Mm(10)
    section.right_margin = Mm(10)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Liberation Sans"
    normal.font.size = Pt(9)
    normal.paragraph_format.space_after = Pt(3)
    normal.paragraph_format.line_spacing = 1.0
    for style_name, size in (("Title", 18), ("Heading 1", 14), ("Heading 2", 11)):
        style = styles[style_name]
        style.font.name = "Liberation Sans"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = None


def set_cell_shading(cell: _Cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), fill)


def set_cell_margins(cell: _Cell, top: int = 45, start: int = 45, bottom: int = 45, end: int = 45) -> None:
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        element = margins.find(qn(f"w:{name}"))
        if element is None:
            element = OxmlElement(f"w:{name}")
            margins.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def repeat_table_header(row: _Row) -> None:
    properties = row._tr.get_or_add_trPr()
    table_header = OxmlElement("w:tblHeader")
    table_header.set(qn("w:val"), "true")
    properties.append(table_header)


def prevent_row_split(row: _Row) -> None:
    properties = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    properties.append(cant_split)


def set_repeat_header_count(table: Table, count: int) -> None:
    for row in table.rows[:count]:
        repeat_table_header(row)


def set_table_fixed_layout(table: Table) -> None:
    table.autofit = False
    properties = table._tbl.tblPr
    layout = properties.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        properties.append(layout)
    layout.set(qn("w:type"), "fixed")


def set_cell_width(cell: _Cell, width_mm: float) -> None:
    width = Mm(width_mm)
    cell.width = width
    properties = cell._tc.get_or_add_tcPr()
    tc_width = properties.find(qn("w:tcW"))
    if tc_width is None:
        tc_width = OxmlElement("w:tcW")
        properties.append(tc_width)
    tc_width.set(qn("w:w"), str(int(width.twips)))
    tc_width.set(qn("w:type"), "dxa")


def set_cell_text(
    cell: _Cell,
    text: str,
    *,
    size: float = 8,
    bold: bool = False,
    align: WD_ALIGN_PARAGRAPH = WD_ALIGN_PARAGRAPH.CENTER,
) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.alignment = align
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.line_spacing = 1.0
    run = paragraph.add_run(text)
    run.font.name = "Liberation Sans"
    run.font.size = Pt(size)
    run.bold = bold
    set_cell_margins(cell)
