import { Card } from "./Card";

interface MetricCardProps {
  label: string;
  value: string | number;
}

export function MetricCard({ label, value }: MetricCardProps) {
  return (
    <Card style={{ textAlign: "center" }}>
      <div style={{ fontFamily: "var(--era-font-display)", fontSize: "1.5rem" }}>{value}</div>
      <div style={{ fontSize: "0.75rem", color: "var(--era-text-muted)" }}>{label}</div>
    </Card>
  );
}
