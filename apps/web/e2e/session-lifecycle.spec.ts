import { expect, test } from "@playwright/test";

test("passcode to persistent recall, correction, inspection, and reset", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Demo passcode").fill("companion-demo");
  await page.getByRole("button", { name: "Unlock Mira" }).click();
  await expect(page.getByRole("heading", { name: "Hey, I'm Mira." })).toBeVisible();

  await page.getByLabel("Message Mira").fill("I live in Pune");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("I remember that The user's current location is Pune.")).toBeVisible();

  await page.reload();
  await expect(page.getByText("I live in Pune", { exact: true })).toBeVisible();
  await expect(page.getByText("I remember that The user's current location is Pune.")).toBeVisible();

  await page.getByLabel("Message Mira").fill("I moved to Bengaluru");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByText("I remember that The user's current location is Bengaluru."),
  ).toBeVisible();

  await page.getByRole("button", { name: /memor/ }).click();
  const drawer = page.getByRole("dialog", { name: "Mira's memory inspector" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("The user's current location is Bengaluru.")).toBeVisible();
  await expect(drawer.getByText("used last turn")).toBeVisible();

  await drawer.getByRole("button", { name: "Delete this session" }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page.getByRole("button", { name: "Delete and start over" }).click();
  await expect(page.getByRole("heading", { name: "Hey, I'm Mira." })).toBeVisible();
  await expect(page.getByText("I live in Pune", { exact: true })).toHaveCount(0);
});
