import * as React from "react";
import {
  ResponseStatus,
  STATUS_LABELS,
  STATUS_COLORS,
} from "../services/ISmsReminder";

export interface IStatusBadgeProps {
  status: string;
}

const StatusBadge: React.FC<IStatusBadgeProps> = ({ status }) => {
  const key = (status || "pending") as ResponseStatus;
  const label = STATUS_LABELS[key] || status;
  const color = STATUS_COLORS[key] || "#797775";

  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: "12px",
        backgroundColor: color,
        color: "#fff",
        fontSize: "12px",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.5px",
      }}
    >
      {label}
    </span>
  );
};

export default StatusBadge;
