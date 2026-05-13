import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  fillSingleSubmissionForm,
  openOverrideDialog,
  resetDemoState,
  uniqueBrand,
} from "./helpers";

interface SubmissionRow {
  id: string;
  status: string;
  is_fixture: boolean;
  created_at: string;
}

async function latestUserSubmissionId(
  request: APIRequestContext,
  apiUrl: string,
): Promise<string> {
  const response = await request.get(`${apiUrl}/api/submissions`);
  const rows = (await response.json()) as SubmissionRow[];
  const userRows = rows.filter((r) => r.is_fixture === false);
  if (userRows.length === 0) throw new Error("no user submission found");
  userRows.sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  return userRows[0].id;
}

async function waitForReadyForReview(
  request: APIRequestContext,
  apiUrl: string,
  id: string,
  timeoutMs = 30_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const response = await request.get(`${apiUrl}/api/submissions/${id}`);
    const body = (await response.json()) as { status: string };
    if (body.status === "ready_for_review") return;
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`submission ${id} did not reach ready_for_review in time`);
}

test.describe("Upload → process → override pass→fail → reject", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await resetDemoState(request, testInfo);
  });

  test("flip a passing field to fail, then reject with that reason", async ({
    page,
    request,
  }, testInfo) => {
    const apiUrl =
      ((testInfo.config.metadata ?? {}) as { apiUrl?: string }).apiUrl ??
      "http://127.0.0.1:8001";

    // Match every stub-extractor field so the row arrives all-pass.
    const comment = uniqueBrand("e2e-override-fail-comment");

    await page.goto("/");
    await fillSingleSubmissionForm(page, {
      brand: "Don Julio",
      class_type: "Tequila Blanco",
      alcohol_content: "40",
      net_contents: "750 mL",
      producer_name: "DIAGEO",
      producer_address: "NEW YORK, NY",
      is_imported: true,
      country_of_origin: "MEXICO",
    });
    await page.getByRole("button", { name: /add to queue/i }).click();

    // Wait for the row to appear in the queue before looking it up via the
    // API — the upload mutation is async and the queue query has to refetch.
    await expect(
      page.locator("tbody tr", { hasText: "User" }).first(),
    ).toBeVisible();

    // Look up the new submission via the API rather than by brand (every
    // fixture is also "Don Julio").
    const id = await latestUserSubmissionId(request, apiUrl);

    await page.getByRole("button", { name: /^Run\b/ }).click();
    await waitForReadyForReview(request, apiUrl, id);

    await page.goto(`/items/${id}`);
    await expect(
      page.getByRole("heading", { name: /^decision$/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Every row should be Pass before we override.
    const addressRow = page.locator("tr", { hasText: "Producer address" }).first();
    await expect(addressRow.locator('[class*="verdictPill"]').first()).toContainText(
      "Pass",
    );

    // Override Producer Address to Fail.
    await openOverrideDialog(page, "Producer address");
    await page.getByLabel(/reason/i).fill(comment);
    await page.getByRole("button", { name: /mark fail/i }).click();

    // Row should now show the model→override transition: Pass → Fail.
    await expect(addressRow.locator('[class*="verdictPill"]').first()).toContainText(
      "Fail",
    );

    // Reject. The reject panel opens with the now-failing field pre-checked.
    await page.getByRole("button", { name: /^reject/i }).first().click();
    await expect(page.getByText(/select rejection reasons/i)).toBeVisible();

    // The "Producer address" candidate appears in the panel marked "Failing".
    const candidate = page.locator("li", { hasText: "Producer address" }).first();
    await expect(candidate).toBeVisible();
    await expect(candidate).toContainText("Failing");

    await page.getByRole("button", { name: /submit rejection/i }).click();

    await expect(
      page.getByRole("heading", { name: /decision recorded/i }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/rejected/i).first()).toBeVisible();

    // Back on the queue, the user-added row reads "Rejected".
    await page.goto("/");
    const userRow = page.locator("tbody tr", { hasText: "User" }).first();
    await expect(userRow).toContainText("Rejected");
  });
});
