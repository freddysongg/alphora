import type { Metadata } from "next";
import type { ReactElement } from "react";
import { Screener } from "./screener";

export const metadata: Metadata = {
  title: "Screener · Alphora",
};

export default function ScreenerPage(): ReactElement {
  return <Screener />;
}
