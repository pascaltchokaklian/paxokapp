(function () {
  "use strict";

  const apps = Array.isArray(window.PORTAL_APPS) ? window.PORTAL_APPS : [];
  const grid = document.getElementById("apps-grid");
  const search = document.getElementById("search");
  const emptyState = document.getElementById("empty-state");
  const appView = document.getElementById("app-view");
  const appFrame = document.getElementById("app-frame");
  const externalLink = document.getElementById("external-link");
  const embeddedGreeting = document.getElementById("embedded-greeting");
  const frameHelpLink = document.getElementById("frame-help-link");
  const shell = document.querySelector(".shell");
  const headingCount = document.getElementById("heading-count");
  const heading = document.getElementById("apps-title");
  const breadcrumb = document.getElementById("breadcrumb-current");

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
    )) + 2}px`;
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

  function renderApps(query) {
    const normalizedQuery = query.trim().toLocaleLowerCase("fr");
    const filteredApps = validApps.filter(function (app) {
      return [app.name, app.description, app.category || ""]
        .join(" ")
        .toLocaleLowerCase("fr")
        .includes(normalizedQuery);
    });

    grid.replaceChildren();
    filteredApps.forEach(function (app) {
      grid.appendChild(createAppCard(app));
    });
    emptyState.hidden = filteredApps.length > 0;
  }

  function openApp(app) {
    shell.classList.add("app-open");
    appFrame.dataset.autoHeight = String(
      new URL(app.url, window.location.href).origin === window.location.origin,
    );
    document.getElementById("active-title").textContent = app.name;
    const activeIcon = document.getElementById("active-icon");
    setAppIcon(activeIcon, app);
    appFrame.title = app.name;
    appFrame.src = app.url;
    externalLink.href = app.url;
    if (embeddedGreeting) {
      embeddedGreeting.hidden = app.id !== "cent-cols";
    }
    frameHelpLink.href = app.url;
    heading.hidden = true;
    grid.hidden = true;
    search.closest(".section-heading").hidden = true;
    emptyState.hidden = true;
    appView.hidden = false;
    breadcrumb.textContent = app.name;
    document.querySelector(".help-card").hidden = true;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function showHome() {
    shell.classList.remove("app-open");
    appFrame.removeAttribute("src");
    delete appFrame.dataset.autoHeight;
    appFrame.style.removeProperty("height");
    appView.hidden = true;
    if (embeddedGreeting) {
      embeddedGreeting.hidden = true;
    }
    heading.hidden = false;
    grid.hidden = false;
    search.closest(".section-heading").hidden = false;
    document.querySelector(".help-card").hidden = false;
    breadcrumb.textContent = "Accueil";
    renderApps(search.value);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  headingCount.textContent = String(validApps.length).padStart(2, "0");
  renderApps("");
  appFrame.addEventListener("load", function () {
    resizeAppFrame();
    if (appFrame.dataset.autoHeight === "true") {
      appFrame.contentDocument.defaultView.addEventListener("resize", resizeAppFrame);
    }
  });

  search.addEventListener("input", function () {
    renderApps(search.value);
  });
  search.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      search.value = "";
      renderApps("");
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "/" && document.activeElement !== search &&
        !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      event.preventDefault();
      search.focus();
    }
  });
  document.getElementById("back-button").addEventListener("click", showHome);
})();
