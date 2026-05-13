import { expect, test } from "@playwright/test";

import {
  approveAndExpectRecorded,
  fillSingleSubmissionForm,
  openItemByBrand,
  openOverrideDialog,
  resetDemoState,
  startAndWaitForReady,
  uniqueBrand,
} from "./helpers";

test.describe("Upload → process → override fail→pass → approve", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await resetDemoState(request, testInfo);
  });

  test("flip a failing brand to pass, then approve cleanly", async ({
    page,
  }) => {
    // Brand intentionally mismatches the stub extractor's "Don Julio" output
    // so the row arrives in fail status.
    const brand = uniqueBrand("e2e-override-pass");

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

    await startAndWaitForReady(page, brand);
    await openItemByBrand(page, brand);

    // Brand row should be Fail.
    const brandRow = page.locator("tr", { hasText: "Brand" }).first();
    await expect(brandRow.getByText("Fail")).toBeVisible();

    // Override Brand to Pass with a comment.
    await openOverrideDialog(page, "Brand");
    await page
      .getByLabel(/reason/i)
      .fill("Reviewer audit: the label brand actually matches the extracted value.");
    await page.getByRole("button", { name: /mark pass/i }).click();

    // Brand row now shows the model→override transition pill ("Fail → Pass").
    await expect(brandRow).toContainText("Pass");

    // With no remaining failing rows, approve goes through without the
    // "approve anyway" confirmation modal.
    await approveAndExpectRecorded(page);
  });
});
