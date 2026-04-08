import * as React from "react";
import * as ReactDom from "react-dom";
import { Version } from "@microsoft/sp-core-library";
import { BaseClientSideWebPart } from "@microsoft/sp-webpart-base";
import {
  IPropertyPaneConfiguration,
  PropertyPaneTextField,
} from "@microsoft/sp-property-pane";

import SmsDashboard from "./components/SmsDashboard";
import { ISmsDashboardProps } from "./components/ISmsDashboardProps";

export interface ISmsDashboardWebPartProps {
  description: string;
}

export default class SmsDashboardWebPart extends BaseClientSideWebPart<ISmsDashboardWebPartProps> {
  public render(): void {
    const element: React.ReactElement<ISmsDashboardProps> =
      React.createElement(SmsDashboard, {
        context: this.context,
        siteUrl: this.context.pageContext.web.absoluteUrl,
      });

    ReactDom.render(element, this.domElement);
  }

  protected onDispose(): void {
    ReactDom.unmountComponentAtNode(this.domElement);
  }

  protected get dataVersion(): Version {
    return Version.parse("1.0");
  }

  protected getPropertyPaneConfiguration(): IPropertyPaneConfiguration {
    return {
      pages: [
        {
          header: { description: "SMS Reminder Dashboard Settings" },
          groups: [
            {
              groupName: "General",
              groupFields: [
                PropertyPaneTextField("description", {
                  label: "Description",
                }),
              ],
            },
          ],
        },
      ],
    };
  }
}
