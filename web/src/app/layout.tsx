import type { Metadata } from "next";
import { Instrument_Sans, Instrument_Serif, JetBrains_Mono } from "next/font/google";
// KaTeX's styles and fonts, served with the page (decision record 24).
import "katex/dist/katex.min.css";
import "./globals.css";

import { SiteHeader } from "@/components/site-header";
import { THEME_SCRIPT } from "@/lib/theme";

import { Providers } from "./providers";

// The Broadsheet type (decision record 25): a display serif for headlines,
// names and numbers, a grotesque for reading, a monospace for labels.
const display = Instrument_Serif({
  variable: "--font-instrument-serif",
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

const text = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
});

const mono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

// No title here: the home page sets "Paideia", and an environment's pages
// set their own once its name has loaded (environment-shell.tsx). A title
// here would compete with theirs.
export const metadata: Metadata = {
  description: "An adaptive learning workspace",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The theme script sets data-theme before React runs, so the server's
    // markup and the page differ on purpose there.
    <html
      lang="en"
      className={`${display.variable} ${text.variable} ${mono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col">
        <Providers>
          <SiteHeader />
          <main className="mx-auto flex w-full max-w-[1440px] flex-1 flex-col">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
