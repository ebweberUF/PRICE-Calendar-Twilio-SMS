import { WebPartContext } from "@microsoft/sp-webpart-base";
import { SPHttpClient, SPHttpClientResponse } from "@microsoft/sp-http";
import { ISmsReminder } from "./ISmsReminder";

const LIST_NAME = "SMS Reminder Log";
const SELECT_FIELDS = [
  "Id",
  "Title",
  "SubjectID",
  "StudyCode",
  "VisitName",
  "EventStart",
  "Location",
  "ExperimenterEmail",
  "ReminderType",
  "ResponseStatus",
  "ResponseText",
  "ResponseAt",
  "MosioTransactionID",
  "CalendarEventID",
  "PhoneHash",
  "NotificationSent",
  "Created",
  "Modified",
].join(",");

export class SmsReminderService {
  private context: WebPartContext;
  private siteUrl: string;

  constructor(context: WebPartContext, siteUrl: string) {
    this.context = context;
    this.siteUrl = siteUrl;
  }

  private async getItems(
    filter?: string,
    orderBy?: string,
    top: number = 200
  ): Promise<ISmsReminder[]> {
    let url =
      `${this.siteUrl}/_api/web/lists/getbytitle('${LIST_NAME}')/items` +
      `?$select=${SELECT_FIELDS}&$top=${top}`;

    if (filter) {
      url += `&$filter=${encodeURIComponent(filter)}`;
    }
    if (orderBy) {
      url += `&$orderby=${encodeURIComponent(orderBy)}`;
    }

    const response: SPHttpClientResponse =
      await this.context.spHttpClient.get(
        url,
        SPHttpClient.configurations.v1,
        {
          headers: { Accept: "application/json;odata=nometadata" },
        }
      );

    if (!response.ok) {
      console.error("Failed to fetch reminders:", response.statusText);
      return [];
    }

    const data = await response.json();
    return data.value || [];
  }

  /**
   * Upcoming: pending reminders for future events, sorted by event date.
   */
  public async getUpcoming(): Promise<ISmsReminder[]> {
    const now = new Date().toISOString();
    return this.getItems(
      `EventStart ge datetime'${now}' and ResponseStatus eq 'pending'`,
      "EventStart asc"
    );
  }

  /**
   * Awaiting reply: sent reminders with no response yet (event may be past or future).
   */
  public async getAwaitingReply(): Promise<ISmsReminder[]> {
    return this.getItems(
      `ResponseStatus eq 'pending'`,
      "EventStart asc"
    );
  }

  /**
   * History: all reminders with a final status, most recent first.
   */
  public async getHistory(): Promise<ISmsReminder[]> {
    return this.getItems(
      `ResponseStatus ne 'pending'`,
      "Modified desc",
      500
    );
  }

  /**
   * All reminders (no filter), most recent first.
   */
  public async getAll(): Promise<ISmsReminder[]> {
    return this.getItems(undefined, "Created desc", 500);
  }

  /**
   * Get status summary counts.
   */
  public async getStatusCounts(): Promise<Record<string, number>> {
    const all = await this.getAll();
    const counts: Record<string, number> = {};
    for (const item of all) {
      const status = item.ResponseStatus || "unknown";
      counts[status] = (counts[status] || 0) + 1;
    }
    return counts;
  }
}
