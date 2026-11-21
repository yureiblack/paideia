// A learner's journey through one subject, end to end (decision record 22):
// the roadmap's twelve scenarios, in order, through the page as a learner
// uses it, against the real API, worker, database, PDF reading, embeddings
// and reranker. Only the language model is a stand-in (api/tests/e2e/model.py):
// it names each concept after its passage's heading, writes summaries as
// "An overview of N passages." and stages as "Title N".

import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const PDFS = path.join(__dirname, ".state", "pdfs");
const WEEK_1 = "Week 1 processes.pdf";
const WEEK_2 = "Week 2 memory.pdf";

function tab(page: Page, name: string) {
  return page
    .getByRole("navigation", { name: "Environment sections" })
    .getByRole("link", { name, exact: true });
}

// A document's card on the Materials tab, and the update its upload made.
function documentCard(page: Page, filename: string) {
  return page
    .getByRole("listitem")
    .filter({ has: page.getByRole("heading", { name: filename, exact: true }) });
}

function update(page: Page, filename: string) {
  return page
    .getByRole("region", { name: "Updates" })
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: `Added ${filename}`, exact: true }) });
}

test("a learner's journey through one subject", async ({ page }) => {
  // Anything that went wrong on the way, checked at the end: an uncaught
  // error, an error the page logged, or a request the API refused.
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`uncaught: ${error.message}`));
  page.on("console", (message) => {
    // The browser's own line for every refused request; those are checked
    // below with their addresses instead.
    if (message.type() === "error" && !message.text().startsWith("Failed to load resource")) {
      problems.push(`logged: ${message.text()}`);
    }
  });
  page.on("response", (response) => {
    if (response.status() < 400) return;
    const { pathname } = new URL(response.url());
    // A document's summary answers 404 until it is written, which the page
    // shows as "not written yet" (src/lib/api.ts, getSummary).
    if (response.status() === 404 && /^\/api\/documents\/[^/]+\/summary$/.test(pathname)) return;
    problems.push(`${response.status()} ${response.request().method()} ${pathname}`);
  });

  await test.step("1. Create an environment", async () => {
    await page.goto("/");
    await page.getByRole("button", { name: "New environment" }).click();
    await page.getByRole("textbox", { name: "Name" }).fill("Operating Systems");
    await page.getByRole("button", { name: "Create environment" }).click();

    await expect(page.getByRole("heading", { level: 1, name: "Operating Systems" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Recent material" })).toContainText(
      "No materials yet.",
    );
  });

  await test.step("2. Upload a PDF", async () => {
    await tab(page, "Materials").click();
    await page.getByLabel("Choose a PDF to upload").setInputFiles(path.join(PDFS, WEEK_1));

    await expect(documentCard(page, WEEK_1)).toBeVisible();
  });

  await test.step("3. Wait for processing", async () => {
    // Read, then summarised, concepts extracted, mapped and staged.
    await expect(documentCard(page, WEEK_1)).toContainText("Ready · 3 pages");
    await expect(update(page, WEEK_1)).toContainText("Done");
    // A finished update is one line until "What changed" opens it.
    await update(page, WEEK_1).getByRole("button", { name: "What changed" }).click();
    // The concepts the document brought, by name.
    await expect(
      update(page, WEEK_1).getByRole("list", { name: "Concepts" }).getByRole("listitem"),
    ).toHaveText(["+ CPU Scheduling", "+ Processes", "+ Threads"]);
  });

  await test.step("4. Search the source material", async () => {
    await tab(page, "Search").click();
    await page
      .getByRole("searchbox", { name: "Search this environment's materials" })
      .fill("how does round robin preempt a thread");
    await page.getByRole("button", { name: "Search", exact: true }).click();

    const best = page.getByRole("list", { name: "Search results" }).getByRole("listitem").first();
    await expect(best).toContainText("Page 3 · CPU Scheduling");
    await expect(best).toContainText("Round robin gives each one a fixed time quantum");
  });

  await test.step("5. View a citation in its page", async () => {
    const best = page.getByRole("list", { name: "Search results" }).getByRole("listitem").first();
    await best.getByRole("button", { name: "Show in page" }).click();

    const source = page.getByRole("region", { name: `${WEEK_1}, Page 3` });
    await expect(source).toBeVisible();
    // The cited passage is marked within its page.
    await expect(source.locator("mark")).toContainText("Round robin gives each one");
  });

  await test.step("6. Read the summary, written from the document", async () => {
    await tab(page, "Summary").click();

    await expect(page.getByText("Based on 1 document")).toBeVisible();
    const summary = page.getByRole("region", { name: "Environment summary" });
    await expect(summary).toContainText("An overview of 3 passages.");
    // Each key point cites its passage, and opens it.
    await summary.getByRole("button", { name: `${WEEK_1} · p. 2` }).click();
    await expect(page.getByRole("region", { name: `${WEEK_1}, Page 2` }).locator("mark")).toContainText(
      "Threads of one process share its address space",
    );
  });

  await test.step("7. View the knowledge map", async () => {
    await tab(page, "Knowledge map").click();

    // The passage on threads names processes, and the one on scheduling
    // names threads: two relationships, both through Threads.
    await expect(page.getByRole("region", { name: "Knowledge graph" })).toContainText(
      "2 relationships between 3 of 3 concepts",
    );
    const threads = page
      .getByRole("list", { name: "Concepts" })
      .getByRole("article")
      .filter({ has: page.getByRole("heading", { name: "Threads" }) });
    await expect(threads).toContainText("2 relationships");
  });

  await test.step("8. View the roadmap", async () => {
    await tab(page, "Roadmap").click();

    const stage = page.getByRole("list", { name: "Stages" }).getByRole("article", { name: "Title 1" });
    await expect(stage).toContainText("Stage 1");
    // In the order of the material, as nothing builds on anything else.
    await expect(
      stage.getByRole("list", { name: "Concepts in stage 1" }).getByRole("link"),
    ).toHaveText(["Processes", "Threads", "CPU Scheduling"]);
  });

  let practised = "";

  await test.step("9. Complete a practice item", async () => {
    await tab(page, "Practice").click();
    await page.getByRole("button", { name: "Prepare practice" }).click();
    await expect(page.getByText("Due today: 3 new concepts.")).toBeVisible();
    await page.getByRole("button", { name: "Start practice" }).click();

    const session = page.getByRole("region", { name: "Due today" });
    await expect(session.getByText(/^1 of \d+$/)).toBeVisible();
    const card = session.getByRole("article");
    // "True or false · Threads": the kind of item, and its concept.
    const label = (await card.locator("p").first().textContent()) ?? "";
    const [kind, concept] = label.split(" · ");
    practised = concept;
    if (kind === "True or false") {
      await card.getByRole("button", { name: "True" }).click();
    } else if (kind === "Multiple choice") {
      await card.getByRole("radio").first().check();
      await card.getByRole("button", { name: "Check" }).click();
    } else {
      await card.getByRole("button", { name: /^Show the (answer|back)$/ }).click();
      await card.getByRole("button", { name: "I knew it" }).click();
    }

    const outcome = card.getByRole("status");
    await expect(outcome).toContainText(`${concept} comes back for review`);
    // Where the answer comes from.
    await expect(outcome.getByRole("button", { name: new RegExp(`^${WEEK_1} · p\\. \\d$`) })).toBeVisible();
  });

  await test.step("10. Confirm the review schedule changed", async () => {
    await page.getByRole("button", { name: "Stop here" }).click();

    // The practised concept is no longer due today, and now has a schedule.
    await expect(page.getByText("Due today: 2 new concepts.")).toBeVisible();
    await expect(page.getByRole("list", { name: "Due today" })).not.toContainText(practised);
    const performance = page
      .getByRole("list", { name: "Concepts, weakest first" })
      .getByRole("listitem")
      .filter({ hasText: practised });
    await expect(performance).toContainText(/1 recalled · every \d+ days? · next /);
    await expect(page.getByRole("list", { name: "Past sessions" })).toContainText("1 answer");
  });

  await test.step("11. Add a second PDF", async () => {
    await tab(page, "Materials").click();
    await page.getByLabel("Choose a PDF to upload").setInputFiles(path.join(PDFS, WEEK_2));

    await expect(documentCard(page, WEEK_2)).toContainText("Ready · 2 pages");
    await expect(update(page, WEEK_2)).toContainText("Done");
  });

  await test.step("12. Confirm the environment updates", async () => {
    // What the second document changed, and what it left alone.
    const changes = update(page, WEEK_2);
    await changes.getByRole("button", { name: "What changed" }).click();
    await expect(changes.getByRole("list", { name: "Concepts" })).toContainText("+ Paging");
    await expect(changes.getByRole("list", { name: "Concepts" })).toContainText("+ Page faults");
    // The passage on page faults names processes, from the first document.
    await expect(changes.getByRole("list", { name: "Relationships" })).toContainText(
      "+ Page faults relates to Processes",
    );
    await expect(changes.getByRole("list", { name: "Unchanged" })).toContainText(
      "Practice items · Those of 3 concepts kept.",
    );

    await tab(page, "Summary").click();
    await expect(page.getByText("Based on 2 documents")).toBeVisible();
    await expect(page.getByRole("region", { name: "Environment summary" })).toContainText(
      "An overview of 5 passages.",
    );

    await tab(page, "Roadmap").click();
    await expect(page.getByRole("list", { name: "Stages" }).getByRole("article")).toHaveCount(2);

    await tab(page, "Overview").click();
    const documents = page
      .getByRole("region", { name: "At a glance" })
      .locator("dt", { hasText: /^Documents$/ })
      .locator("xpath=following-sibling::dd[1]");
    await expect(documents).toContainText("2 read");
  });

  expect(problems).toEqual([]);
});
