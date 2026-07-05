import { test, expect } from "@playwright/test";
import { randomUser, registerAndLand } from "./helpers";

// This drives the real CRAG graph end to end (router -> retrieve/websearch -> grade ->
// generate -> grade), which is meaningfully slower than the rest of the API - give this
// one test a longer budget than the suite default rather than loosening it globally.
test.describe("chat flow", () => {
  test.setTimeout(150_000);

  test("create a session, send a message, see the answer, rename, then archive", async ({
    page,
  }) => {
    const user = randomUser();
    await registerAndLand(page, user);

    await expect(page.getByText("No chat selected")).toBeVisible();

    await page.click('button:has-text("+ New")');
    await expect(page).toHaveURL(/\/chat\/[^/]+$/);

    const question = "What is a ReAct agent?";
    await page.fill('input[placeholder="Ask a question…"]', question);
    await page.getByRole("button", { name: /^send$/i }).click();

    const userMessage = page.locator('[data-testid="chat-message"][data-role="user"]').last();
    await expect(userMessage).toContainText(question);

    // The backend's SSE stream isn't truly token-by-token (known limitation, see
    // api/routers/chat.py) - it resolves the full answer in one event, so the pending
    // cursor renders immediately and isn't itself proof the answer arrived. The input
    // stays disabled (empty) either way, so wait on real answer text showing up instead.
    const assistantMessage = page
      .locator('[data-testid="chat-message"][data-role="assistant"]')
      .last();
    await expect(assistantMessage).toContainText(/\w{10,}/, { timeout: 60_000 });

    // Rename via the sidebar - rename/delete controls are CSS `group-hover`-revealed.
    // Keyed off data-testid, not the row's text, since that text swaps to a rename
    // <input> mid-flow (an <input>'s value isn't matched by a text-content filter).
    const sessionRow = page.getByTestId("session-item").first();
    await sessionRow.hover();
    await sessionRow.getByLabel("Rename chat").click();
    const renameInput = sessionRow.locator("input");
    await renameInput.fill("ReAct question");
    await renameInput.press("Enter");
    await expect(sessionRow).toContainText("ReAct question");

    // Archive (soft-delete) - confirm() dialog must be accepted explicitly.
    page.once("dialog", (dialog) => dialog.accept());
    await sessionRow.hover();
    await sessionRow.getByLabel("Delete chat").click();
    await expect(page.getByText("ReAct question")).not.toBeVisible();
  });
});
