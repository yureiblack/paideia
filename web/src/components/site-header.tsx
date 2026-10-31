// The bar across the top of every page.

import Link from "next/link";

import { ApiStatus } from "@/components/api-status";

export function SiteHeader() {
  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Paideia
        </Link>
        <ApiStatus />
      </div>
    </header>
  );
}
