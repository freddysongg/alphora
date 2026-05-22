import { redirect } from "next/navigation";
import type { Route } from "next";

export default function DataHealthIndexPage(): never {
  redirect("/data-health/providers" as Route);
}
