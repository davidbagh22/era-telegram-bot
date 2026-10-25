import { useCallback, useEffect, useMemo, useState } from "react";
import { describeActionError, fetchAuctions, placeBid } from "../../api/client";
import { BottomSheet } from "../../components/BottomSheet";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { AuctionIcon } from "../../components/icons";
import { useAsync } from "../../hooks/useAsync";
import type { Auction } from "../../types/opportunity";

// Points-based auctions — the participant-facing half of
// app/handlers/participant/auction_block17.py. Distinct from the offers
// list: the cost is whatever the winning bid turns out to be, decided only
// after bidding closes and an admin confirms a winner — points are never
// deducted just for placing a bid.
//
// 2026-08 master spec: premium marketplace redesign — hero card with a
// live countdown and current bid at a glance, a detail bottom sheet for
// the actual bid, immediate UI update after bidding. No lot photos (the
// backend Auction model has no image field — see docs/SYSTEM_FLOW_MATRIX.md)
// — the gradient + gavel glyph is the one branded cover, not a fake per-lot
// image pipeline.

function formatCountdown(endsAt: string): { label: string; urgent: boolean } {
  const remainingMs = new Date(endsAt).getTime() - Date.now();
  if (remainingMs <= 0) {
    return { label: "Приём ставок завершён", urgent: false };
  }
  const minutes = Math.floor(remainingMs / 60000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) {
    return { label: `Осталось ${days} д ${hours} ч`, urgent: false };
  }
  if (hours > 0) {
    return { label: `Осталось ${hours} ч ${mins} мин`, urgent: hours < 3 };
  }
  return { label: `Осталось ${Math.max(mins, 1)} мин`, urgent: true };
}

function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

interface AuctionHeroCardProps {
  auction: Auction;
  onOpen: () => void;
}

function AuctionHeroCard({ auction, onOpen }: AuctionHeroCardProps) {
  // Ticks once a minute — a lot's countdown doesn't need second-level
  // precision, and this keeps every card in the list from re-rendering
  // every second.
  useNow(60000);
  const countdown = formatCountdown(auction.ends_at);

  return (
    <Card style={{ padding: 0, overflow: "hidden" }}>
      <div
        style={{
          background: "var(--era-gradient)",
          color: "#fff",
          padding: "1rem",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "0.75rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
          <span
            style={{
              flexShrink: 0,
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: "rgba(255,255,255,0.18)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <AuctionIcon width={20} height={20} />
          </span>
          <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-lg)" }}>
            {auction.title}
          </strong>
        </div>
        {auction.is_open && (
          <span
            style={{
              flexShrink: 0,
              fontSize: "0.75rem",
              fontWeight: 600,
              padding: "0.25rem 0.5rem",
              borderRadius: "var(--era-radius-pill)",
              background: countdown.urgent ? "rgba(255,255,255,0.92)" : "rgba(255,255,255,0.18)",
              color: countdown.urgent ? "var(--era-red)" : "#fff",
              whiteSpace: "nowrap",
            }}
          >
            {countdown.label}
          </span>
        )}
      </div>
      <div style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div>
          <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--era-text-muted)" }}>Текущая ставка</p>
          <p style={{ margin: "0.125rem 0 0", fontSize: "1.5rem", fontFamily: "var(--era-font-display)" }}>
            {auction.top_bid ?? "—"}
            {auction.top_bid != null && <span style={{ fontSize: "0.875rem", fontWeight: 400 }}> баллов</span>}
          </p>
          {auction.top_bidder && (
            <p style={{ margin: "0.125rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
              Лидер: {auction.top_bidder}
            </p>
          )}
        </div>
        {auction.my_bid != null && (
          <p style={{ margin: 0, color: "var(--era-violet)", fontSize: "0.875rem", fontWeight: 600 }}>
            Ваша ставка: {auction.my_bid} баллов
          </p>
        )}
        {auction.is_open ? (
          <button type="button" className="era-btn-primary" onClick={onOpen}>
            Сделать ставку
          </button>
        ) : (
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
            Приём ставок завершён. Победителя подтвердит администратор.
          </p>
        )}
      </div>
    </Card>
  );
}

interface BidSheetProps {
  auction: Auction;
  onClose: () => void;
  onBid: (amount: number) => Promise<void>;
  busy: boolean;
  error: string | null;
}

function BidSheet({ auction, onClose, onBid, busy, error }: BidSheetProps) {
  const [amount, setAmount] = useState(String(auction.next_minimum_bid));

  return (
    <BottomSheet open onClose={onClose} title={auction.title}>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <p style={{ margin: 0, color: "var(--era-text-muted)" }}>{auction.description}</p>
        <p style={{ margin: 0, fontSize: "0.875rem" }}>
          Текущая ставка: {auction.top_bid ?? "ставок пока нет"}
          {auction.top_bidder ? ` · Лидер: ${auction.top_bidder}` : ""}
        </p>
        {auction.my_bid != null && (
          <p style={{ margin: 0, color: "var(--era-violet)", fontSize: "0.875rem" }}>
            Ваша текущая ставка: {auction.my_bid} баллов
          </p>
        )}
        {error && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{error}</p>}
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="number"
            placeholder={`от ${auction.next_minimum_bid}`}
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            style={{
              flex: 1,
              fontFamily: "var(--era-font-body)",
              padding: "0.625rem",
              borderRadius: "0.5rem",
              border: "1px solid var(--era-border)",
              background: "var(--era-bg)",
              color: "var(--era-text)",
            }}
          />
        </div>
        <button
          type="button"
          className="era-btn-primary"
          disabled={busy}
          onClick={() => {
            const parsed = amount ? Number(amount) : auction.next_minimum_bid;
            if (!Number.isFinite(parsed) || parsed <= 0) return;
            void onBid(parsed);
          }}
        >
          Подтвердить ставку
        </button>
      </div>
    </BottomSheet>
  );
}

export function AuctionsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAuctions(), [refreshKey]);
  const [openAuctionId, setOpenAuctionId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const openAuction = useMemo(
    () => (state.status === "ready" ? state.data.find((item) => item.id === openAuctionId) ?? null : null),
    [state, openAuctionId],
  );

  const handleBid = useCallback(
    async (auctionId: number, amount: number) => {
      setBusyId(auctionId);
      setActionError(null);
      try {
        await placeBid(auctionId, amount);
        // Immediate UI update: close the sheet and refetch right away
        // rather than leaving the stale pre-bid state up.
        setOpenAuctionId(null);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
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
      {state.data.map((auction) => (
        <AuctionHeroCard key={auction.id} auction={auction} onOpen={() => setOpenAuctionId(auction.id)} />
      ))}
      {openAuction && (
        <BidSheet
          auction={openAuction}
          onClose={() => setOpenAuctionId(null)}
          onBid={(amount) => handleBid(openAuction.id, amount)}
          busy={busyId === openAuction.id}
          error={actionError}
        />
      )}
    </div>
  );
}
