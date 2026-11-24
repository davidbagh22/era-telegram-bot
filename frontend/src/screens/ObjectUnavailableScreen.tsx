import { Card } from "../components/Card";

interface ObjectUnavailableScreenProps {
  onHome?: () => void;
}

export function ObjectUnavailableScreen({ onHome }: ObjectUnavailableScreenProps) {
  return (
    <div className="era-page" style={{ minHeight: "100vh", padding: "1.25rem", display: "grid", placeItems: "center" }}>
      <Card
        style={{ width: "100%", maxWidth: 440, textAlign: "center", padding: "1.25rem" }}
      >
        <div
          role="status"
          aria-live="polite"
          style={{ display: "grid", gap: "0.55rem", justifyItems: "center" }}
        >
          <div
            aria-hidden="true"
            style={{
              width: 52,
              height: 52,
              borderRadius: "50%",
              display: "grid",
              placeItems: "center",
              background: "rgba(229,27,54,.12)",
              fontSize: "1.35rem",
            }}
          >
            ×
          </div>
          <h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Этот объект больше недоступен</h1>
          <p style={{ margin: 0, color: "var(--era-text-muted)", lineHeight: 1.5 }}>
            Ссылка неверна, объект удалён или у вас больше нет доступа к нему.
          </p>
        </div>
        {onHome && (
          <button
            type="button"
            className="era-btn-primary"
            onClick={onHome}
            style={{ width: "100%", marginTop: "1rem", minHeight: 44 }}
          >
            На главную
          </button>
        )}
      </Card>
    </div>
  );
}
