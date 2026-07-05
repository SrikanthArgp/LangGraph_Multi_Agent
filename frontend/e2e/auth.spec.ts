import { test, expect } from "@playwright/test";
import { randomUser, registerAndLand } from "./helpers";

test.describe("auth flow", () => {
  test("unauthenticated visitors are redirected to /login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("register, survive a hard reload, then log out", async ({ page }) => {
    const user = randomUser();
    await registerAndLand(page, user);

    // Access token is memory-only by design (plan.md's token-storage decision) - a hard
    // reload only survives via AuthProvider's silent refresh using the refresh token
    // in localStorage.
    await page.reload();
    await expect(page.getByText(user.username)).toBeVisible();

    await page.click('button:has-text("Log out")');
    await expect(page).toHaveURL(/\/login$/);
    const storedToken = await page.evaluate(() =>
      window.localStorage.getItem("crag_refresh_token"),
    );
    expect(storedToken).toBeNull();
  });

  test("logged-out user can log back in with the same credentials", async ({ page }) => {
    const user = randomUser();
    await registerAndLand(page, user);
    await page.click('button:has-text("Log out")');
    await expect(page).toHaveURL(/\/login$/);

    await page.fill("#email", user.email);
    await page.fill("#password", user.password);
    await page.click('button[type="submit"]');

    await expect(page).toHaveURL(/\/chat$/);
    await expect(page.getByText(user.username)).toBeVisible();
  });

  test("wrong password shows an inline error, not a crash", async ({ page }) => {
    const user = randomUser();
    await registerAndLand(page, user);
    await page.click('button:has-text("Log out")');
    await expect(page).toHaveURL(/\/login$/);

    await page.fill("#email", user.email);
    await page.fill("#password", "the-wrong-password");
    await page.click('button[type="submit"]');

    // Scoped to a <p>: Next.js's own route-change announcer is also role="alert" (a <div>),
    // so the unscoped getByRole("alert") matches both and fails Playwright's strict mode.
    await expect(page.locator('p[role="alert"]')).toHaveText(/invalid email or password/i);
    // The form must still be usable - a crash would have unmounted it.
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });
});
