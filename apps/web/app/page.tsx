import { redirect } from "next/navigation";
import type { Route } from "next";

export default function HomePage(): never {
  redirect("/research/runs" as Route);
}
