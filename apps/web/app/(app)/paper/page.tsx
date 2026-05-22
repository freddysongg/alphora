import { redirect } from "next/navigation";
import type { Route } from "next";

export default function PaperIndexPage(): never {
  redirect("/paper/portfolio" as Route);
}
