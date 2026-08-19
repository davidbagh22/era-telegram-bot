import { useState } from "react";
import { downloadAdminMetric, fetchAdminMetric } from "../../api/adminMetrics";
import { ActionCell } from "../../components/ActionCell";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";
import type { AdminMetricKey } from "../../types/adminMetrics";

interface AdminMetricDetailScreenProps {
  metric: AdminMetricKey;
  expectedTotal: number;
  onBack: () => void;
  onOpenEntity?: (entityType: string, entityId: number) => void;
}

export function AdminMetricDetailScreen({ metric, expectedTotal, onBack, onOpenEntity }: AdminMetricDetailScreenProps) {
  const data = useAsync(() => fetchAdminMetric(metric), [metric]);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  async function exportRows() {
    if (exporting) return;
    setExporting(true);
    setExportError(null);
    try {
      await downloadAdminMetric(metric);
    } catch {
      setExportError("Не удалось сформировать Excel. Попробуйте ещё раз.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>
      {data.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Собираем исходные строки показателя…</p>}
      {data.status === "error" && <EmptyState text="Не удалось открыть детализацию показателя." />}
      {data.status === "ready" && (
        <>
          <Card>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
              Точный drill-down
            </p>
            <h1 style={{ margin: "0.35rem 0 0", fontSize: "var(--era-text-2xl)" }}>{data.data.label}</h1>
            <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-muted)" }}>
              В показателе: <strong>{data.data.total}</strong>. Список построен тем же правилом, что и KPI на главной.
            </p>
            {expectedTotal !== data.data.total && (
              <p role="alert" style={{ margin: "0.55rem 0 0", color: "var(--era-error)", fontWeight: 800 }}>
                Показатель обновился: было {expectedTotal}, сейчас {data.data.total}.
              </p>
            )}
            <button type="button" disabled={exporting} onClick={() => void exportRows()} style={{ width: "100%", minHeight: 46, marginTop: "0.8rem", fontWeight: 850 }}>
              {exporting ? "Формируем Excel…" : `Скачать эти ${data.data.total} строк в Excel`}
            </button>
            {exportError && <p role="alert" style={{ margin: "0.45rem 0 0" }}>{exportError}</p>}
          </Card>

          {data.data.items.length === 0 ? (
            <EmptyState text="В этом показателе сейчас нет строк." />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {data.data.items.map((item) => (
                <ActionCell
                  key={`${item.entity_type}:${item.id}`}
                  title={item.title}
                  description={[item.subtitle, item.status].filter(Boolean).join(" · ") || "Открыть запись"}
                  onClick={onOpenEntity ? () => onOpenEntity(item.entity_type, item.entity_id) : undefined}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
