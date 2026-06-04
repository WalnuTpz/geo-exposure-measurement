from __future__ import annotations

import csv
import html
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "config" / "benchmark_100" / "queries.csv"
OUTPUT_XLSX = ROOT / "reports" / "benchmark_100" / "benchmark_100_queries.xlsx"

CATEGORY_NAMES = {
    "product_recommendation": "产品推荐",
    "business_legal_service": "商业/法律服务",
    "health_medical_advice": "健康/医学建议",
    "mental_health_therapy": "心理健康/治疗",
    "finance_tax_software": "金融/税务/软件",
    "technical_troubleshooting": "技术排错",
    "factual_official_control": "事实/官方信息对照",
    "multi_hop_factual": "多跳事实",
    "debate_opinion": "辩论/观点",
    "social_community_qa": "社区问答",
}


def compact_query_id(query_id: str) -> str:
    match = re.match(r"^B100Q0*(\d+)$", query_id)
    return f"Q{match.group(1)}" if match else query_id


def col_name(index: int) -> str:
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def inline_string_cell(row_idx: int, col_idx: int, value: str, style: int = 0) -> str:
    ref = f"{col_name(col_idx)}{row_idx}"
    style_attr = f' s="{style}"' if style else ""
    return (
        f'<c r="{ref}" t="inlineStr"{style_attr}>'
        f"<is><t>{html.escape(value)}</t></is>"
        "</c>"
    )


def build_sheet_xml(rows: list[list[str]]) -> str:
    sheet_rows = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            cells.append(inline_string_cell(row_idx, col_idx, value, style=1 if row_idx == 1 else 0))
        sheet_rows.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
    </sheetView>
  </sheetViews>
  <cols>
    <col min="1" max="1" width="18" customWidth="1"/>
    <col min="2" max="2" width="58" customWidth="1"/>
    <col min="3" max="3" width="46" customWidth="1"/>
  </cols>
  <sheetData>
    {"".join(sheet_rows)}
  </sheetData>
</worksheet>'''


def write_xlsx(rows: list[list[str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    files = {
        "[Content_Types].xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>''',
        "_rels/.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>''',
        "xl/workbook.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="100 queries" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>''',
        "xl/_rels/workbook.xml.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>''',
        "xl/styles.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>''',
        "xl/worksheets/sheet1.xml": build_sheet_xml(rows),
        "docProps/core.xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>GEO Exposure Benchmark 100 Queries</dc:title>
  <dc:creator>Codex</dc:creator>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>''',
        "docProps/app.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
</Properties>''',
    }

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as xlsx:
        for archive_name, content in files.items():
            xlsx.writestr(archive_name, content)


def main() -> None:
    rows = [["种类", "具体问题", "问题来源"]]
    with INPUT_CSV.open("r", encoding="utf-8", newline="") as handle:
        for record in csv.DictReader(handle):
            source = " | ".join(
                part
                for part in [
                    record["source_dataset"],
                    record["source_split"],
                    record["source_item_id"],
                ]
                if part
            )
            rows.append(
                [
                    CATEGORY_NAMES.get(record["category"], record["category"]),
                    f'{compact_query_id(record["query_id"])}: {record["query"]}',
                    source,
                ]
            )

    write_xlsx(rows, OUTPUT_XLSX)
    print(f"wrote {len(rows) - 1} queries to {OUTPUT_XLSX}")


if __name__ == "__main__":
    main()
