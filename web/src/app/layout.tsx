import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
// KaTeX's styles and fonts, served with the page (decision record 24).
import "katex/dist/katex.min.css";
import "./globals.css";

import { SiteHeader } from "@/components/site-header";

import { Providers } from "./providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
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
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Providers>
          <SiteHeader />
          <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
