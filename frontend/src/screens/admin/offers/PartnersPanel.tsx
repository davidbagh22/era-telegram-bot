import { useCallback, useState } from "react";
import {
  archivePartner,
  createPartner,
  describeActionError,
  fetchAdminPartners,
  setPartnerActive,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

// The Mini App equivalent of app/handlers/admin/partners_admin.py — the
// sponsor/partner organizations behind offers, not to be confused with the
// offers (PartnerInitiative) themselves in OffersPanel.
export function PartnersPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminPartners(), [refreshKey]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !description.trim()) return;
    setCreating(true);
    setActionError(null);
    try {
      await createPartner({ name: name.trim(), description: description.trim(), source_url: sourceUrl.trim() });
      setName("");
      setDescription("");
      setSourceUrl("");
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [name, description, sourceUrl, refresh]);

  const runAction = useCallback(
    async (partnerId: number, action: () => Promise<unknown>) => {
      setBusyId(partnerId);
      setActionError(null);
      try {
        await action();
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      <Card>
        <strong>Новый партнёр</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <input placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} />
          <textarea
            placeholder="Описание"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            style={inputStyle}
          />
          <input
            placeholder="Ссылка (необязательно)"
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            style={inputStyle}
          />
          <button
            type="button"
            className="era-btn-primary"
            disabled={creating || !name.trim() || !description.trim()}
            onClick={handleCreate}
          >
            Добавить партнёра
          </button>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить партнёров." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Партнёров пока нет." />}
      {state.status === "ready" &&
        state.data.map((partner) => (
          <Card key={partner.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{partner.name}</strong>
              {!partner.is_active && <StatusBadge label="скрыт" tone="neutral" />}
            </div>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{partner.description}</p>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                type="button"
                disabled={busyId === partner.id}
                onClick={() => runAction(partner.id, () => setPartnerActive(partner.id, !partner.is_active))}
              >
                {partner.is_active ? "Скрыть" : "Активировать"}
              </button>
              <button
                type="button"
                disabled={busyId === partner.id}
                onClick={() => runAction(partner.id, () => archivePartner(partner.id))}
              >
                Архивировать
              </button>
            </div>
          </Card>
        ))}
    </div>
  );
}
