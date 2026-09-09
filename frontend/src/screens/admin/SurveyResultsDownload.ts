import type { SurveyAdmin, SurveyResponseAdmin } from "../../types/admin";

export interface SurveyRankingItem {
  name: string;
  votes: number;
  percent: number;
}

type CellValue = string | number;
type SheetCell = { value: CellValue; style?: number };
type SheetRow = SheetCell[];

type ZipEntry = {
  name: string;
  data: Uint8Array;
  crc: number;
  offset: number;
};

const encoder = new TextEncoder();

function escapeXml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function parseChoices(answer: string): string[] {
  try {
    const parsed = JSON.parse(answer);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function displayAnswer(answer: string): string {
  const choices = parseChoices(answer);
  return choices.length > 0 ? choices.join(", ") : answer || "";
}

function submittedAt(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ru-RU");
}

function columnName(index: number): string {
  let value = index + 1;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function cellXml(cell: SheetCell, row: number, column: number): string {
  const ref = `${columnName(column)}${row}`;
  const style = cell.style != null ? ` s="${cell.style}"` : "";
  if (typeof cell.value === "number") {
    return `<c r="${ref}"${style} t="n"><v>${cell.value}</v></c>`;
  }
  return `<c r="${ref}"${style} t="inlineStr"><is><t xml:space="preserve">${escapeXml(cell.value)}</t></is></c>`;
}

function sheetXml(rows: SheetRow[], widths: number[], merges: string[] = [], freezeRow = 0): string {
  const cols = widths
    .map((width, index) => `<col min="${index + 1}" max="${index + 1}" width="${width}" customWidth="1"/>`)
    .join("");
  const rowXml = rows
    .map((cells, rowIndex) => `<row r="${rowIndex + 1}">${cells.map((cell, columnIndex) => cellXml(cell, rowIndex + 1, columnIndex)).join("")}</row>`)
    .join("");
  const mergeXml = merges.length
    ? `<mergeCells count="${merges.length}">${merges.map((ref) => `<mergeCell ref="${ref}"/>`).join("")}</mergeCells>`
    : "";
  const paneXml = freezeRow > 0
    ? `<sheetViews><sheetView workbookViewId="0"><pane ySplit="${freezeRow}" topLeftCell="A${freezeRow + 1}" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>`
    : `<sheetViews><sheetView workbookViewId="0"/></sheetViews>`;
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
${paneXml}
<cols>${cols}</cols>
<sheetData>${rowXml}</sheetData>
${mergeXml}
</worksheet>`;
}

function uint16(value: number): Uint8Array {
  return new Uint8Array([value & 0xff, (value >>> 8) & 0xff]);
}

function uint32(value: number): Uint8Array {
  return new Uint8Array([
    value & 0xff,
    (value >>> 8) & 0xff,
    (value >>> 16) & 0xff,
    (value >>> 24) & 0xff,
  ]);
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const output = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

const crcTable = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) !== 0 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(data: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of data) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function makeZip(files: { name: string; content: string }[]): Uint8Array {
  const localParts: Uint8Array[] = [];
  const entries: ZipEntry[] = [];
  let offset = 0;

  for (const file of files) {
    const name = encoder.encode(file.name);
    const data = encoder.encode(file.content);
    const crc = crc32(data);
    const header = concat([
      uint32(0x04034b50), uint16(20), uint16(0), uint16(0), uint16(0), uint16(0),
      uint32(crc), uint32(data.length), uint32(data.length), uint16(name.length), uint16(0), name,
    ]);
    localParts.push(header, data);
    entries.push({ name: file.name, data, crc, offset });
    offset += header.length + data.length;
  }

  const centralParts: Uint8Array[] = [];
  for (const entry of entries) {
    const name = encoder.encode(entry.name);
    centralParts.push(concat([
      uint32(0x02014b50), uint16(20), uint16(20), uint16(0), uint16(0), uint16(0), uint16(0),
      uint32(entry.crc), uint32(entry.data.length), uint32(entry.data.length),
      uint16(name.length), uint16(0), uint16(0), uint16(0), uint16(0), uint32(0), uint32(entry.offset), name,
    ]));
  }
  const central = concat(centralParts);
  const local = concat(localParts);
  const end = concat([
    uint32(0x06054b50), uint16(0), uint16(0), uint16(entries.length), uint16(entries.length),
    uint32(central.length), uint32(local.length), uint16(0),
  ]);
  return concat([local, central, end]);
}

function buildWorkbook(
  survey: SurveyAdmin,
  responses: SurveyResponseAdmin[],
  ranking: SurveyRankingItem[],
  isConference: boolean,
): Uint8Array {
  const generatedAt = new Date().toLocaleString("ru-RU");
  const summaryRows: SheetRow[] = [
    [{ value: "ЭРА · РЕЗУЛЬТАТЫ ОПРОСА", style: 1 }],
    [{ value: survey.title, style: 2 }],
    [],
    [{ value: "Ответов", style: 3 }, { value: responses.length, style: 6 }],
    [{ value: "Сформировано", style: 3 }, { value: generatedAt, style: 4 }],
  ];

  if (isConference) {
    summaryRows.push(
      [],
      [{ value: "РЕЙТИНГ СПИКЕРОВ", style: 2 }],
      [
        { value: "Место", style: 3 },
        { value: "Спикер", style: 3 },
        { value: "Голосов", style: 3 },
        { value: "% участников", style: 3 },
      ],
    );
    ranking.forEach((item, index) => {
      summaryRows.push([
        { value: index + 1, style: index < 3 ? 6 : 5 },
        { value: item.name, style: index < 3 ? 7 : 4 },
        { value: item.votes, style: 5 },
        { value: `${item.percent}%`, style: 5 },
      ]);
    });
  }

  const questionLabels = responses[0]?.answers.map((answer) => answer.question) ?? survey.questions;
  const answerHeaders = isConference
    ? ["№", "Участник", "Дата ответа", "Выбранные спикеры", "Свой кандидат", "ID"]
    : ["№", "Участник", "Дата ответа", ...questionLabels, "ID"];
  const answerRows: SheetRow[] = [
    [{ value: "ЭРА · КТО ЗА ЧТО ГОЛОСОВАЛ", style: 1 }],
    [{ value: survey.title, style: 2 }],
    [],
    answerHeaders.map((header) => ({ value: header, style: 3 })),
  ];

  responses.forEach((response, responseIndex) => {
    if (isConference) {
      answerRows.push([
        { value: responseIndex + 1, style: 5 },
        { value: response.user_name, style: 7 },
        { value: submittedAt(response.submitted_at), style: 4 },
        { value: displayAnswer(response.answers[0]?.answer ?? ""), style: 4 },
        { value: response.answers[1]?.answer?.trim() || "—", style: 4 },
        { value: response.user_id, style: 5 },
      ]);
    } else {
      answerRows.push([
        { value: responseIndex + 1, style: 5 },
        { value: response.user_name, style: 7 },
        { value: submittedAt(response.submitted_at), style: 4 },
        ...questionLabels.map((_, index) => ({ value: displayAnswer(response.answers[index]?.answer ?? ""), style: 4 })),
        { value: response.user_id, style: 5 },
      ]);
    }
  });

  const summarySheet = sheetXml(summaryRows, [12, 42, 14, 18], ["A1:D1", "A2:D2", ...(isConference ? ["A7:D7"] : [])], isConference ? 8 : 0);
  const answerWidths = isConference
    ? [7, 28, 22, 58, 36, 10]
    : [7, 28, 22, ...questionLabels.map(() => 42), 10];
  const lastAnswerColumn = columnName(answerHeaders.length - 1);
  const answersSheet = sheetXml(answerRows, answerWidths, [`A1:${lastAnswerColumn}1`, `A2:${lastAnswerColumn}2`], 4);

  const contentTypes = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>`;

  const rootRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`;

  const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
<sheet name="Сводка" sheetId="1" r:id="rId1"/>
<sheet name="Ответы участников" sheetId="2" r:id="rId2"/>
</sheets>
</workbook>`;

  const workbookRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`;

  const styles = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="4">
<font><sz val="11"/><name val="Arial"/></font>
<font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>
<font><b/><sz val="13"/><color rgb="FF201B2C"/><name val="Arial"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>
</fonts>
<fills count="5">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF6F2DBD"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF2EDFF"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF2E8"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFE3DCEA"/></left><right style="thin"><color rgb="FFE3DCEA"/></right><top style="thin"><color rgb="FFE3DCEA"/></top><bottom style="thin"><color rgb="FFE3DCEA"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="8">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="3" fillId="2" borderId="1" xfId="0"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="4" borderId="1" xfId="0"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0"><alignment vertical="center" wrapText="1"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;

  return makeZip([
    { name: "[Content_Types].xml", content: contentTypes },
    { name: "_rels/.rels", content: rootRels },
    { name: "xl/workbook.xml", content: workbook },
    { name: "xl/_rels/workbook.xml.rels", content: workbookRels },
    { name: "xl/styles.xml", content: styles },
    { name: "xl/worksheets/sheet1.xml", content: summarySheet },
    { name: "xl/worksheets/sheet2.xml", content: answersSheet },
  ]);
}

export function downloadSurveyResultsExcel(
  survey: SurveyAdmin,
  responses: SurveyResponseAdmin[],
  ranking: SurveyRankingItem[],
  isConference: boolean,
): void {
  const workbook = buildWorkbook(survey, responses, ranking, isConference);
  const blob = new Blob([workbook], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ERA_survey_${survey.id}_results.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
