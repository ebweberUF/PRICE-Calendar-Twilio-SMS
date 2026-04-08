import * as React from "react";
import { ISmsReminder } from "../services/ISmsReminder";
import StatusBadge from "./StatusBadge";

export interface IReminderTableProps {
  items: ISmsReminder[];
  showReplyColumns: boolean;
}

const formatDate = (iso: string): string => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
};

const formatDateTime = (iso: string): string => {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
};

const cellStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid rgba(255,255,255,0.1)",
  fontSize: "13px",
  verticalAlign: "middle",
  color: "#fff",
};

const headerStyle: React.CSSProperties = {
  ...cellStyle,
  fontWeight: 600,
  backgroundColor: "rgba(255,255,255,0.08)",
  position: "sticky" as "sticky",
  top: 0,
  fontSize: "12px",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  color: "rgba(255,255,255,0.6)",
};

const ReminderTable: React.FC<IReminderTableProps> = ({
  items,
  showReplyColumns,
}) => {
  if (items.length === 0) {
    return (
      <div
        style={{
          padding: "40px",
          textAlign: "center",
          color: "rgba(255,255,255,0.5)",
          fontSize: "14px",
        }}
      >
        No reminders found.
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto", maxHeight: "500px", overflowY: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          tableLayout: "auto",
        }}
      >
        <thead>
          <tr>
            <th style={headerStyle}>Subject ID</th>
            <th style={headerStyle}>Study</th>
            <th style={headerStyle}>Visit</th>
            <th style={headerStyle}>Event Date</th>
            <th style={headerStyle}>Location</th>
            <th style={headerStyle}>Type</th>
            <th style={headerStyle}>Status</th>
            {showReplyColumns && (
              <>
                <th style={headerStyle}>Reply</th>
                <th style={headerStyle}>Reply Time</th>
              </>
            )}
            <th style={headerStyle}>Sent</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.Id}
              style={{ cursor: "default" }}
              onMouseEnter={(e) =>
                ((e.currentTarget as HTMLElement).style.backgroundColor =
                  "rgba(255,255,255,0.05)")
              }
              onMouseLeave={(e) =>
                ((e.currentTarget as HTMLElement).style.backgroundColor = "")
              }
            >
              <td style={{ ...cellStyle, fontWeight: 600 }}>
                {item.SubjectID}
              </td>
              <td style={cellStyle}>{item.StudyCode}</td>
              <td style={cellStyle}>{item.VisitName}</td>
              <td style={cellStyle}>{formatDateTime(item.EventStart)}</td>
              <td style={cellStyle}>{item.Location}</td>
              <td style={cellStyle}>
                <span
                  style={{
                    padding: "2px 6px",
                    borderRadius: "4px",
                    backgroundColor:
                      item.ReminderType === "24h" ? "#fff4ce" : "#e1dfdd",
                    fontSize: "11px",
                    fontWeight: 600,
                  }}
                >
                  {item.ReminderType}
                </span>
              </td>
              <td style={cellStyle}>
                <StatusBadge status={item.ResponseStatus} />
              </td>
              {showReplyColumns && (
                <>
                  <td style={cellStyle}>{item.ResponseText || ""}</td>
                  <td style={cellStyle}>
                    {formatDateTime(item.ResponseAt)}
                  </td>
                </>
              )}
              <td style={{ ...cellStyle, color: "rgba(255,255,255,0.4)", fontSize: "12px" }}>
                {formatDate(item.Created)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default ReminderTable;
