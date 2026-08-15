import { Card } from "../components/Card";

interface ObjectUnavailableScreenProps {
  onHome?: () => void;
}

export function ObjectUnavailableScreen({ onHome }: ObjectUnavailableScreenProps) {
  return (
    <div className="era-page" style={{ minHeight: "100vh", padding: "1.25rem", display: "grid", placeItems: "center" }}>
      <Card style={{ width: "100%", maxWidth: 440, textAlign: "center", padding: "1.25rem" }}>
        <div style={{ width: 52, height: 52, borderRadius: "50%", display: "grid", placeItems: "center", margin: "0 auto .85rem", background: "rgba(229,27,54,.12)", fontSize: "1.35rem" }}>×</div>
        <h1 style={{ margin: 0, fontSize: "var(--era-text-2xl)" }}>Этот объект больше недоступен</h1>
        <p style={{ margin: ".55rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.5 }}>
          Ссылка неверна, объект удалён или у вас больше нет доступа к нему.
        </p>
        {onHome && <button type="button" className="era-btn-primary" onClick={onHome} style={{ width: "100%", marginTop: "1rem" }}>На главную</button>}
      </Card>
    </div>
  );
}
