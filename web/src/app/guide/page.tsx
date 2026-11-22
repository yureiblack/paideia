import type { Metadata } from "next";

import { Guide } from "@/components/guide";

export const metadata: Metadata = { title: "Guide · Paideia" };

export default function GuidePage() {
  return <Guide />;
}
