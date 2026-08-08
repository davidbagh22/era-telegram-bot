import { useCallback, useState } from "react";
import { describeActionError, fetchAuctions, placeBid } from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { useAsync } from "../../hooks/useAsync";

// Points-based auctions — the participant-facing half of
// app/handlers/participant/auction_block17.py. Distinct from the offers
// list: the cost is whatever the winning bid turns out to be, decided only
// after bidding closes and an admin confirms a winner — points are never
// deducted just for placing a bid.
export function AuctionsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAuctions(), [refreshKey]);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleBid = useCallback(
    async (auctionId: number, minimum: number) => {
      const raw = amounts[auctionId];
      const amount = raw ? Number(raw) : minimum;
      if (!Number.isFinite(amount) || amount <= 0) return;
      setBusyId(auctionId);
      setActionError(null);
      try {
        await placeBid(auctionId, amount);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [amounts, refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить аукционы." />;
  }
  if (state.data.length === 0) {
    return <EmptyState text="Активных лотов пока нет." />;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      {state.data.map((auction) => (
        <Card key={auction.id}>
          <strong>{auction.title}</strong>
          <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>{auction.description}</p>
          <p style={{ margin: "0 0 0.5rem", fontSize: "0.875rem" }}>
            Последняя ставка: {auction.top_bid ?? "ставок пока нет"}
            {auction.top_bidder ? ` · Лидер: ${auction.top_bidder}` : ""}
          </p>
          {auction.my_bid != null && (
            <p style={{ margin: "0 0 0.5rem", color: "var(--era-violet)", fontSize: "0.875rem" }}>
              Ваша ставка: {auction.my_bid} баллов
            </p>
          )}
          {auction.is_open ? (
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <input
                type="number"
                placeholder={`от ${auction.next_minimum_bid}`}
                value={amounts[auction.id] ?? ""}
                onChange={(event) =>
                  setAmounts((previous) => ({ ...previous, [auction.id]: event.target.value }))
                }
                style={{
                  flex: 1,
                  fontFamily: "var(--era-font-body)",
                  padding: "0.5rem",
                  borderRadius: "0.5rem",
                  border: "1px solid var(--era-border)",
                  background: "var(--era-bg)",
                  color: "var(--era-text)",
                }}
              />
              <button
                type="button"
                className="era-btn-primary"
                disabled={busyId === auction.id}
                onClick={() => handleBid(auction.id, auction.next_minimum_bid)}
              >
                Сделать ставку
              </button>
            </div>
          ) : (
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              Приём ставок завершён. Победителя подтвердит администратор.
            </p>
          )}
        </Card>
      ))}
    </div>
  );
}
