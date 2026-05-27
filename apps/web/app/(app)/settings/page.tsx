import { redirect } from "next/navigation";
import type { Route } from "next";

export default function SettingsIndexPage(): never {
  redirect("/settings/api-keys" as Route);
}
