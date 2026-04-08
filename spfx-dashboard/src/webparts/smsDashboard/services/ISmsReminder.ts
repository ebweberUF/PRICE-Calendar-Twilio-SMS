export interface ISmsReminder {
  Id: number;
  Title: string;
  SubjectID: string;
  StudyCode: string;
  VisitName: string;
  EventStart: string;
  Location: string;
  ExperimenterEmail: string;
  ReminderType: string;
  ResponseStatus: string;
  ResponseText: string;
  ResponseAt: string;
  MosioTransactionID: string;
  CalendarEventID: string;
  PhoneHash: string;
  NotificationSent: boolean;
  Created: string;
  Modified: string;
}

export type ReminderView = "upcoming" | "awaiting" | "history";

export type ResponseStatus =
  | "pending"
  | "confirmed"
  | "reschedule"
  | "cancel"
  | "no_response";

export const STATUS_LABELS: Record<ResponseStatus, string> = {
  pending: "Pending",
  confirmed: "Confirmed",
  reschedule: "Reschedule",
  cancel: "Cancelled",
  no_response: "No Response",
};

export const STATUS_COLORS: Record<ResponseStatus, string> = {
  pending: "#0078d4",
  confirmed: "#107c10",
  reschedule: "#ca5010",
  cancel: "#d13438",
  no_response: "#797775",
};
