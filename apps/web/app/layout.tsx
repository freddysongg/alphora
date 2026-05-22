import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Plus_Jakarta_Sans, Fira_Code } from "next/font/google";
import { Toaster } from "sonner";
import { NoiseGrain } from "@/components/system/noise-grain";
import "./globals.css";

const jakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-jakarta",
  display: "swap",
});

const firaCode = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-fira",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Alphora",
  description: "Research desk for US equities",
  icons: {
    icon: [
      { url: "/alphora.png", type: "image/png" },
      { url: "/favicon.ico", sizes: "any" },
    ],
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
      className={`${jakartaSans.variable} ${firaCode.variable}`}
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
