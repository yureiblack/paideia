import type { Metadata } from "next";

import { Dashboard } from "@/components/dashboard";

export const metadata: Metadata = { title: "Paideia" };

export default function Home() {
  return <Dashboard />;
}
