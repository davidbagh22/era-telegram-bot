import type { SurveyAdmin, SurveyResponseAdmin } from "../../types/admin";

export interface SurveyRankingItem {
  name: string;
  votes: number;
  percent: number;
}

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
  return choices.length > 0 ? choices.join(", ") : answer || "—";
}

function submittedAt(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("ru-RU");
}

function cell(value: unknown, style = "Body", type: "String" | "Number" = "String"): string {
  return `<Cell ss:StyleID="${style}"><Data ss:Type="${type}">${escapeXml(value)}</Data></Cell>`;
}

function row(cells: string[], height?: number): string {
  const heightAttr = height ? ` ss:Height="${height}"` : "";
  return `<Row${heightAttr}>${cells.join("")}</Row>`;
}

function column(width: number): string {
  return `<Column ss:AutoFitWidth="0" ss:Width="${width}"/>`;
}

function buildSummarySheet(
  survey: SurveyAdmin,
  responses: SurveyResponseAdmin[],
  ranking: SurveyRankingItem[],
  isConference: boolean,
): string {
  const rows: string[] = [
    row([cell("ЭРА · РЕЗУЛЬТАТЫ ОПРОСА", "Hero")], 30),
    row([cell(survey.title, "Title")], 34),
    row([]),
    row([cell("Ответов", "Label"), cell(responses.length, "Metric", "Number")]),
    row([cell("Сформировано", "Label"), cell(new Date().toLocaleString("ru-RU"), "Body")]),
  ];

  if (isConference) {
    rows.push(
      row([]),
      row([cell("РЕЙТИНГ СПИКЕРОВ", "Section")], 26),
      row([
        cell("Место", "Header"),
        cell("Спикер", "Header"),
        cell("Голосов", "Header"),
        cell("% участников", "Header"),
      ]),
    );
    ranking.forEach((item, index) => {
      const topStyle = index < 3 ? "Top" : "Body";
      rows.push(row([
        cell(index + 1, index < 3 ? "TopNumber" : "Center", "Number"),
        cell(item.name, topStyle),
        cell(item.votes, "Center", "Number"),
        cell(`${item.percent}%`, "Center"),
      ]));
    });
  }

  return `<Worksheet ss:Name="Сводка">
<Table>
${column(70)}${column(300)}${column(90)}${column(110)}
${rows.join("\n")}
</Table>
<WorksheetOptions xmlns="urn:schemas-microsoft-com:office:excel"><FreezePanes/><FrozenNoSplit/><SplitHorizontal>${isConference ? 8 : 5}</SplitHorizontal><TopRowBottomPane>${isConference ? 8 : 5}</TopRowBottomPane><ActivePane>2</ActivePane></WorksheetOptions>
</Worksheet>`;
}

function buildAnswersSheet(
  survey: SurveyAdmin,
  responses: SurveyResponseAdmin[],
  isConference: boolean,
): string {
  const questionLabels = responses[0]?.answers.map((answer) => answer.question) ?? survey.questions;
  const headers = isConference
    ? ["№", "Участник", "Дата ответа", "Выбранные спикеры", "Свой кандидат", "ID"]
    : ["№", "Участник", "Дата ответа", ...questionLabels, "ID"];

  const rows: string[] = [
    row([cell("ЭРА · КТО ЗА ЧТО ГОЛОСОВАЛ", "Hero")], 30),
    row([cell(survey.title, "Title")], 34),
    row([]),
    row(headers.map((header) => cell(header, "Header")), 30),
  ];

  responses.forEach((response, responseIndex) => {
    if (isConference) {
      rows.push(row([
        cell(responseIndex + 1, "Center", "Number"),
        cell(response.user_name, "Strong"),
        cell(submittedAt(response.submitted_at), "Body"),
        cell(displayAnswer(response.answers[0]?.answer ?? ""), "Wrap"),
        cell(response.answers[1]?.answer?.trim() || "—", "Wrap"),
        cell(response.user_id, "Center", "Number"),
      ]));
      return;
    }

    rows.push(row([
      cell(responseIndex + 1, "Center", "Number"),
      cell(response.user_name, "Strong"),
      cell(submittedAt(response.submitted_at), "Body"),
      ...questionLabels.map((_, index) => cell(displayAnswer(response.answers[index]?.answer ?? ""), "Wrap")),
      cell(response.user_id, "Center", "Number"),
    ]));
  });

  const columns = isConference
    ? [42, 170, 125, 330, 220, 60]
    : [42, 170, 125, ...questionLabels.map(() => 250), 60];

  return `<Worksheet ss:Name="Ответы участников">
<Table>
${columns.map(column).join("")}
${rows.join("\n")}
</Table>
<WorksheetOptions xmlns="urn:schemas-microsoft-com:office:excel"><FreezePanes/><FrozenNoSplit/><SplitHorizontal>4</SplitHorizontal><TopRowBottomPane>4</TopRowBottomPane><ActivePane>2</ActivePane></WorksheetOptions>
</Worksheet>`;
}

function buildWorkbook(
  survey: SurveyAdmin,
  responses: SurveyResponseAdmin[],
  ranking: SurveyRankingItem[],
  isConference: boolean,
): string {
  const summary = buildSummarySheet(survey, responses, ranking, isConference);
  const answers = buildAnswersSheet(survey, responses, isConference);
  return `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:html="http://www.w3.org/TR/REC-html40">
<Styles>
<Style ss:ID="Default" ss:Name="Normal"><Alignment ss:Vertical="Center"/><Font ss:FontName="Arial" ss:Size="10"/></Style>
<Style ss:ID="Hero"><Alignment ss:Vertical="Center"/><Font ss:FontName="Arial" ss:Size="16" ss:Bold="1" ss:Color="#FFFFFF"/><Interior ss:Color="#6F2DBD" ss:Pattern="Solid"/></Style>
<Style ss:ID="Title"><Alignment ss:Vertical="Center" ss:WrapText="1"/><Font ss:FontName="Arial" ss:Size="13" ss:Bold="1" ss:Color="#201B2C"/></Style>
<Style ss:ID="Section"><Font ss:FontName="Arial" ss:Size="11" ss:Bold="1" ss:Color="#6F2DBD"/></Style>
<Style ss:ID="Label"><Font ss:FontName="Arial" ss:Size="10" ss:Bold="1" ss:Color="#6F2DBD"/><Interior ss:Color="#F2EDFF" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E3DCEA"/></Borders></Style>
<Style ss:ID="Metric"><Alignment ss:Horizontal="Center"/><Font ss:FontName="Arial" ss:Size="12" ss:Bold="1"/><Interior ss:Color="#FFF2E8" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E3DCEA"/></Borders></Style>
<Style ss:ID="Header"><Alignment ss:Horizontal="Center" ss:Vertical="Center" ss:WrapText="1"/><Font ss:FontName="Arial" ss:Size="10" ss:Bold="1" ss:Color="#FFFFFF"/><Interior ss:Color="#6F2DBD" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#FFFFFF"/></Borders></Style>
<Style ss:ID="Body"><Alignment ss:Vertical="Top"/><Font ss:FontName="Arial" ss:Size="10"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E8E2EC"/></Borders></Style>
<Style ss:ID="Wrap"><Alignment ss:Vertical="Top" ss:WrapText="1"/><Font ss:FontName="Arial" ss:Size="10"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E8E2EC"/></Borders></Style>
<Style ss:ID="Center"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/><Font ss:FontName="Arial" ss:Size="10"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E8E2EC"/></Borders></Style>
<Style ss:ID="Strong"><Alignment ss:Vertical="Top" ss:WrapText="1"/><Font ss:FontName="Arial" ss:Size="10" ss:Bold="1"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E8E2EC"/></Borders></Style>
<Style ss:ID="Top"><Alignment ss:Vertical="Center" ss:WrapText="1"/><Font ss:FontName="Arial" ss:Size="10" ss:Bold="1"/><Interior ss:Color="#F2EDFF" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9CCF5"/></Borders></Style>
<Style ss:ID="TopNumber"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/><Font ss:FontName="Arial" ss:Size="10" ss:Bold="1" ss:Color="#6F2DBD"/><Interior ss:Color="#FFF2E8" ss:Pattern="Solid"/><Borders><Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D9CCF5"/></Borders></Style>
</Styles>
${summary}
${answers}
</Workbook>`;
}

export function downloadSurveyResultsExcel(
  survey: SurveyAdmin,
  responses: SurveyResponseAdmin[],
  ranking: SurveyRankingItem[],
  isConference: boolean,
): void {
  const workbook = buildWorkbook(survey, responses, ranking, isConference);
  const blob = new Blob(["\uFEFF", workbook], { type: "application/vnd.ms-excel;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ERA_survey_${survey.id}_results.xml`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
