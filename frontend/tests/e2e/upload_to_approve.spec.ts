import { expect, test } from "@playwright/test";

import {
  approveAndExpectRecorded,
  fillSingleSubmissionForm,
  openItemByBrand,
  resetDemoState,
  startAndWaitForReady,
  uniqueBrand,
} from "./helpers";

test.describe("Upload → process → approve (happy path)", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await resetDemoState(request, testInfo);
  });

  test("upload a new item, process it, approve it", async ({ page }) => {
    const brand = uniqueBrand("e2e-approve");

    await page.goto("/");

    await fillSingleSubmissionForm(page, {
      brand,
      class_type: "Tequila Blanco",
      alcohol_content: "40",
      net_contents: "750 mL",
      producer_name: "DIAGEO",
      producer_address: "NEW YORK, NY",
      is_imported: true,
      country_of_origin: "MEXICO",
    });
    await page.getByRole("button", { name: /add to queue/i }).click();

    // The new row should appear with our brand and a "Loaded" pill.
    const newRow = page.locator("tbody tr", { hasText: brand });
    await expect(newRow).toBeVisible();
    await expect(newRow).toContainText("Loaded");
    await expect(newRow).toContainText("User");

    await startAndWaitForReady(page, brand);
    await openItemByBrand(page, brand);

    // We sent expected values that match the stub extractor's Don Julio output
    // on every field except `brand` (which is the unique e2e marker).
    // The brand row therefore fails, everything else passes — and we can still
    // approve as long as the reviewer explicitly opts in.
    await approveAndExpectRecorded(page);
  });
});
