import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

const FIXTURE_IMAGE = "/tmp/ttb-e2e-test-image.jpg";

const apiUrl = (testInfo: TestInfo): string => {
  const meta = (testInfo.config.metadata ?? {}) as { apiUrl?: string };
  return meta.apiUrl ?? "http://127.0.0.1:8001";
};

/**
 * Wipe user-added submissions + reset fixtures to `loaded`. Runs before each
 * test so the queue is in a known state regardless of prior runs.
 */
export async function resetDemoState(
  request: APIRequestContext,
  testInfo: TestInfo,
): Promise<void> {
  const response = await request.post(`${apiUrl(testInfo)}/api/admin/reset`, {
    data: { confirm: true },
    headers: { "Content-Type": "application/json" },
  });
  expect(response.status(), `admin reset HTTP status`).toBeLessThan(400);
}

/**
 * Generate a unique brand string for this test run so we can find our row in
 * a queue that may also contain fixtures.
 */
export function uniqueBrand(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`;
}

export interface SingleFormValues {
  brand: string;
  class_type: string;
  alcohol_content: string;
  net_contents: string;
  producer_name: string;
  producer_address: string;
  is_imported: boolean;
  country_of_origin?: string;
}

/**
 * Fill the "Single" upload form (image + every expected-values field) on the
 * queue page. Assumes the form is already rendered (it is on `/`).
 */
export async function fillSingleSubmissionForm(
  page: Page,
  values: SingleFormValues,
): Promise<void> {
  // The Dropzone wraps a real <input type="file"> labelled by its headline.
  await page.setInputFiles(
    'input[type="file"][accept*="image/jpeg"]',
    FIXTURE_IMAGE,
  );

  await page.getByLabel("Brand").fill(values.brand);
  await page.getByLabel("Class / Type").fill(values.class_type);
  await page
    .getByLabel(/Alcohol content/i)
    .fill(values.alcohol_content);
  await page.getByLabel("Net contents").fill(values.net_contents);
  await page.getByLabel("Producer name").fill(values.producer_name);
  await page.getByLabel("Producer address").fill(values.producer_address);

  if (values.is_imported) {
    await page.getByLabel("Imported").check();
    if (values.country_of_origin) {
      await page.getByLabel("Country of origin").fill(values.country_of_origin);
    }
  }
}

/**
 * Click "Run N" and wait for the submission whose row contains `brandOrMarker`
 * to reach `Ready for Review`. The Run button label is `Run <count>` when at
 * least one item is loaded.
 */
export async function startAndWaitForReady(
  page: Page,
  brandOrMarker: string,
): Promise<void> {
  await page.getByRole("button", { name: /^Run\b/ }).click();
  const row = page.locator("tbody tr", { hasText: brandOrMarker });
  await expect(row).toBeVisible();
  await expect(row).toContainText("Ready for Review", { timeout: 30_000 });
}

/**
 * Click the "Open" link on the row matching `brandOrMarker` and wait for the
 * review page to render.
 */
export async function openItemByBrand(
  page: Page,
  brandOrMarker: string,
): Promise<void> {
  const row = page.locator("tbody tr", { hasText: brandOrMarker });
  await row.getByRole("link", { name: /open/i }).click();
  await expect(page.getByRole("heading", { name: /decision/i })).toBeVisible({
    timeout: 15_000,
  });
}

/**
 * Open the "Override" dialog for the row whose label text matches `fieldLabel`.
 * The label argument is the human-friendly column name (e.g. "Brand",
 * "Producer address") — the same string FieldRow shows in the first cell.
 */
export async function openOverrideDialog(
  page: Page,
  fieldLabel: string,
): Promise<void> {
  const row = page.locator("tr", { hasText: fieldLabel }).first();
  await row.getByRole("button", { name: /override/i }).click();
  await expect(page.getByRole("dialog", { name: /override/i })).toBeVisible();
}

/**
 * Click Approve. If the "approve anyway" confirmation modal shows up (because
 * some rows are still failing), confirm it. Wait for "Decision recorded".
 */
export async function approveAndExpectRecorded(page: Page): Promise<void> {
  await page.getByRole("button", { name: /^approve$/i }).click();

  const confirm = page.getByRole("button", {
    name: /approve anyway|confirm/i,
  });
  if (await confirm.isVisible({ timeout: 1000 }).catch(() => false)) {
    await confirm.click();
  }

  await expect(
    page.getByRole("heading", { name: /decision recorded/i }),
  ).toBeVisible({ timeout: 15_000 });
}
