import { Card } from "./Card";
import { ChevronRightIcon } from "./icons";
import { StatusOrbit } from "./StatusOrbit";

interface EraScoreProps {
  score: number;
  progressPercent: number;
  levelLabel: string;
  onClick?: () => void;
}

export function EraScore({ score, progressPercent, levelLabel, onClick }: EraScoreProps) {
  return (
    <Card interactive={Boolean(onClick)} onClick={onClick} ariaLabel={onClick ? `ERA SCORE ${score}. Открыть мой прогресс` : undefined} style={{ padding: "1.15rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <StatusOrbit percent={progressPercent} size={104} strokeWidth={8}>
          <div>
            <strong style={{ display: "block", fontSize: "1.1rem", lineHeight: 1 }}>{Math.round(progressPercent)}%</strong>
            <span style={{ display: "block", marginTop: 4, color: "var(--era-text-muted)", fontSize: "0.65rem", fontWeight: 750 }}>путь</span>
          </div>
        </StatusOrbit>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span className="era-kicker" style={{ display: "block", marginBottom: "0.25rem" }}>ERA SCORE</span>
          <strong className="era-number" style={{ display: "block", fontSize: "var(--era-text-4xl)", lineHeight: 0.95, letterSpacing: "-0.055em" }}>{score}</strong>
          <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
            Сейчас: <strong style={{ color: "var(--era-text)" }}>{levelLabel}</strong>. Откройте расшифровку роста.
          </p>
        </div>
        {onClick && <ChevronRightIcon width={20} height={20} style={{ color: "var(--era-text-muted)", flexShrink: 0 }} />}
      </div>
    </Card>
  );
}
