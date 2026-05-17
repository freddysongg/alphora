import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Geist, Geist_Mono } from "next/font/google";
import { Toaster } from "sonner";
import { NoiseGrain } from "@/components/system/noise-grain";
import "./globals.css";

const geistSans = Geist({
  subsets: ["latin"],
  variable: "--font-geist-sans",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-geist-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Alphora",
  description: "Research desk for US equities",
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps): ReactNode {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable}`}
    >
      <body className="min-h-[100dvh] bg-canvas text-fg">
        <NoiseGrain />
        <div className="relative z-10">{children}</div>
        <Toaster
          theme="dark"
          position="bottom-right"
          style={
            {
              "--normal-bg": "var(--color-surface)",
              "--normal-border": "var(--color-line)",
            } as React.CSSProperties
          }
        />
      </body>
    </html>
  );
}
