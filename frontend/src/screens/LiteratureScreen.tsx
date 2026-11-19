import { useEffect, useState } from "react";
import { describeActionError, fetchLiterature, fetchLiteratureIssue, setLiteratureSubscription } from "../api/client";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { SkeletonList } from "../components/Skeleton";
import { useAsync } from "../hooks/useAsync";

const go = (number?: number) => { window.location.hash = number ? "#/literature/" + number : "#/literature"; };
function savedPosition(key: string): { number: number; scrollY: number } | null {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "null");
    return Number.isInteger(value?.number) && value.number >= 1 && value.number <= 48
      ? { number: value.number, scrollY: Math.max(0, Number(value.scrollY) || 0) } : null;
  } catch { return null; }
}
export function LiteratureScreen({ userId, number }: { userId: number; number?: number | null }) {
  const catalog = useAsync(fetchLiterature, []);
  const issue = useAsync(() => number ? fetchLiteratureIssue(number) : Promise.resolve(null), [number]);
  const key = "era.literature.position." + userId;
  const [resume, setResume] = useState(() => savedPosition(key));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!number || issue.status !== "ready" || !issue.data) return;
    const position = savedPosition(key);
    window.scrollTo(0, position?.number === number ? position.scrollY : 0);
    const save = () => {
      try { localStorage.setItem(key, JSON.stringify({ number, scrollY: window.scrollY })); } catch { /* private mode */ }
    };
    let timer: number | undefined;
    const onScroll = () => { window.clearTimeout(timer); timer = window.setTimeout(save, 150); };
    save();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => { window.removeEventListener("scroll", onScroll); window.clearTimeout(timer); };
  }, [number, issue.status, key]);
  useEffect(() => { if (!number) setResume(savedPosition(key)); }, [number, key]);

  const subscribe = async () => {
    if (catalog.status !== "ready") return;
    setBusy(true); setError("");
    try { await setLiteratureSubscription(!catalog.data.subscribed); catalog.reload(); }
    catch (e) { setError(describeActionError(e)); }
    finally { setBusy(false); }
  };
  return <div className="era-page era-discover-page">
    <button className="era-btn-ghost" style={{ alignSelf: "flex-start" }} onClick={() => number ? go() : (window.location.hash = "#/discover/leisure")}>← {number ? "Литература" : "Открытия"}</button>
    {number ? <>
      {issue.status === "loading" && <SkeletonList count={3} />}
      {issue.status === "error" && <EmptyState title="Материал недоступен" text="Обнови страницу или выбери другой выпуск в архиве." actionLabel="Повторить" onAction={issue.reload} />}
      {issue.status === "ready" && issue.data && <article className="era-reader">
        <MonoLabel>Материал ЭРА · № {issue.data.number}</MonoLabel>
        <h1>{issue.data.title}</h1>
        {([["Коротко", issue.data.summary], ["Жизненная ситуация", issue.data.example], ["Другой взгляд", issue.data.critical_view],
          ["Вопрос для себя", issue.data.reflection_question], ["Попробуй", issue.data.practical_task]]).map(([heading, text]) =>
          <section key={heading}><h2>{heading}</h2><p>{text}</p></section>)}
        {catalog.status === "ready" && number < catalog.data.latest && <button className="era-btn-primary" onClick={() => go(number + 1)}>Следующий выпуск →</button>}
      </article>}
    </> : <>
      <header><MonoLabel>Открытия</MonoLabel><h1>Литература</h1><p className="era-discover-copy">Читай в своём ритме.</p></header>
      {catalog.status === "loading" && <SkeletonList count={3} />}
      {catalog.status === "error" && <EmptyState text="Не удалось загрузить архив." actionLabel="Повторить" onAction={catalog.reload} />}
      {catalog.status === "ready" && <>
        {resume && resume.number <= catalog.data.latest && <Card onClick={() => go(resume.number)}><MonoLabel>Продолжить чтение</MonoLabel><strong className="era-discover-title">{catalog.data.items.find(i => i.number === resume.number)?.title}</strong></Card>}
        {catalog.data.items[0] && <Card gradient onClick={() => go(catalog.data.latest)}><MonoLabel>Последний доступный выпуск · {catalog.data.latest}</MonoLabel><strong className="era-discover-title">{catalog.data.items[0].title}</strong><p className="era-discover-copy">Читать →</p></Card>}
        <button disabled={busy} onClick={() => void subscribe()}>{busy ? "Сохраняем…" : catalog.data.subscribed ? "Отключить подписку" : "Подписаться на выпуски"}</button>
        <details className="era-reader-archive"><summary>Архив · {catalog.data.items.length} выпусков</summary>
          {catalog.data.items.map(item => <button key={item.number} onClick={() => go(item.number)}><span>{item.number}</span>{item.title}</button>)}
        </details>
      </>}
      {error && <p role="alert" style={{ color: "var(--era-error)" }}>{error}</p>}
    </>}
  </div>;
}
