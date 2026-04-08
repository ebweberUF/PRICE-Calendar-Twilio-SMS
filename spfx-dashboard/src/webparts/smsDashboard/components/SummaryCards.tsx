import * as React from "react";
import { STATUS_COLORS } from "../services/ISmsReminder";

export interface ISummaryCardsProps {
  counts: Record<string, number>;
}

const CARD_ORDER = ["pending", "confirmed", "reschedule", "cancel", "no_response"];
const CARD_LABELS: Record<string, string> = {
  pending: "Pending",
  confirmed: "Confirmed",
  reschedule: "Reschedule",
  cancel: "Cancelled",
  no_response: "No Response",
};

const SummaryCards: React.FC<ISummaryCardsProps> = ({ counts }) => {
  const total = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div style={{ display: "flex", gap: "12px", marginBottom: "20px", flexWrap: "wrap" }}>
      <div
        style={{
          padding: "16px 24px",
          borderRadius: "8px",
          backgroundColor: "rgba(255,255,255,0.08)",
          border: "1px solid rgba(255,255,255,0.15)",
          minWidth: "100px",
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: "28px", fontWeight: 700, color: "#fff" }}>{total}</div>
        <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.6)" }}>Total</div>
      </div>
      {CARD_ORDER.map((status) => (
        <div
          key={status}
          style={{
            padding: "16px 24px",
            borderRadius: "8px",
            backgroundColor: "rgba(255,255,255,0.08)",
            border: "1px solid rgba(255,255,255,0.15)",
            borderLeft: `4px solid ${(STATUS_COLORS as Record<string, string>)[status] || "#797775"}`,
            minWidth: "100px",
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: "28px", fontWeight: 700, color: "#fff" }}>
            {counts[status] || 0}
          </div>
          <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.6)" }}>
            {CARD_LABELS[status] || status}
          </div>
        </div>
      ))}
    </div>
  );
};

export default SummaryCards;
