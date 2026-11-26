const authView = document.querySelector("#auth-view");
const authMessage = document.querySelector("#auth-message");
const board = document.querySelector("#board");
const loginForm = document.querySelector("#login-form");
const registerForm = document.querySelector("#register-form");
const logoutButton = document.querySelector("#logout-button");
const accountEmail = document.querySelector("#account-email");
const manageAccountButton = document.querySelector("#manage-account-button");
const accountPanel = document.querySelector("#account-panel");
const profileForm = document.querySelector("#profile-form");
const profileEmail = document.querySelector("#profile-email");
const accountMessage = document.querySelector("#account-message");
const deleteAccountForm = document.querySelector("#delete-account-form");
const deleteConfirmationDialog = document.querySelector("#delete-confirmation-dialog");
const cancelDeleteAccountButton = document.querySelector("#cancel-delete-account");
const confirmDeleteAccountButton = document.querySelector("#confirm-delete-account");
const taskForm = document.querySelector("#task-form");
const taskList = document.querySelector("#task-list");
const taskCount = document.querySelector("#task-count");
const formMessage = document.querySelector("#form-message");
const loadingMessage = document.querySelector("#loading-message");
const emptyMessage = document.querySelector("#empty-message");
const errorMessage = document.querySelector("#error-message");
let pendingDeletePassword = "";

const statusLabels = {
  todo: "Pendiente",
  in_progress: "En progreso",
  done: "Terminada",
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = new Error(
      (body && body.detail) || `Error del servidor (${response.status}).`,
    );
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function showAuth(message = "", isError = true) {
  if (deleteConfirmationDialog.open) deleteConfirmationDialog.close();
  board.hidden = true;
  authView.hidden = false;
  authMessage.classList.toggle("message-error", isError);
  authMessage.textContent = message;
  authMessage.hidden = !message;
  profileForm.reset();
  deleteAccountForm.reset();
  accountPanel.hidden = true;
  manageAccountButton.setAttribute("aria-expanded", "false");
}

function showAccountMessage(message, isError = false) {
  accountMessage.classList.toggle("message-error", isError);
  accountMessage.textContent = message;
}

async function showBoard(user) {
  authView.hidden = true;
  board.hidden = false;
  accountEmail.textContent = user.email;
  profileEmail.value = user.email;
  await loadTasks();
}

function updateCount(count) {
  taskCount.textContent = `${count} ${count === 1 ? "tarea" : "tareas"}`;
}

function createTaskElement(task) {
  const item = document.createElement("li");
  item.className = "task-card";
  item.dataset.taskId = task.id;
  item.dataset.status = task.status;

  const content = document.createElement("div");
  content.className = "task-content";
  const title = document.createElement("h3");
  title.textContent = task.title;
  const description = document.createElement("p");
  description.className = "task-description";
  description.textContent = task.description || "Sin descripción";
  const badge = document.createElement("span");
  badge.className = `status status-${task.status}`;
  badge.textContent = statusLabels[task.status];
  content.append(title, description, badge);

  const actions = document.createElement("div");
  actions.className = "task-actions";
  const statusButton = document.createElement("button");
  statusButton.className = "button button-secondary";
  statusButton.type = "button";
  statusButton.dataset.action = "advance";
  statusButton.textContent = task.status === "done" ? "Reabrir" : "Avanzar";
  statusButton.setAttribute(
    "aria-label",
    `${task.status === "done" ? "Reabrir" : "Avanzar"} tarea: ${task.title}`,
  );
  const deleteButton = document.createElement("button");
  deleteButton.className = "button button-danger";
  deleteButton.type = "button";
  deleteButton.dataset.action = "delete";
  deleteButton.textContent = "Eliminar";
  deleteButton.setAttribute("aria-label", `Eliminar tarea: ${task.title}`);
  actions.append(statusButton, deleteButton);
  item.append(content, actions);
  return item;
}

function renderTasks(tasks) {
  taskList.replaceChildren(...tasks.map(createTaskElement));
  updateCount(tasks.length);
  emptyMessage.hidden = tasks.length > 0;
}

async function loadTasks() {
  loadingMessage.hidden = false;
  errorMessage.hidden = true;
  try {
    renderTasks(await request("/api/tasks"));
  } catch (error) {
    if (error.status === 401) {
      showAuth("Tu sesión venció. Inicia sesión de nuevo.");
      return;
    }
    errorMessage.textContent = `No se pudieron cargar las tareas: ${error.message}`;
    errorMessage.hidden = false;
  } finally {
    loadingMessage.hidden = true;
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authMessage.classList.add("message-error");
  authMessage.hidden = true;
  const formData = new FormData(loginForm);
  try {
    const user = await request("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: formData.get("email"),
        password: formData.get("password"),
      }),
    });
    loginForm.reset();
    await showBoard(user);
  } catch (error) {
    authMessage.textContent = `No se pudo iniciar sesión: ${error.message}`;
    authMessage.hidden = false;
  }
});

manageAccountButton.addEventListener("click", () => {
  accountPanel.hidden = !accountPanel.hidden;
  manageAccountButton.setAttribute("aria-expanded", String(!accountPanel.hidden));
  showAccountMessage("");
  if (accountPanel.hidden) {
    profileForm.reset();
    profileEmail.value = accountEmail.textContent;
    deleteAccountForm.reset();
  }
});

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showAccountMessage("");
  const formData = new FormData(profileForm);
  const email = String(formData.get("email")).trim();
  const currentPassword = String(formData.get("current_password"));
  const newPassword = String(formData.get("new_password"));
  const confirmNewPassword = String(formData.get("confirm_new_password"));

  if (newPassword !== confirmNewPassword) {
    showAccountMessage("Las nuevas contraseñas no coinciden.", true);
    return;
  }

  const payload = { current_password: currentPassword };
  if (email !== accountEmail.textContent) payload.email = email;
  if (newPassword) payload.new_password = newPassword;
  if (Object.keys(payload).length === 1) {
    showAccountMessage("No hay cambios para guardar.", true);
    return;
  }

  try {
    const user = await request("/api/auth/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    accountEmail.textContent = user.email;
    profileEmail.value = user.email;
    profileForm.reset();
    profileEmail.value = user.email;
    showAccountMessage("Los cambios de tu cuenta se guardaron.");
  } catch (error) {
    showAccountMessage(
      `No se pudieron guardar los cambios: ${error.message}`,
      true,
    );
  }
});

deleteAccountForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  pendingDeletePassword = String(
    new FormData(deleteAccountForm).get("current_password"),
  );
  showAccountMessage("");
  deleteConfirmationDialog.showModal();
});

cancelDeleteAccountButton.addEventListener("click", () => {
  deleteConfirmationDialog.close();
});

deleteConfirmationDialog.addEventListener("close", () => {
  pendingDeletePassword = "";
  deleteAccountForm.reset();
});

confirmDeleteAccountButton.addEventListener("click", async () => {
  confirmDeleteAccountButton.disabled = true;
  try {
    await request("/api/auth/me", {
      method: "DELETE",
      body: JSON.stringify({ current_password: pendingDeletePassword }),
    });
    deleteConfirmationDialog.close();
    showAuth("Tu cuenta se eliminó correctamente.", false);
  } catch (error) {
    showAccountMessage(`No se pudo eliminar la cuenta: ${error.message}`, true);
  } finally {
    if (deleteConfirmationDialog.open) deleteConfirmationDialog.close();
    confirmDeleteAccountButton.disabled = false;
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authMessage.classList.add("message-error");
  authMessage.hidden = true;
  const formData = new FormData(registerForm);
  try {
    const user = await request("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email: formData.get("email"),
        password: formData.get("password"),
      }),
    });
    registerForm.reset();
    await showBoard(user);
  } catch (error) {
    authMessage.textContent = `No se pudo crear la cuenta: ${error.message}`;
    authMessage.hidden = false;
  }
});

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    await request("/api/auth/logout", { method: "POST" });
    showAuth("Sesión cerrada correctamente.", false);
  } catch (error) {
    errorMessage.textContent = `No se pudo cerrar la sesión: ${error.message}`;
    errorMessage.hidden = false;
  } finally {
    logoutButton.disabled = false;
  }
});

taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formMessage.textContent = "";
  const formData = new FormData(taskForm);
  const title = String(formData.get("title")).trim();
  if (!title) {
    formMessage.textContent = "Escribe un título para la tarea.";
    return;
  }
  try {
    await request("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title,
        description: String(formData.get("description")).trim(),
      }),
    });
    taskForm.reset();
    formMessage.textContent = "Tarea creada.";
    await loadTasks();
  } catch (error) {
    formMessage.textContent = `No se pudo crear la tarea: ${error.message}`;
  }
});

taskList.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const item = button.closest("[data-task-id]");
  if (!item) return;
  button.disabled = true;
  try {
    if (button.dataset.action === "delete") {
      await request(`/api/tasks/${item.dataset.taskId}`, { method: "DELETE" });
    } else {
      const nextStatus =
        item.dataset.status === "todo"
          ? "in_progress"
          : item.dataset.status === "in_progress"
            ? "done"
            : "todo";
      await request(`/api/tasks/${item.dataset.taskId}`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
    }
    await loadTasks();
  } catch (error) {
    errorMessage.textContent = `No se pudo actualizar la tarea: ${error.message}`;
    errorMessage.hidden = false;
  } finally {
    button.disabled = false;
  }
});

async function initialize() {
  try {
    const user = await request("/api/auth/me");
    await showBoard(user);
  } catch (error) {
    if (error.status !== 401) {
      showAuth(`No se pudo conectar con Taskboard: ${error.message}`);
      return;
    }
    showAuth();
  }
}

initialize();
