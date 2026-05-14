import { expect, test } from "@playwright/test";

import { resetDemoState } from "./helpers";

// Pick a fixture brand that's reliably in the seeded demo data and likely
// not at the very top of the queue, so scroll-restoration is observable.
const TARGET_BRAND = "Maker's Mark";

test.describe("Back to queue scroll restoration", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    await resetDemoState(request, testInfo);
  });

  test("clicking Back to queue scrolls the previously-opened row into view", async ({
    page,
  }) => {
    await page.goto("/");

    // Sanity: the queue table is rendered.
    await expect(page.locator("tbody tr").first()).toBeVisible();

    // Open the fixture row directly. Fixtures start in `loaded` status, so we
    // can't wait for the Decision heading here — wait for the review toolbar
    // (which renders regardless of processing state) instead.
    const targetRow = page.locator("tbody tr", { hasText: TARGET_BRAND });
    await targetRow.getByRole("link", { name: /open/i }).click();
    await expect(
      page.getByRole("link", { name: /back to queue/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Click the new toolbar's Back link.
    await page.getByRole("link", { name: /back to queue/i }).click();
    await expect(page).toHaveURL(/\/$/);

    // The row we just reviewed should be in viewport (scrollIntoView fired
    // on mount when location.state.focusId matched its DOM id).
    const backRow = page.locator("tbody tr", { hasText: TARGET_BRAND });
    await expect(backRow).toBeVisible();
    await expect(backRow).toBeInViewport();
  });
});
