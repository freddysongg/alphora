import { redirect } from "next/navigation";
import type { Route } from "next";

export default function ResearchIndexPage(): never {
  redirect("/research/runs" as Route);
}
