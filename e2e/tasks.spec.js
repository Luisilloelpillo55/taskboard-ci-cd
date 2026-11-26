const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");
const { attachScreenshot } = require("./helpers");

test("user can register, log in again, and manage private tasks", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Taskboard" })).toBeVisible();
  await expect(page.locator("#board")).toBeHidden();
  await attachScreenshot(page, testInfo, "login-and-registration");

  const email = `e2e-${randomUUID()}@example.com`;
  const password = "ClaveE2E2026!";
  await page.getByLabel("Correo electrónico (registro)").fill(email);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill(password);
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText("Aún no hay tareas")).toBeVisible();
  await attachScreenshot(page, testInfo, "empty-taskboard");

  await page.getByLabel("Título").fill("Validar despliegue");
  await page.getByLabel("Descripción").fill("Prueba de extremo a extremo");
  await page.getByRole("button", { name: "Crear tarea" }).click();

  const task = page.locator(".task-card");
  await expect(task.getByRole("heading", { name: "Validar despliegue" })).toBeVisible();
  await expect(task.getByText("Pendiente")).toBeVisible();
  await attachScreenshot(page, testInfo, "task-created");
  await task.getByRole("button", { name: "Avanzar tarea" }).click();
  await expect(task.getByText("En progreso")).toBeVisible();
  await attachScreenshot(page, testInfo, "task-in-progress");

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page.locator("#board")).toBeHidden();
  await attachScreenshot(page, testInfo, "logged-out");
  await page.getByLabel("Correo electrónico (inicio de sesión)").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(task.getByText("En progreso")).toBeVisible();
  await attachScreenshot(page, testInfo, "logged-in-with-saved-task");
  await task.getByRole("button", { name: "Avanzar tarea" }).click();
  await expect(task.getByText("Terminada")).toBeVisible();
  await attachScreenshot(page, testInfo, "task-completed");
  await task.getByRole("button", { name: "Eliminar tarea" }).click();
  await expect(page.getByText("Aún no hay tareas")).toBeVisible();
  await attachScreenshot(page, testInfo, "empty-taskboard-after-delete");
});

test("task board is gated and a task title is required", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("#board")).toBeHidden();
  await page.getByLabel("Correo electrónico (registro)").fill(`empty-${randomUUID()}@example.com`);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.locator("#board")).toBeVisible();
  await page.getByRole("button", { name: "Crear tarea" }).click();
  const titleIsValid = await page.getByLabel("Título").evaluate((input) => input.validity.valid);
  expect(titleIsValid).toBe(false);
  await expect(page.getByText("Aún no hay tareas")).toBeVisible();
});

test("login rejects invalid credentials without leaving the auth view", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Correo electrónico (inicio de sesión)").fill("missing@example.com");
  await page.getByLabel("Contraseña", { exact: true }).fill("WrongPassphrase2026!");
  await page.getByRole("button", { name: "Iniciar sesión" }).click();

  await expect(page.locator("#auth-message")).toContainText(
    "No se pudo iniciar sesión: Correo o contraseña incorrectos.",
  );
  await expect(page.locator("#board")).toBeHidden();
});

test("duplicate registration displays a useful error", async ({ page }) => {
  const email = `duplicate-${randomUUID()}@example.com`;
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(email);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await page.getByRole("button", { name: "Cerrar sesión" }).click();

  await page.getByLabel("Correo electrónico (registro)").fill(email);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  await expect(page.locator("#auth-message")).toContainText(
    "Ya existe una cuenta con ese correo.",
  );
});

test("registration displays the normalized email address", async ({ page }) => {
  const email = `UPPER-${randomUUID()}@Example.COM`;
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(email);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  await expect(page.locator("#account-email")).toHaveText(email.toLowerCase());
});

test("session and tasks persist after reloading the page", async ({ page }) => {
  await page.goto("/");
  const email = `reload-${randomUUID()}@example.com`;
  await page.getByLabel("Correo electrónico (registro)").fill(email);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await page.getByLabel("Título").fill("Persisted task");
  await page.getByRole("button", { name: "Crear tarea" }).click();

  await page.reload();

  await expect(page.locator("#board")).toBeVisible();
  await expect(page.locator(".task-card")).toContainText("Persisted task");
});

test("task count, descriptions, and newest-first ordering stay in sync", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(`count-${randomUUID()}@example.com`);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  await page.getByLabel("Título").fill("First task");
  await page.getByRole("button", { name: "Crear tarea" }).click();
  await expect(page.locator("#task-count")).toHaveText("1 tarea");
  await expect(page.locator(".task-card")).toContainText("Sin descripción");

  await page.getByLabel("Título").fill("Second task");
  await page.getByLabel("Descripción").fill("  Details  ");
  await page.getByRole("button", { name: "Crear tarea" }).click();

  const cards = page.locator(".task-card");
  await expect(page.locator("#task-count")).toHaveText("2 tareas");
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText("Second task");
  await expect(cards.nth(0)).toContainText("Details");
  await expect(cards.nth(1)).toContainText("First task");
});

test("deleting one task updates the count and keeps the remaining task", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(`delete-one-${randomUUID()}@example.com`);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  for (const [index, title] of ["Keep task", "Delete task"].entries()) {
    await page.getByLabel("Título").fill(title);
    await page.getByRole("button", { name: "Crear tarea" }).click();
    await expect(page.locator(".task-card")).toHaveCount(index + 1);
  }

  await page.getByRole("button", { name: "Eliminar tarea: Delete task" }).click();

  await expect(page.locator("#task-count")).toHaveText("1 tarea");
  await expect(page.getByText("Keep task")).toBeVisible();
  await expect(page.getByText("Delete task")).toHaveCount(0);
  await expect(page.getByText("Aún no hay tareas")).toBeHidden();
});

test("a completed task can be reopened", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(`reopen-${randomUUID()}@example.com`);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await page.getByLabel("Título").fill("Reopen task");
  await page.getByRole("button", { name: "Crear tarea" }).click();

  const task = page.locator(".task-card");
  await task.getByRole("button", { name: "Avanzar tarea: Reopen task" }).click();
  await task.getByRole("button", { name: "Avanzar tarea: Reopen task" }).click();
  await expect(task.getByText("Terminada")).toBeVisible();
  await task.getByRole("button", { name: "Reabrir tarea: Reopen task" }).click();

  await expect(task.getByText("Pendiente")).toBeVisible();
  await expect(task.getByRole("button", { name: "Avanzar tarea: Reopen task" })).toBeVisible();
});

test("tasks remain private when another account signs in", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(`owner-${randomUUID()}@example.com`);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await page.getByLabel("Título").fill("Private task");
  await page.getByRole("button", { name: "Crear tarea" }).click();
  await page.getByRole("button", { name: "Cerrar sesión" }).click();

  await page.getByLabel("Correo electrónico (registro)").fill(`other-${randomUUID()}@example.com`);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  await expect(page.getByText("Aún no hay tareas")).toBeVisible();
  await expect(page.getByText("Private task")).toHaveCount(0);
});

test("registration blocks an invalid email in the browser", async ({ page }) => {
  await page.goto("/");
  const email = page.getByLabel("Correo electrónico (registro)");
  await email.fill("not-an-email");
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");

  expect(await email.evaluate((input) => input.validity.typeMismatch)).toBe(true);
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.locator("#auth-message")).toBeHidden();
  await expect(page.locator("#board")).toBeHidden();
});

test("registration enforces the minimum password length in the browser", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(`short-${randomUUID()}@example.com`);
  const password = page.getByLabel("Contraseña (mínimo 12 caracteres)");
  await password.fill("short");

  expect(await password.evaluate((input) => input.validity.tooShort)).toBe(true);
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.locator("#board")).toBeHidden();
});

test("whitespace-only task titles receive inline feedback", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Correo electrónico (registro)").fill(`spaces-${randomUUID()}@example.com`);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill("ClaveE2E2026!");
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await page.getByLabel("Título").fill("   ");
  await page.getByRole("button", { name: "Crear tarea" }).click();

  await expect(page.locator("#form-message")).toHaveText("Escribe un título para la tarea.");
  await expect(page.locator(".task-card")).toHaveCount(0);
});

test("mobile layout fits the viewport without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  const panels = page.locator("#auth-view .panel");
  const firstPanel = await panels.nth(0).boundingBox();
  const secondPanel = await panels.nth(1).boundingBox();

  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  expect(secondPanel.y).toBeGreaterThan(firstPanel.y);
});

test("keyboard navigation reaches a visibly focused login field", async ({ page }, testInfo) => {
  await page.goto("/");
  await page.keyboard.press("Tab");

  const email = page.getByLabel("Correo electrónico (inicio de sesión)");
  await expect(email).toBeFocused();
  const outline = await email.evaluate((input) => {
    const style = getComputedStyle(input);
    return { width: Number.parseFloat(style.outlineWidth), style: style.outlineStyle };
  });
  expect(outline.width).toBeGreaterThanOrEqual(2);
  expect(outline.style).toBe("solid");
  await attachScreenshot(page, testInfo, "keyboard-focus-indicator");
});

test("task loading errors are announced in the board", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "mock@example.com", created_at: "2026-01-01" }),
    }),
  );
  await page.route("**/api/tasks", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Service unavailable" }),
    }),
  );
  await page.goto("/");

  await expect(page.locator("#error-message")).toContainText(
    "No se pudieron cargar las tareas: Service unavailable",
  );
});

test("an expired session during task loading returns to sign in", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "mock@example.com", created_at: "2026-01-01" }),
    }),
  );
  await page.route("**/api/tasks", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Unauthorized" }),
    }),
  );
  await page.goto("/");

  await expect(page.locator("#auth-view")).toBeVisible();
  await expect(page.locator("#auth-message")).toHaveText(
    "Tu sesión venció. Inicia sesión de nuevo.",
  );
});

test("task creation errors are shown without clearing the form", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "mock@example.com", created_at: "2026-01-01" }),
    }),
  );
  await page.route("**/api/tasks", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ status: 200, contentType: "application/json", body: "[]" })
      : route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Write unavailable" }),
        }),
  );
  await page.goto("/");
  await page.getByLabel("Título").fill("Keep this value");
  await page.getByRole("button", { name: "Crear tarea" }).click();

  await expect(page.locator("#form-message")).toContainText(
    "No se pudo crear la tarea: Write unavailable",
  );
  await expect(page.getByLabel("Título")).toHaveValue("Keep this value");
});

test("task update errors are announced", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "mock@example.com", created_at: "2026-01-01" }),
    }),
  );
  await page.route("**/api/tasks**", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: 10,
              title: "Mock task",
              description: "",
              status: "todo",
              created_at: "2026-01-01",
            },
          ]),
        })
      : route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Update unavailable" }),
        }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Avanzar tarea: Mock task" }).click();

  await expect(page.locator("#error-message")).toContainText(
    "No se pudo actualizar la tarea: Update unavailable",
  );
});

test("task deletion errors are announced", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "mock@example.com", created_at: "2026-01-01" }),
    }),
  );
  await page.route("**/api/tasks**", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: 10,
              title: "Mock task",
              description: "",
              status: "todo",
              created_at: "2026-01-01",
            },
          ]),
        })
      : route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "Delete unavailable" }),
        }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Eliminar tarea: Mock task" }).click();

  await expect(page.locator("#error-message")).toContainText(
    "No se pudo actualizar la tarea: Delete unavailable",
  );
});

test("logout errors are announced without hiding the task board", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "mock@example.com", created_at: "2026-01-01" }),
    }),
  );
  await page.route("**/api/tasks", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/auth/logout", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Logout unavailable" }),
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Cerrar sesión" }).click();

  await expect(page.locator("#error-message")).toContainText(
    "No se pudo cerrar la sesión: Logout unavailable",
  );
  await expect(page.locator("#board")).toBeVisible();
});

test("initial API connection errors are displayed on the auth view", async ({ page }) => {
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Service unavailable" }),
    }),
  );
  await page.goto("/");

  await expect(page.locator("#auth-message")).toContainText(
    "No se pudo conectar con Taskboard: Service unavailable",
  );
  await expect(page.locator("#board")).toBeHidden();
});