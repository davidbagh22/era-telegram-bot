import { useCallback, useState } from "react";
import {
  archiveOffer,
  createOffer,
  describeActionError,
  fetchAdminOffers,
  fetchAdminPartners,
  setOfferActive,
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

// The Mini App equivalent of the create/list/toggle/archive half of
// app/handlers/admin/partner_offers_block16.py — managing the offers
// themselves. Reviewing participants' applications to these offers is a
// separate screen (OfferApplicationsPanel), since it was already covered
// before this admin gap was found.
export function OffersPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const offers = useAsync(() => fetchAdminOffers(), [refreshKey]);
  const partners = useAsync(() => fetchAdminPartners(), []);

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

  const canCreate = partnerId && title.trim() && description.trim() && pointCost.trim() !== "";

  const handleCreate = useCallback(async () => {
    if (!canCreate) return;
    setCreating(true);
    setActionError(null);
    try {
      await createOffer({
        partner_id: Number(partnerId),
        title: title.trim(),
        description: description.trim(),
        point_cost: Number(pointCost),
        quantity: quantity.trim() ? Number(quantity) : null,
        instruction: instruction.trim(),
      });
      setTitle("");
      setDescription("");
      setPointCost("");
      setQuantity("");
      setInstruction("");
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [canCreate, partnerId, title, description, pointCost, quantity, instruction, refresh]);

  const runAction = useCallback(
    async (offerId: number, action: () => Promise<unknown>) => {
      setBusyId(offerId);
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
        <strong>Новое предложение</strong>
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
              placeholder="Стоимость в баллах"
              value={pointCost}
              onChange={(e) => setPointCost(e.target.value)}
              style={inputStyle}
            />
            <input
              type="number"
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
          <button type="button" className="era-btn-primary" disabled={creating || !canCreate} onClick={handleCreate}>
            Добавить предложение
          </button>
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
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                type="button"
                disabled={busyId === offer.id}
                onClick={() => runAction(offer.id, () => setOfferActive(offer.id, !offer.is_active))}
              >
                {offer.is_active ? "Скрыть" : "Активировать"}
              </button>
              <button
                type="button"
                disabled={busyId === offer.id}
                onClick={() => runAction(offer.id, () => archiveOffer(offer.id))}
              >
                Архивировать
              </button>
            </div>
          </Card>
        ))}
    </div>
  );
}
