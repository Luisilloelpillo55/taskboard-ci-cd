const { test, expect } = require("@playwright/test");
const { randomUUID } = require("node:crypto");

test("user can register, log in again, and manage private tasks", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Taskboard" })).toBeVisible();
  await expect(page.locator("#board")).toBeHidden();

  const email = `e2e-${randomUUID()}@example.com`;
  const password = "ClaveE2E2026!";
  await page.getByLabel("Correo electrónico (registro)").fill(email);
  await page.getByLabel("Contraseña (mínimo 12 caracteres)").fill(password);
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByText(email)).toBeVisible();
  await expect(page.getByText("Aún no hay tareas")).toBeVisible();

  await page.getByLabel("Título").fill("Validar despliegue");
  await page.getByLabel("Descripción").fill("Prueba de extremo a extremo");
  await page.getByRole("button", { name: "Crear tarea" }).click();

  const task = page.locator(".task-card");
  await expect(task.getByRole("heading", { name: "Validar despliegue" })).toBeVisible();
  await expect(task.getByText("Pendiente")).toBeVisible();
  await task.getByRole("button", { name: "Avanzar tarea" }).click();
  await expect(task.getByText("En progreso")).toBeVisible();

  await page.getByRole("button", { name: "Cerrar sesión" }).click();
  await expect(page.locator("#board")).toBeHidden();
  await page.getByLabel("Correo electrónico (inicio de sesión)").fill(email);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Iniciar sesión" }).click();
  await expect(task.getByText("En progreso")).toBeVisible();
  await task.getByRole("button", { name: "Avanzar tarea" }).click();
  await expect(task.getByText("Terminada")).toBeVisible();
  await task.getByRole("button", { name: "Eliminar tarea" }).click();
  await expect(page.getByText("Aún no hay tareas")).toBeVisible();
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