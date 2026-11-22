// A document's own page, for reading it (decision record 28). The tab it
// opens on comes from the address (?tab=summary), read in the browser, so
// the reader waits inside a Suspense boundary until it is known.

import { Suspense } from "react";

import { DocumentReader } from "@/components/document-reader";
import { Loading } from "@/components/query-states";

export default async function DocumentPage({
  params,
}: PageProps<"/environments/[id]/materials/[documentId]">) {
  const { id, documentId } = await params;
  return (
    <Suspense fallback={<Loading what="the document" lines={4} />}>
      <DocumentReader environmentId={id} documentId={documentId} />
    </Suspense>
  );
}
