import { expect, test } from "@playwright/test";

test("signed-out users see Google authentication", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
});

test("Google identity keeps chat persistent and isolated", async ({ browser }) => {
  const firstContext = await browser.newContext();
  await firstContext.addCookies([
    { name: "e2e_auth_subject", value: "google-user-a", domain: "127.0.0.1", path: "/" },
  ]);
  const page = await firstContext.newPage();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Hey, I'm Mira." })).toBeVisible();

  await page.getByLabel("Message Mira").fill("I live in Pune");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("I remember that The user's current location is Pune.")).toBeVisible();

  const otherContext = await browser.newContext();
  await otherContext.addCookies([
    { name: "e2e_auth_subject", value: "google-user-b", domain: "127.0.0.1", path: "/" },
  ]);
  const otherPage = await otherContext.newPage();
  await otherPage.goto("/");
  await expect(otherPage.getByText("I live in Pune", { exact: true })).toHaveCount(0);
  await otherContext.close();

  const returnContext = await browser.newContext();
  await returnContext.addCookies([
    { name: "e2e_auth_subject", value: "google-user-a", domain: "127.0.0.1", path: "/" },
  ]);
  const returnPage = await returnContext.newPage();
  await returnPage.goto("/");
  await expect(returnPage.getByText("I live in Pune", { exact: true })).toBeVisible();
  await expect(
    returnPage.getByText("I remember that The user's current location is Pune."),
  ).toBeVisible();
  await firstContext.close();

  await returnPage.getByLabel("Message Mira").fill("I moved to Bengaluru");
  await returnPage.getByRole("button", { name: "Send message" }).click();
  await expect(
    returnPage.getByText("I remember that The user's current location is Bengaluru."),
  ).toBeVisible();

  await returnPage.getByRole("button", { name: /memor/ }).click();
  const drawer = returnPage.getByRole("dialog", { name: "Mira's memory inspector" });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("The user's current location is Bengaluru.")).toBeVisible();
  await expect(drawer.getByText("used last turn")).toBeVisible();

  await drawer.getByRole("button", { name: "Delete this session" }).click();
  await expect(returnPage.getByRole("alertdialog")).toBeVisible();
  await returnPage.getByRole("button", { name: "Delete and start over" }).click();
  await expect(returnPage.getByRole("heading", { name: "Hey, I'm Mira." })).toBeVisible();
  await expect(returnPage.getByText("I live in Pune", { exact: true })).toHaveCount(0);
  await returnContext.close();
});
