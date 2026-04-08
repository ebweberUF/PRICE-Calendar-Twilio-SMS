import * as React from "react";
import { ISmsDashboardProps } from "./ISmsDashboardProps";
import { ISmsReminder, ReminderView } from "../services/ISmsReminder";
import { SmsReminderService } from "../services/SmsReminderService";
import SummaryCards from "./SummaryCards";
import ReminderTable from "./ReminderTable";

interface ISmsDashboardState {
  view: ReminderView;
  items: ISmsReminder[];
  counts: Record<string, number>;
  loading: boolean;
  error: string;
  studyFilter: string;
  studies: string[];
}

const TAB_STYLE: React.CSSProperties = {
  padding: "10px 20px",
  border: "none",
  borderBottom: "3px solid transparent",
  backgroundColor: "transparent",
  fontSize: "14px",
  fontWeight: 600,
  color: "rgba(255,255,255,0.5)",
  cursor: "pointer",
  transition: "all 0.15s",
};

const TAB_ACTIVE: React.CSSProperties = {
  ...TAB_STYLE,
  color: "#4db8ff",
  borderBottomColor: "#4db8ff",
};

export default class SmsDashboard extends React.Component<
  ISmsDashboardProps,
  ISmsDashboardState
> {
  private service: SmsReminderService;

  constructor(props: ISmsDashboardProps) {
    super(props);
    this.service = new SmsReminderService(props.context, props.siteUrl);
    this.state = {
      view: "upcoming",
      items: [],
      counts: {},
      loading: true,
      error: "",
      studyFilter: "",
      studies: [],
    };
  }

  public async componentDidMount(): Promise<void> {
    await this.loadData("upcoming");
    await this.loadCounts();
  }

  private async loadCounts(): Promise<void> {
    try {
      const counts = await this.service.getStatusCounts();
      this.setState({ counts });
    } catch (err) {
      console.error("Failed to load counts:", err);
    }
  }

  private async loadData(view: ReminderView): Promise<void> {
    this.setState({ loading: true, error: "", view });
    try {
      let items: ISmsReminder[];
      switch (view) {
        case "upcoming":
          items = await this.service.getUpcoming();
          break;
        case "awaiting":
          items = await this.service.getAwaitingReply();
          break;
        case "history":
          items = await this.service.getHistory();
          break;
        default:
          items = [];
      }

      const studies = Array.from(
        new Set(items.map((i) => i.StudyCode).filter(Boolean))
      ).sort();

      this.setState({ items, studies, loading: false });
    } catch (err) {
      this.setState({
        error: `Failed to load data: ${err}`,
        loading: false,
      });
    }
  }

  private onTabClick = (view: ReminderView): void => {
    this.setState({ studyFilter: "" });
    this.loadData(view);
  };

  private onStudyFilter = (
    e: React.ChangeEvent<HTMLSelectElement>
  ): void => {
    this.setState({ studyFilter: e.target.value });
  };

  private onRefresh = (): void => {
    this.loadData(this.state.view);
    this.loadCounts();
  };

  public render(): React.ReactElement<ISmsDashboardProps> {
    const { view, items, counts, loading, error, studyFilter, studies } =
      this.state;

    const filtered = studyFilter
      ? items.filter((i) => i.StudyCode === studyFilter)
      : items;

    return (
      <div style={{ fontFamily: "'Segoe UI', sans-serif", padding: "20px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "16px",
          }}
        >
          <h2 style={{ margin: 0, fontWeight: 600, fontSize: "20px", color: "#fff" }}>
            SMS Reminder Dashboard
          </h2>
          <button
            onClick={this.onRefresh}
            style={{
              padding: "6px 16px",
              border: "1px solid rgba(255,255,255,0.3)",
              borderRadius: "4px",
              backgroundColor: "rgba(255,255,255,0.1)",
              color: "#fff",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            Refresh
          </button>
        </div>

        <SummaryCards counts={counts} />

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderBottom: "1px solid rgba(255,255,255,0.1)",
            marginBottom: "12px",
          }}
        >
          <div>
            <button
              style={view === "upcoming" ? TAB_ACTIVE : TAB_STYLE}
              onClick={() => this.onTabClick("upcoming")}
            >
              Upcoming
            </button>
            <button
              style={view === "awaiting" ? TAB_ACTIVE : TAB_STYLE}
              onClick={() => this.onTabClick("awaiting")}
            >
              Awaiting Reply
            </button>
            <button
              style={view === "history" ? TAB_ACTIVE : TAB_STYLE}
              onClick={() => this.onTabClick("history")}
            >
              History
            </button>
          </div>
          {studies.length > 1 && (
            <select
              value={studyFilter}
              onChange={this.onStudyFilter}
              style={{
                padding: "4px 8px",
                border: "1px solid rgba(255,255,255,0.3)",
                backgroundColor: "rgba(255,255,255,0.1)",
                color: "#fff",
                borderRadius: "4px",
                fontSize: "13px",
              }}
            >
              <option value="">All Studies</option>
              {studies.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          )}
        </div>

        {error && (
          <div
            style={{
              padding: "12px",
              backgroundColor: "rgba(211,52,56,0.2)",
              color: "#ff6b6b",
              borderRadius: "4px",
              marginBottom: "12px",
            }}
          >
            {error}
          </div>
        )}

        {loading ? (
          <div
            style={{
              padding: "40px",
              textAlign: "center",
              color: "rgba(255,255,255,0.4)",
            }}
          >
            Loading...
          </div>
        ) : (
          <ReminderTable
            items={filtered}
            showReplyColumns={view !== "upcoming"}
          />
        )}

        <div
          style={{
            marginTop: "12px",
            fontSize: "11px",
            color: "rgba(255,255,255,0.4)",
            textAlign: "right",
          }}
        >
          {filtered.length} reminder{filtered.length !== 1 ? "s" : ""}
          {studyFilter ? ` (${studyFilter})` : ""}
        </div>
      </div>
    );
  }
}
