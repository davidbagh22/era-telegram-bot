import { useCallback, useState } from "react";
import {
  archiveOffer,
  createOffer,
  describeActionError,
  fetchAdminOffers,
  fetchAdminPartners,
  setOfferActive,
} from "../../../api/client";
import { updateOffer } from "../../../api/adminOffers";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import type { OfferAdmin } from "../../../types/admin";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

export function OffersPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const offers = useAsync(() => fetchAdminOffers(), [refreshKey]);
  const partners = useAsync(() => fetchAdminPartners(), []);

  const [editingId, setEditingId] = useState<number | null>(null);
  const [partnerId, setPartnerId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [pointCost, setPointCost] = useState("");
  const [quantity, setQuantity] = useState("");
  const [instruction, setInstruction] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);
  const canSave = Boolean(partnerId && title.trim() && description.trim() && pointCost.trim() !== "");

  const resetForm = useCallback(() => {
    setEditingId(null);
    setPartnerId("");
    setTitle("");
    setDescription("");
    setPointCost("");
    setQuantity("");
    setInstruction("");
  }, []);

  const startEditing = useCallback((offer: OfferAdmin) => {
    setEditingId(offer.id);
    setPartnerId(String(offer.partner_id));
    setTitle(offer.title);
    setDescription(offer.description);
    setPointCost(String(offer.point_cost));
    setQuantity(offer.quantity == null ? "" : String(offer.quantity));
    setInstruction(offer.instruction ?? "");
    setActionError(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const handleSave = useCallback(async () => {
    if (!canSave) return;
    setCreating(true);
    setActionError(null);
    const payload = {
      partner_id: Number(partnerId),
      title: title.trim(),
      description: description.trim(),
      point_cost: Number(pointCost),
      quantity: quantity.trim() ? Number(quantity) : null,
      instruction: instruction.trim() || null,
    };
    try {
      if (editingId != null) await updateOffer(editingId, payload);
      else await createOffer({ ...payload, instruction: payload.instruction ?? "" });
      resetForm();
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [canSave, partnerId, title, description, pointCost, quantity, instruction, editingId, resetForm, refresh]);

  const runAction = useCallback(
    async (offerId: number, action: () => Promise<unknown>) => {
      setBusyId(offerId);
      setActionError(null);
      try {
        await action();
        if (editingId === offerId) resetForm();
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [editingId, resetForm, refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      <Card>
        <strong>{editingId != null ? "Редактирование предложения" : "Новое предложение"}</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <select value={partnerId} onChange={(e) => setPartnerId(e.target.value)} style={inputStyle}>
            <option value="">Партнёр…</option>
            {partners.status === "ready" &&
              partners.data.map((partner) => (
                <option key={partner.id} value={partner.id}>
                  {partner.name}
                </option>
              ))}
          </select>
          <input placeholder="Название" value={title} onChange={(e) => setTitle(e.target.value)} style={inputStyle} />
          <textarea
            placeholder="Описание"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            style={inputStyle}
          />
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <input
              type="number"
              min={0}
              placeholder="Стоимость в баллах"
              value={pointCost}
              onChange={(e) => setPointCost(e.target.value)}
              style={inputStyle}
            />
            <input
              type="number"
              min={1}
              placeholder="Количество (пусто = без лимита)"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              style={inputStyle}
            />
          </div>
          <textarea
            placeholder="Инструкция после одобрения (необязательно)"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            rows={2}
            style={inputStyle}
          />
          <div style={{ display: "flex", gap: ".5rem" }}>
            <button type="button" className="era-btn-primary" disabled={creating || !canSave} onClick={() => void handleSave()}>
              {editingId != null ? "Сохранить изменения" : "Добавить предложение"}
            </button>
            {editingId != null && <button type="button" disabled={creating} onClick={resetForm}>Отмена</button>}
          </div>
        </div>
      </Card>

      {offers.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {offers.status === "error" && <EmptyState text="Не удалось загрузить предложения." />}
      {offers.status === "ready" && offers.data.length === 0 && <EmptyState text="Предложений пока нет." />}
      {offers.status === "ready" &&
        offers.data.map((offer) => (
          <Card key={offer.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{offer.title}</strong>
              {!offer.is_active && <StatusBadge label="скрыто" tone="neutral" />}
            </div>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
              {offer.partner_name} · {offer.point_cost} баллов · {offer.quantity ?? "без лимита"}
            </p>
            <p style={{ margin: "0 0 .55rem", fontSize: ".82rem", lineHeight: 1.45 }}>{offer.description}</p>
            {offer.instruction && <p style={{ margin: "0 0 .55rem", color: "var(--era-text-muted)", fontSize: ".78rem" }}>После одобрения: {offer.instruction}</p>}
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              <button type="button" disabled={busyId === offer.id} onClick={() => startEditing(offer)}>Редактировать</button>
              <button
                type="button"
                disabled={busyId === offer.id}
                onClick={() => void runAction(offer.id, () => setOfferActive(offer.id, !offer.is_active))}
              >
                {offer.is_active ? "Скрыть" : "Активировать"}
              </button>
              <button
                type="button"
                disabled={busyId === offer.id}
                onClick={() => void runAction(offer.id, () => archiveOffer(offer.id))}
              >
                Архивировать
              </button>
            </div>
          </Card>
        ))}
    </div>
  );
}
