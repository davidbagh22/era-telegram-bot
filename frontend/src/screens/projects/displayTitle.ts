/** Present a stored project title without changing the database value. */
export function displayProjectTitle(title: string | null | undefined): string {
  const cleaned = (title ?? "").replace(/\s+/g, " ").trim();
  return cleaned || "Без названия";
}
