import { redirect } from "next/navigation";
import type { Route } from "next";

export default function MarketsIndexPage(): never {
  redirect("/markets/screener" as Route);
}
