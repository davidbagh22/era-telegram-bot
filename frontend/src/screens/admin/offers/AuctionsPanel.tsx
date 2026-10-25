import { useCallback, useState } from "react";
import {
  cancelAuction,
  confirmAuctionWinner,
  createAuction,
  deliverAuction,
  describeActionError,
  fetchAdminAuctions,
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

const STATUS_LABELS: Record<string, string> = {
  active: "идут ставки",
  completed: "победитель подтверждён",
  delivered: "лот передан",
  cancelled: "отменён",
};

// The Mini App equivalent of the admin half of
// app/handlers/admin/auction_block17.py — create a lot, confirm the
// winner once bidding closes, mark it delivered, or cancel without a
// winner. The participant side (browse + bid) lives in
// OpportunitiesScreen's "Аукционы" tab.
export function AuctionsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminAuctions(), [refreshKey]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [minimumBid, setMinimumBid] = useState("");
  const [bidStep, setBidStep] = useState("");
  const [endsAt, setEndsAt] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const canCreate = title.trim() && description.trim() && minimumBid.trim() && bidStep.trim() && endsAt;

  const handleCreate = useCallback(async () => {
    if (!canCreate) return;
    setCreating(true);
    setActionError(null);
    try {
      // <input type="datetime-local"> gives "YYYY-MM-DDTHH:MM" — the API
      // expects a space, matching the bot's own "ДД.ММ.ГГГГ ЧЧ:ММ" input
      // reinterpreted as ISO for the web form.
      const ends_at = endsAt.replace("T", " ");
      await createAuction({
        title: title.trim(),
        description: description.trim(),
        minimum_bid: Number(minimumBid),
        bid_step: Number(bidStep),
        ends_at,
      });
      setTitle("");
      setDescription("");
      setMinimumBid("");
      setBidStep("");
      setEndsAt("");
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [canCreate, title, description, minimumBid, bidStep, endsAt, refresh]);

  const runAction = useCallback(
    async (auctionId: number, action: () => Promise<unknown>) => {
      setBusyId(auctionId);
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
        <strong>Новый лот</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
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
              placeholder="Стартовая ставка"
              value={minimumBid}
              onChange={(e) => setMinimumBid(e.target.value)}
              style={inputStyle}
            />
            <input
              type="number"
              placeholder="Шаг ставки"
              value={bidStep}
              onChange={(e) => setBidStep(e.target.value)}
              style={inputStyle}
            />
          </div>
          <input
            type="datetime-local"
            value={endsAt}
            onChange={(e) => setEndsAt(e.target.value)}
            style={inputStyle}
          />
          <button type="button" className="era-btn-primary" disabled={creating || !canCreate} onClick={handleCreate}>
            Опубликовать лот
          </button>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить аукционы." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Лотов пока нет." />}
      {state.status === "ready" &&
        state.data.map((auction) => (
          <Card key={auction.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{auction.title}</strong>
              <StatusBadge label={STATUS_LABELS[auction.status] ?? auction.status} tone="violet" />
            </div>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{auction.description}</p>
            <p style={{ margin: "0 0 0.5rem", fontSize: "0.875rem" }}>
              Ставок: {auction.bids.length} · Последняя: {auction.top_bid ?? "нет"}
            </p>
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {auction.status === "active" && (
                <>
                  <button
                    type="button"
                    className="era-btn-primary"
                    disabled={busyId === auction.id}
                    onClick={() => runAction(auction.id, () => confirmAuctionWinner(auction.id))}
                  >
                    Подтвердить победителя
                  </button>
                  <button
                    type="button"
                    disabled={busyId === auction.id}
                    onClick={() => runAction(auction.id, () => cancelAuction(auction.id))}
                  >
                    Закрыть без победителя
                  </button>
                </>
              )}
              {auction.status === "completed" && (
                <button
                  type="button"
                  disabled={busyId === auction.id}
                  onClick={() => runAction(auction.id, () => deliverAuction(auction.id))}
                >
                  Лот передан победителю
                </button>
              )}
            </div>
          </Card>
        ))}
    </div>
  );
}
