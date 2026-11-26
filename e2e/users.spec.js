const { test, expect, request: playwrightRequest } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const { attachScreenshot } = require("./helpers");

const BASE_URL = "http://127.0.0.1:8001";
const PASSWORD = "ClaveE2E2026!";

async function register(api, email, password = PASSWORD) {
  return api.post("/api/auth/register", {
    data: { email, password },
  });
}

test.describe("User account API", () => {
  test("users can read, update, and delete only their own account", async ({ request }) => {
    const email = `account-${randomUUID()}@example.com`;
    const newEmail = `updated-${randomUUID()}@example.com`;
    const otherEmail = `other-${randomUUID()}@example.com`;
    const newPassword = "NuevaClaveSegura2026!";
    const other = await playwrightRequest.newContext({ baseURL: BASE_URL });

    try {
      const created = await register(request, email);
      expect(created.status()).toBe(201);
      expect(Object.keys(await created.json()).sort()).toEqual([
        "created_at",
        "email",
        "id",
      ]);
      expect((await request.get("/api/auth/me")).status()).toBe(200);

      const ownTask = await request.post("/api/tasks", {
        data: { title: "Tarea de mi cuenta" },
      });
      expect(ownTask.status()).toBe(201);

      expect((await register(other, otherEmail)).status()).toBe(201);
      const otherTask = await other.post("/api/tasks", {
        data: { title: "Tarea de otra cuenta" },
      });
      expect(otherTask.status()).toBe(201);

      const updated = await request.patch("/api/auth/me", {
        data: {
          current_password: PASSWORD,
          email: newEmail,
          new_password: newPassword,
        },
      });
      expect(updated.status()).toBe(200);
      expect((await updated.json()).email).toBe(newEmail);
      expect((await request.get("/api/tasks")).status()).toBe(200);
      expect((await other.get("/api/auth/me")).status()).toBe(200);

      const duplicateEmail = await request.patch("/api/auth/me", {
        data: { current_password: newPassword, email: otherEmail },
      });
      expect(duplicateEmail.status()).toBe(409);

      const deleted = await request.delete("/api/auth/me", {
        data: { current_password: newPassword },
      });
      expect(deleted.status()).toBe(204);
      expect(deleted.headers()["set-cookie"]).toContain("Max-Age=0");
      expect((await request.get("/api/auth/me")).status()).toBe(401);
      expect((await request.get("/api/tasks")).status()).toBe(401);

      const otherUser = await other.get("/api/auth/me");
      expect(otherUser.status()).toBe(200);
      expect(await (await other.get("/api/tasks")).json()).toEqual([
        await otherTask.json(),
      ]);
    } finally {
      await other.dispose();
    }
  });

  test("account changes require authentication, current password, and valid fields", async ({
    request,
  }) => {
    expect(
      (
        await request.patch("/api/auth/me", {
          data: { current_password: PASSWORD, email: "anon@example.com" },
        })
      ).status(),
    ).toBe(401);
    expect(
      (
        await request.delete("/api/auth/me", {
          data: { current_password: PASSWORD },
        })
      ).status(),
    ).toBe(401);

    const email = `validation-${randomUUID()}@example.com`;
    expect((await register(request, email)).status()).toBe(201);

    expect(
      (
        await request.patch("/api/auth/me", {
          data: { current_password: PASSWORD },
        })
      ).status(),
    ).toBe(400);
    expect(
      (
        await request.patch("/api/auth/me", {
          data: { current_password: PASSWORD, email: null },
        })
      ).status(),
    ).toBe(422);
    expect(
      (
        await request.patch("/api/auth/me", {
          data: { current_password: PASSWORD, new_password: null },
        })
      ).status(),
    ).toBe(422);
    expect(
      (
        await request.patch("/api/auth/me", {
          data: { current_password: PASSWORD, new_password: "short" },
        })
      ).status(),
    ).toBe(422);
    expect(
      (
        await request.patch("/api/auth/me", {
          data: {
            current_password: "ContraseñaIncorrecta2026!",
            email: "changed@example.com",
          },
        })
      ).status(),
    ).toBe(403);
    expect(
      (
        await request.delete("/api/auth/me", {
          data: { current_password: "ContraseñaIncorrecta2026!" },
        })
      ).status(),
    ).toBe(403);
    expect(await (await request.get("/api/auth/me")).json()).toMatchObject({
      email,
    });
  });
});

test("user can change account details from the page and keep their tasks", async ({ page }, testInfo) => {
  const email = `profile-${randomUUID()}@example.com`;
  const newEmail = `profile-updated-${randomUUID()}@example.com`;
  const newPassword = "NuevaClaveSegura2026!";
  await page.goto("/");
  await attachScreenshot(page, testInfo, "account-test-before-registration");
  await page.getByLabel("Correo electrónico (registro)").fill(email);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill(PASSWORD);
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await page.getByLabel("Título").fill("Tarea que debe conservarse");
  await page.getByRole("button", { name: "Crear tarea" }).click();

  await page.getByRole("button", { name: "Mi cuenta" }).click();
  await attachScreenshot(page, testInfo, "account-settings");
  await page.getByLabel("Correo electrónico", { exact: true }).fill(newEmail);
  await page.getByLabel("Contraseña actual (para confirmar cambios)").fill(PASSWORD);
  await page.locator("#new-password").fill(newPassword);
  await page.getByLabel("Confirmar nueva contraseña").fill("OtraClaveSegura2026!");
  await page.getByRole("button", { name: "Guardar cambios" }).click();
  await expect(page.locator("#account-message")).toHaveText(
    "Las nuevas contraseñas no coinciden.",
  );
  await expect(page.locator("#account-message")).toHaveClass(/message-error/);

  await page.getByLabel("Confirmar nueva contraseña").fill(newPassword);
  await page.getByRole("button", { name: "Guardar cambios" }).click();

  await expect(page.locator("#account-email")).toHaveText(newEmail);
  await expect(page.locator("#account-message")).toHaveText(
    "Los cambios de tu cuenta se guardaron.",
  );
  await expect(page.getByText("Tarea que debe conservarse")).toBeVisible();
  await attachScreenshot(page, testInfo, "account-updated");

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await attachScreenshot(page, testInfo, "account-test-logged-out");
  await page.getByLabel("Correo electrónico (inicio de sesión)").fill(newEmail);
  await page.getByLabel("Contraseña", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.locator("#auth-message")).toContainText(
    "Correo o contraseña incorrectos.",
  );

  await page.getByLabel("Contraseña", { exact: true }).fill(newPassword);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.locator("#board")).toBeVisible();
  await expect(page.getByText("Tarea que debe conservarse")).toBeVisible();
  await attachScreenshot(page, testInfo, "account-test-logged-in");
});

test("account settings fit the mobile viewport", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(
    `mobile-account-${randomUUID()}@example.com`,
  );
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill(PASSWORD);
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await page.getByRole("button", { name: "Mi cuenta" }).click();
  await attachScreenshot(page, testInfo, "mobile-account-settings");

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  await expect(page.getByRole("heading", { name: "Administrar tu cuenta" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Guardar cambios" })).toBeVisible();
});

test("user must confirm before deleting their account in the page", async ({ page }, testInfo) => {
  const email = `delete-account-${randomUUID()}@example.com`;
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(email);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill(PASSWORD);
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await page.getByRole("button", { name: "Mi cuenta" }).click();
  await page.getByLabel("Confirma tu contraseña actual").fill(PASSWORD);

  await page.getByRole("button", { name: "Eliminar mi cuenta" }).click();
  const confirmation = page.getByRole("dialog", {
    name: "Confirmar eliminación de cuenta",
  });
  await expect(confirmation).toBeVisible();
  await attachScreenshot(page, testInfo, "account-deletion-confirmation");
  await confirmation.getByRole("button", { name: "Cancelar" }).click();
  await expect(confirmation).toBeHidden();
  await expect(page.locator("#board")).toBeVisible();
  await attachScreenshot(page, testInfo, "account-deletion-cancelled");

  await page.getByLabel("Confirma tu contraseña actual").fill(PASSWORD);
  await page.getByRole("button", { name: "Eliminar mi cuenta" }).click();
  await expect(confirmation).toBeVisible();
  await confirmation.getByRole("button", { name: "Sí, eliminar mi cuenta" }).click();

  await expect(page.locator("#auth-view")).toBeVisible();
  await expect(page.locator("#auth-message")).toHaveText(
    "Tu cuenta se eliminó correctamente.",
  );
  await page.getByLabel("Correo electrónico (inicio de sesión)").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(page.locator("#auth-message")).toContainText(
    "Correo o contraseña incorrectos.",
  );
  await expect(page.locator("#auth-message")).toHaveClass(/message-error/);
  await attachScreenshot(page, testInfo, "account-deleted");
});
