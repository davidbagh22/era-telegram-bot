import type { SurveyAdmin, SurveyResponseAdmin } from "../../types/admin";

export interface SurveyRankingItem {
  name: string;
  votes: number;
  percent: number;
}

function csvCell(value: unknown): string {
  const text = value == null ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function csvRow(values: unknown[]): string {
  return values.map(csvCell).join(";");
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

export function downloadSurveyResultsCsv(
  survey: SurveyAdmin,
  responses: SurveyResponseAdmin[],
  ranking: SurveyRankingItem[],
  isConference: boolean,
): void {
  const lines: string[] = [];

  lines.push(csvRow(["Опрос", survey.title]));
  lines.push(csvRow(["ID опроса", survey.id]));
  lines.push(csvRow(["Всего ответов", responses.length]));
  lines.push("");

  if (isConference) {
    lines.push(csvRow(["Рейтинг спикеров"]));
    lines.push(csvRow(["Место", "Спикер", "Голосов", "% участников"]));
    ranking.forEach((item, index) => {
      lines.push(csvRow([index + 1, item.name, item.votes, item.percent]));
    });
    lines.push("");
    lines.push(csvRow(["Кто за что голосовал"]));
    lines.push(csvRow(["Участник", "User ID", "Дата ответа", "Выбранные спикеры", "Свой кандидат"]));
    responses.forEach((response) => {
      lines.push(csvRow([
        response.user_name,
        response.user_id,
        submittedAt(response.submitted_at),
        displayAnswer(response.answers[0]?.answer ?? ""),
        response.answers[1]?.answer?.trim() ?? "",
      ]));
    });
  } else {
    const questions = responses[0]?.answers.map((answer) => answer.question) ?? survey.questions;
    lines.push(csvRow(["Кто за что голосовал"]));
    lines.push(csvRow(["Участник", "User ID", "Дата ответа", ...questions]));
    responses.forEach((response) => {
      lines.push(csvRow([
        response.user_name,
        response.user_id,
        submittedAt(response.submitted_at),
        ...questions.map((_, index) => displayAnswer(response.answers[index]?.answer ?? "")),
      ]));
    });
  }

  const blob = new Blob(["\uFEFF", lines.join("\r\n")], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ERA_survey_${survey.id}_results.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
