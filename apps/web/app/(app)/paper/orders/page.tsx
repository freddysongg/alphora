import type { Metadata } from "next";
import type { ReactElement } from "react";

import { CapsLabel } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { OrdersTable } from "./orders-table";

export const metadata: Metadata = {
  title: "Orders · Alphora",
};

export const dynamic = "force-dynamic";

type PaperOrderPublic = components["schemas"]["PaperOrderPublic"];

const ORDER_LIMIT = 200;

interface LoadResult {
  orders: readonly PaperOrderPublic[];
  errorDetail: string | null;
}

async function loadOrders(): Promise<LoadResult> {
  try {
    const portfolioResponse = await getServerApi().GET(
      "/api/paper/portfolio",
      {
        cache: "force-cache",
        next: { tags: ["paper-portfolio"] },
      },
    );
    const snapshot = portfolioResponse.data;
    if (snapshot === undefined) {
      return { orders: [], errorDetail: null };
    }
    const ordersResponse = await getServerApi().GET("/api/paper/orders", {
      params: { query: { portfolio_id: snapshot.id, limit: ORDER_LIMIT } },
      cache: "force-cache",
      next: { tags: ["paper-orders"] },
    });
    const orders = ordersResponse.data ?? [];
    return { orders, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { orders: [], errorDetail: caught.detail };
    }
    throw caught;
  }
}

export default async function OrdersPage(): Promise<ReactElement> {
  const { orders, errorDetail } = await loadOrders();
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-6">
        <CapsLabel as="h1">ORDERS</CapsLabel>
      </header>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load orders: {errorDetail}
        </div>
      ) : null}
      <OrdersTable rows={orders} />
    </div>
  );
}
