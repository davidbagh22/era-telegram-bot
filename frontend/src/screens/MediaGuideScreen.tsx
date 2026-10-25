import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { fetchMediaGuide, type MediaGuide } from "../api/media";

interface MediaGuideScreenProps {
  onBack: () => void;
}

const SECTIONS: { key: keyof MediaGuide; title: string }[] = [
  { key: "principles", title: "Принципы" },
  { key: "post", title: "Структура поста" },
  { key: "reels", title: "Структура Reels" },
  { key: "visual", title: "Визуал" },
];

/**
 * Internal `#/media/guide` destination (DELTA ToR §32-34). Reached only via
 * SPA hash navigation from MediaScreen's library list -- never window.open,
 * so Telegram initData survives and the guide never bounces out to Safari.
 */
export function MediaGuideScreen({ onBack }: MediaGuideScreenProps) {
  const [guide, setGuide] = useState<MediaGuide | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMediaGuide()
      .then((result) => { if (!cancelled) setGuide(result); })
      .catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Не удалось загрузить гайд"); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="era-page" style={{ padding: "1.25rem 1.25rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button
          type="button"
          onClick={onBack}
          aria-label="Назад"
          style={{
            minWidth: 44,
            minHeight: 44,
            border: "1px solid var(--era-border)",
            background: "var(--era-surface-2)",
            color: "var(--era-text)",
            borderRadius: 14,
            padding: "0.55rem 0.7rem",
            fontWeight: 800,
            cursor: "pointer",
          }}
        >←</button>
        <div>
          <div style={{ fontSize: "0.72rem", color: "var(--era-text-muted)", fontWeight: 900, textTransform: "uppercase" }}>ЭРА · Медиа</div>
          <h1 style={{ margin: "0.15rem 0 0", fontSize: "var(--era-text-3xl)", lineHeight: 1.05 }}>Гайд Медиа ЭРА</h1>
        </div>
      </div>

      {error ? <Card><strong>Нужно внимание</strong><div style={{ color: "var(--era-text-muted)", marginTop: 5 }}>{error}</div></Card> : null}
      {!guide && !error ? <Card>Загружаем гайд…</Card> : null}

      {guide && SECTIONS.map(({ key, title }) => (
        <Card key={key} style={{ display: "grid", gap: 10 }}>
          <strong>{title}</strong>
          <ul style={{ margin: 0, paddingLeft: "1.1rem", display: "grid", gap: 6 }}>
            {guide[key].map((line, index) => (
              <li key={index} style={{ color: "var(--era-text-muted)", lineHeight: 1.5, fontSize: "0.9rem" }}>{line}</li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}
