(function () {
  "use strict";

  const apps = Array.isArray(window.PORTAL_APPS) ? window.PORTAL_APPS : [];
  const grid = document.getElementById("apps-grid");
  const emptyState = document.getElementById("empty-state");
  const appView = document.getElementById("app-view");
  const appFrame = document.getElementById("app-frame");
  const externalLink = document.getElementById("external-link");
  const embeddedGreeting = document.getElementById("embedded-greeting");
  const frameHelpLink = document.getElementById("frame-help-link");
  const shell = document.querySelector(".shell");
  const breadcrumb = document.getElementById("breadcrumb-current");
  let appFrameHasLoaded = false;

  function resizeAppFrame() {
    if (appFrame.dataset.autoHeight !== "true") {
      return;
    }

    const frameDocument = appFrame.contentDocument;
    if (!frameDocument) {
      return;
    }

    appFrame.style.height = `${Math.ceil(Math.max(
      frameDocument.body.scrollHeight,
      frameDocument.documentElement.scrollHeight,
    ))}px`;
  }

  function isValidApp(app) {
    if (!app || typeof app !== "object" || typeof app.id !== "string" ||
        typeof app.name !== "string" || typeof app.description !== "string" ||
        typeof app.url !== "string") {
      return false;
    }

    try {
      const url = new URL(app.url, window.location.href);
      return url.protocol === "http:" || url.protocol === "https:";
    } catch (error) {
      return false;
    }
  }

  const validApps = apps.filter(isValidApp);

  function setAppIcon(element, app) {
    const baseClass = element.classList.contains("mini-app-icon")
      ? "mini-app-icon"
      : "app-icon";
    element.className = baseClass + " " + (app.image ? "image-icon" : (app.color || "mint"));
    element.replaceChildren();

    if (app.image) {
      const image = document.createElement("img");
      image.src = app.image;
      image.alt = "";
      element.appendChild(image);
    } else {
      element.textContent = app.icon || app.name.slice(0, 2).toUpperCase();
    }

    element.setAttribute("aria-hidden", "true");
  }

  function createAppCard(app) {
    const card = document.createElement("button");
    card.className = "app-card";
    card.type = "button";
    card.setAttribute("aria-label", "Ouvrir " + app.name);

    const top = document.createElement("span");
    top.className = "card-top";
    const icon = document.createElement("span");
    setAppIcon(icon, app);
    const arrow = document.createElement("span");
    arrow.className = "card-arrow";
    arrow.textContent = "↗";
    arrow.setAttribute("aria-hidden", "true");
    top.append(icon, arrow);

    const category = document.createElement("span");
    category.className = "app-category";
    category.textContent = app.category || "Application";
    const title = document.createElement("span");
    title.className = "app-name";
    title.textContent = app.name;
    const description = document.createElement("span");
    description.className = "app-description";
    description.textContent = app.description;
    card.append(top, category, title, description);
    card.addEventListener("click", function () {
      openApp(app);
    });
    return card;
  }

  function renderApps() {
    grid.replaceChildren();
    validApps.forEach(function (app) {
      grid.appendChild(createAppCard(app));
    });
    emptyState.hidden = validApps.length > 0;
  }

  function openApp(app) {
    shell.classList.add("app-open");
    appFrameHasLoaded = false;
    appFrame.dataset.autoHeight = String(
      new URL(app.url, window.location.href).origin === window.location.origin,
    );
    document.getElementById("active-title").textContent = app.name;
    const activeIcon = document.getElementById("active-icon");
    setAppIcon(activeIcon, app);
    activeIcon.style.display = app.id === "cent-cols" ? "none" : "";
    appFrame.title = app.name;
    appFrame.src = app.url;
    externalLink.href = app.url;
    if (embeddedGreeting) {
      embeddedGreeting.hidden = app.id !== "cent-cols";
    }
    frameHelpLink.href = app.url;
    grid.hidden = true;
    emptyState.hidden = true;
    appView.hidden = false;
    breadcrumb.textContent = app.name;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function showHome() {
    shell.classList.remove("app-open");
    appFrameHasLoaded = false;
    appFrame.removeAttribute("src");
    delete appFrame.dataset.autoHeight;
    appFrame.style.removeProperty("height");
    appView.hidden = true;
    if (embeddedGreeting) {
      embeddedGreeting.hidden = true;
    }
    grid.hidden = false;
    breadcrumb.textContent = "Accueil";
    renderApps();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  renderApps();
  appFrame.addEventListener("load", function () {
    if (appFrame.dataset.autoHeight !== "true" || !appFrame.contentDocument) {
      return;
    }
    appFrame.style.removeProperty("height");
    resizeAppFrame();
    if (appFrameHasLoaded) {
      appView.scrollIntoView({ block: "start", behavior: "auto" });
    }
    appFrameHasLoaded = true;
    appFrame.contentDocument.defaultView.addEventListener("resize", resizeAppFrame);
  });

  document.getElementById("back-button").addEventListener("click", showHome);
})();
