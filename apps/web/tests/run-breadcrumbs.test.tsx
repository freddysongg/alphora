import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { RunBreadcrumbs } from "@/components/research/run-breadcrumbs";

const RUN_ID = "11111111-1111-4111-8111-111111111111";
const SECTOR_ENTITY_ID = "22222222-2222-4222-8222-222222222222";

describe("RunBreadcrumbs", () => {
  it("renders 'Run › Sector' for the sector variant, with Run linking back to the run detail and Sector as the current page", () => {
    render(<RunBreadcrumbs runId={RUN_ID} variant="sector" />);

    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    const runLink = within(nav).getByRole("link", { name: "Run" });
    expect(runLink).toHaveAttribute("href", `/research/runs/${RUN_ID}`);

    expect(within(nav).getByText("Sector")).toBeInTheDocument();
    expect(
      within(nav).queryByRole("link", { name: "Sector" }),
    ).not.toBeInTheDocument();

    expect(within(nav).getAllByText("›")).toHaveLength(1);
  });

  it("renders 'Run › Portfolio › Company' when the company variant has a portfolio parent, with Company as the current page", () => {
    render(
      <RunBreadcrumbs
        runId={RUN_ID}
        variant="company"
        parent="portfolio"
      />,
    );

    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    const runLink = within(nav).getByRole("link", { name: "Run" });
    expect(runLink).toHaveAttribute("href", `/research/runs/${RUN_ID}`);

    const portfolioLink = within(nav).getByRole("link", { name: "Portfolio" });
    expect(portfolioLink).toHaveAttribute(
      "href",
      `/research/runs/${RUN_ID}/portfolio-brief`,
    );

    expect(within(nav).getByText("Company")).toBeInTheDocument();
    expect(
      within(nav).queryByRole("link", { name: "Company" }),
    ).not.toBeInTheDocument();

    expect(within(nav).getAllByText("›")).toHaveLength(2);
  });

  it("renders 'Run › Sector › Company' when the company variant has a sector parent, with Sector linking to the sector brief detail page", () => {
    render(
      <RunBreadcrumbs
        runId={RUN_ID}
        variant="company"
        parent="sector"
        sectorEntityId={SECTOR_ENTITY_ID}
      />,
    );

    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    const runLink = within(nav).getByRole("link", { name: "Run" });
    expect(runLink).toHaveAttribute("href", `/research/runs/${RUN_ID}`);

    const sectorLink = within(nav).getByRole("link", { name: "Sector" });
    expect(sectorLink).toHaveAttribute(
      "href",
      `/research/runs/${RUN_ID}/sectors/${SECTOR_ENTITY_ID}`,
    );

    expect(within(nav).getByText("Company")).toBeInTheDocument();
    expect(
      within(nav).queryByRole("link", { name: "Company" }),
    ).not.toBeInTheDocument();

    expect(within(nav).getAllByText("›")).toHaveLength(2);
  });
});
