import { expect, type Page } from "@playwright/test";

export function randomUser() {
  const id = Math.random().toString(36).slice(2, 10);
  return {
    email: `e2e_${id}@example.com`,
    username: `e2e_${id}`,
    password: "E2ePassword123!",
  };
}

export async function registerAndLand(page: Page, user: ReturnType<typeof randomUser>) {
  await page.goto("/register");
  await page.fill("#email", user.email);
  await page.fill("#username", user.username);
  await page.fill("#password", user.password);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByText(user.username)).toBeVisible();
}
