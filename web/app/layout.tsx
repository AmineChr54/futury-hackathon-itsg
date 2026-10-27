import type { Metadata, Viewport } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Condensed } from "next/font/google";
import "./globals.css";

const body = IBM_Plex_Sans({ variable: "--font-plex", subsets: ["latin"], weight: ["400", "600", "700"] });
const display = IBM_Plex_Sans_Condensed({ variable: "--font-plex-condensed", subsets: ["latin"], weight: ["600", "700"] });
const mono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400"] });

export const metadata: Metadata = {
  title: "ITSG Spec Pipeline",
  description: "From specification to certified test, in one session. Futury Build Days 2026, ITSG challenge.",
};

export const viewport: Viewport = {
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f6f4f4" }, { media: "(prefers-color-scheme: dark)", color: "#131112" }],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${body.variable} ${display.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
