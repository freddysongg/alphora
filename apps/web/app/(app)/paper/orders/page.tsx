import type { Metadata } from "next";
import type { ReactElement } from "react";
import { CapsLabel } from "@/components/ui";
import { OrdersTable } from "./orders-table";

export const metadata: Metadata = {
  title: "Orders · Alphora",
};

export default function OrdersPage(): ReactElement {
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-6">
        <CapsLabel as="h1">ORDERS</CapsLabel>
      </header>
      <OrdersTable />
    </div>
  );
}
