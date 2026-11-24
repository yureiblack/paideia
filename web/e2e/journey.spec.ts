// A learner's journey through one subject, end to end (decision records 22,
// 28 and 29):
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
const WEEK_3 = "Week 3 eigenvalues.pdf";
// A lecture with a captioned chart, and a photograph of a board note
// (api/tests/e2e/prepare.py); the stand-in model reads the chart.
const WEEK_4 = "Week 4 scheduling.pdf";
const CHART_CAPTION = "Figure 1. Round robin time slices.";
const BOARD = "Board note.png";
const BOARD_NOTE = "Quantum too short: too many switches";

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

// The page as it is now fits a 320px phone: nothing scrolls sideways.
// The window is narrowed and then given back its size.
async function fitsPhone(page: Page) {
  const size = page.viewportSize();
  await page.setViewportSize({ width: 320, height: 720 });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
    )
    .toBe(0);
  if (size) await page.setViewportSize(size);
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
    // A first visit is welcomed, with one action.
    await expect(page.getByRole("heading", { level: 1, name: "A library that reads with you." })).toBeVisible();
    await page.getByRole("button", { name: "Create your first environment" }).click();
    await page.getByRole("textbox", { name: "Name" }).fill("Operating Systems");
    await page.getByRole("button", { name: "Create environment" }).click();

    // A new environment opens on adding its first PDF, with a note on what
    // an environment holds.
    await expect(page.getByRole("heading", { level: 1, name: "Operating Systems" })).toBeVisible();
    await expect(page.getByText("Start with a PDF.")).toBeVisible();
    await expect(
      page.getByRole("complementary", { name: "A new environment — what it holds" }),
    ).toBeVisible();
  });

  await test.step("2. Upload a PDF", async () => {
    await tab(page, "Materials").click();
    // The new environment's overview offers an upload too; wait until it
    // has made way for Materials, or the file could go to its picker as it
    // leaves.
    await expect(page).toHaveURL(/\/materials$/);
    await expect(page.getByText("Start with a PDF.")).toBeHidden();
    await page.getByLabel("Choose a PDF or picture to upload").setInputFiles(path.join(PDFS, WEEK_1));

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
    await page.getByLabel("Choose a PDF or picture to upload").setInputFiles(path.join(PDFS, WEEK_2));

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
    const materials = page
      .getByRole("region", { name: "In this environment" })
      .getByRole("link", { name: /^Materials/ });
    await expect(materials).toContainText("2 documents, all read.");
  });

  await test.step("13. Read a document's maths", async () => {
    await tab(page, "Materials").click();
    await page.getByLabel("Choose a PDF or picture to upload").setInputFiles(path.join(PDFS, WEEK_3));
    const card = documentCard(page, WEEK_3);
    await expect(card).toContainText("Ready · 1 page");
    await expect(update(page, WEEK_3)).toContainText("Done");

    // Never read unasked: offered from the document's menu, on the
    // document's own page, with an estimate.
    await card.getByRole("button", { name: `More for ${WEEK_3}` }).click();
    await card.getByRole("link", { name: "Read the maths" }).click();
    const offer = page.getByRole("region", { name: `Maths of ${WEEK_3}` });
    await expect(offer.getByRole("status")).toContainText("1 page to read · about a minute");
    await offer.getByRole("button", { name: "Read the maths" }).click();

    // What changed is reported with the material's other updates.
    await page
      .getByRole("navigation", { name: "Breadcrumb" })
      .getByRole("link", { name: "Materials" })
      .click();
    const reading = page
      .getByRole("region", { name: "Updates" })
      .getByRole("article")
      .filter({
        has: page.getByRole("heading", { name: `Read the maths of ${WEEK_3}`, exact: true }),
      });
    await expect(reading).toContainText("Done");
    await reading.getByRole("button", { name: "What changed" }).click();
    await expect(reading).toContainText("1 of 1 page read.");

    // The document's page now holds the formula, typeset.
    await card.getByRole("link", { name: `Read ${WEEK_3}` }).click();
    await expect(page.getByRole("tab", { name: "Text", selected: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Page 1" }).locator(".katex")).toBeVisible();
    await fitsPhone(page);
  });

  await test.step("14. Practise a computed exercise", async () => {
    // A document's page keeps the contents out of the way until asked.
    await expect(tab(page, "Practice")).toBeHidden();
    await page.getByRole("button", { name: "Show contents" }).click();
    await tab(page, "Practice").click();
    const stage = page
      .getByRole("list", { name: "Stages to practise" })
      .getByRole("listitem")
      .filter({ hasText: "Eigenvalues" });
    await stage.getByRole("button", { name: "Prepare practice" }).click();
    await stage.getByRole("button", { name: "Practise this stage" }).click();

    // The stage's items come in some order: answer the others on the way.
    const session = page.locator("section[aria-labelledby='session-heading']");
    for (let n = 1; n <= 5; n++) {
      await expect(session.getByText(new RegExp(`^${n} of \\d+$`))).toBeVisible();
      const item = session.getByRole("article");
      const kind = (await item.locator("p").first().textContent()) ?? "";
      if (kind.startsWith("Exercise")) break;
      if (kind.startsWith("Multiple choice")) {
        await item.getByRole("radio").first().check();
        await item.getByRole("button", { name: "Check" }).click();
      } else if (kind.startsWith("True or false")) {
        await item.getByRole("button", { name: "True" }).click();
      } else {
        await item.getByRole("button", { name: /^Show the (answer|back)$/ }).click();
        await item.getByRole("button", { name: "I knew it" }).click();
      }
      await item.getByRole("button", { name: /^(Next|Finish)$/ }).click();
    }

    // An eigenvalue exercise, answered wrongly on purpose: its numbers are
    // new on every review, so the right answer is not known in advance.
    const exercise = session.getByRole("article");
    await expect(exercise).toContainText("Exercise · Eigenvalues");
    await fitsPhone(page);
    for (const cell of await exercise.getByRole("textbox").all()) await cell.fill("1");
    await exercise.getByRole("button", { name: "Check" }).click();

    await expect(exercise.getByRole("status")).toContainText("Not quite.");
    const worked = exercise.getByRole("region", { name: "Worked solution" });
    await expect(worked).toContainText("So the eigenvalues are");
    await expect(worked.locator(".katex").first()).toBeVisible();
    await fitsPhone(page);
  });

  await test.step("15. Read a document's figures, and a picture's text", async () => {
    await tab(page, "Materials").click();
    await page
      .getByLabel("Choose a PDF or picture to upload")
      .setInputFiles(path.join(PDFS, WEEK_4));
    const card = documentCard(page, WEEK_4);
    await expect(card).toContainText("Ready · 1 page");
    await expect(update(page, WEEK_4)).toContainText("Done");

    // Never read unasked: offered from the menu, with an estimate.
    await card.getByRole("button", { name: `More for ${WEEK_4}` }).click();
    await card.getByRole("link", { name: "Read the figures" }).click();
    const offer = page.getByRole("region", { name: `Figures of ${WEEK_4}` });
    await expect(offer.getByRole("status")).toContainText("1 figure to read · under a minute");
    await offer.getByRole("button", { name: "Read the figures" }).click();

    await page
      .getByRole("navigation", { name: "Breadcrumb" })
      .getByRole("link", { name: "Materials" })
      .click();
    const reading = page
      .getByRole("region", { name: "Updates" })
      .getByRole("article")
      .filter({
        has: page.getByRole("heading", { name: `Read the figures of ${WEEK_4}`, exact: true }),
      });
    await expect(reading).toContainText("Done");
    await reading.getByRole("button", { name: "What changed" }).click();
    await expect(reading).toContainText("1 of 1 figure read.");

    // The page shows the figure in its place: its picture, and the model's
    // description marked as the model's.
    await card.getByRole("link", { name: `Read ${WEEK_4}` }).click();
    const figure = page
      .getByRole("region", { name: "Page 1" })
      .getByRole("figure", { name: CHART_CAPTION });
    await expect(figure).toContainText("Described by the model");
    const picture = figure.getByRole("img");
    await expect
      .poll(() => picture.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth))
      .toBeGreaterThan(0);

    // A photograph of a board note: stored as a page, its words read.
    await page
      .getByRole("navigation", { name: "Breadcrumb" })
      .getByRole("link", { name: "Materials" })
      .click();
    await page.getByLabel("Choose a PDF or picture to upload").setInputFiles(path.join(PDFS, BOARD));
    const board = documentCard(page, BOARD);
    await expect(board).toContainText("Ready · 1 page");
    await expect(board).toContainText("1 page read from pictures");
    await board.getByRole("link", { name: `Read ${BOARD}` }).click();
    await expect(page.getByRole("region", { name: "Page 1" })).toContainText(BOARD_NOTE);
  });

  await test.step("16. Open the guide, and go back to where it was opened", async () => {
    const reading = page.url();
    await page.getByRole("banner").getByRole("link", { name: "Guide" }).click();
    await expect(page.getByRole("heading", { name: "Organise, explore, learn." })).toBeVisible();
    // Moving between its steps is not where its link goes back to.
    await page.getByRole("navigation", { name: "Steps" }).getByRole("link").nth(2).click();
    await expect(page).toHaveURL(/\/guide#step-3$/);
    await page.getByRole("link", { name: "Back", exact: true }).click();
    await expect(page).toHaveURL(reading);
    await expect(page.getByRole("region", { name: "Page 1" })).toContainText(BOARD_NOTE);
  });

  await test.step("17. Every section fits a phone", async () => {
    const base = new URL(page.url()).pathname.split("/").slice(0, 3).join("/");
    for (const section of ["", "/materials", "/summary", "/knowledge-map", "/search", "/roadmap", "/practice"]) {
      await page.goto(base + section);
      await page.waitForLoadState("networkidle");
      await fitsPhone(page);
    }

    // A document's menu opens inside the window, though its button sits
    // near the left edge on a phone.
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto(`${base}/materials`);
    const card = documentCard(page, WEEK_3);
    await card.getByRole("button", { name: `More for ${WEEK_3}` }).click();
    const item = await card.getByRole("link", { name: "Read the maths" }).boundingBox();
    expect(item?.x).toBeGreaterThanOrEqual(0);
    expect((item?.x ?? 0) + (item?.width ?? 0)).toBeLessThanOrEqual(320);
    await page.setViewportSize({ width: 1280, height: 720 });
  });

  expect(problems).toEqual([]);
});
