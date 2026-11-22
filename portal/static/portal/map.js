(function () {
  "use strict";

  document.body.classList.toggle("embedded", window.self !== window.top);

  const mapElement = document.getElementById("map");
  const errorElement = document.getElementById("map-error");
  const dataElement = document.getElementById("map-cols");
  const countryFilter = document.getElementById("country-filter");
  const departmentFilter = document.getElementById("department-filter");
  const totalElement = document.getElementById("map-total-count");
  const totalLabel = document.getElementById("map-total-label");
  const mapPanel = document.getElementById("map-panel");
  const passedColsPanel = document.getElementById("passed-cols-panel");
  const monthlyStatsPanel = document.getElementById("monthly-col-stats-panel");
  const mapTab = document.getElementById("map-tab");
  const passedColsTab = document.getElementById("passed-cols-tab");
  const monthlyStatsTab = document.getElementById("monthly-col-stats-tab");
  const passedYearOnly = document.getElementById("passed-year-only");
  const passedVisibleCount = document.getElementById("passed-visible-count");
  const passedFilterEmpty = document.getElementById("passed-filter-empty");
  let map = null;
  let currentBounds = [];
  let mapVisibleCount = Number(totalElement.textContent);
  let activeView = "map";

  function refreshTotal() {
    if (activeView === "passed") {
      totalElement.textContent = passedVisibleCount ? passedVisibleCount.textContent : "0";
      totalLabel.textContent = "cols affichés";
    } else if (activeView === "statistics") {
      totalElement.textContent = String(
        document.querySelectorAll("#monthly-col-stats-panel tbody tr").length
      );
      totalLabel.textContent = "mois affichés";
    } else {
      totalElement.textContent = String(mapVisibleCount);
      totalLabel.textContent = "cols affichés";
    }
  }

  function fitCurrentBounds() {
    if (currentBounds.length > 1) {
      map.fitBounds(currentBounds, { padding: [24, 24], maxZoom: 7 });
    } else if (currentBounds.length === 1) {
      map.setView(currentBounds[0], 9);
    }
  }

  function showView(view) {
    activeView = view;
    mapPanel.hidden = view !== "map";
    passedColsPanel.hidden = view !== "passed";
    monthlyStatsPanel.hidden = view !== "statistics";
    mapTab.setAttribute("aria-pressed", String(view === "map"));
    passedColsTab.setAttribute("aria-pressed", String(view === "passed"));
    monthlyStatsTab.setAttribute("aria-pressed", String(view === "statistics"));
    refreshTotal();
    if (view === "map" && map) {
      window.requestAnimationFrame(function () {
        map.invalidateSize();
        fitCurrentBounds();
      });
    }
  }

  mapTab.addEventListener("click", function () {
    showView("map");
  });
  passedColsTab.addEventListener("click", function () {
    filterPassedCols();
    showView("passed");
  });
  monthlyStatsTab.addEventListener("click", function () {
    showView("statistics");
  });
  if (window.location.hash === "#cols-franchis") {
    showView("passed");
  } else if (window.location.hash === "#statistiques-mensuelles") {
    showView("statistics");
  }

  function filterPassedCols() {
    if (!passedYearOnly) {
      return;
    }

    const rows = Array.from(
      document.querySelectorAll("#passed-cols-panel tbody tr")
    );
    rows.sort(function (leftRow, rightRow) {
      const yearDifference = Number(rightRow.dataset.yearCount) -
        Number(leftRow.dataset.yearCount);
      if (passedYearOnly.checked && yearDifference !== 0) {
        return yearDifference;
      }

      const totalDifference = Number(rightRow.dataset.colCount) -
        Number(leftRow.dataset.colCount);
      if (totalDifference !== 0) {
        return totalDifference;
      }

      const leftName = leftRow.querySelector('th[scope="row"]').textContent.trim();
      const rightName = rightRow.querySelector('th[scope="row"]').textContent.trim();
      return leftName.localeCompare(rightName, "fr");
    });

    if (rows.length) {
      const tableBody = rows[0].parentElement;
      rows.forEach(function (row) {
        tableBody.appendChild(row);
      });
    }

    let visibleCount = 0;

    rows.forEach(function (row) {
      const matchesCountry = !countryFilter.value ||
        row.dataset.countryCode === countryFilter.value;
      const matchesDepartment = !departmentFilter.value ||
        row.dataset.departmentCode === departmentFilter.value;
      const matchesYear = !passedYearOnly.checked ||
        Number(row.dataset.yearCount) > 0;
      const matches = matchesCountry && matchesDepartment && matchesYear;
      row.hidden = !matches;
      if (matches) {
        visibleCount += 1;
      }
    });

    passedVisibleCount.textContent = String(visibleCount);
    refreshTotal();
    passedFilterEmpty.hidden = visibleCount > 0;
  }

  if (passedYearOnly) {
    passedYearOnly.checked = false;
    passedYearOnly.addEventListener("change", filterPassedCols);
    window.addEventListener("pageshow", function () {
      passedYearOnly.checked = false;
      filterPassedCols();
    });
  }

  if (!mapElement || !dataElement) {
    return;
  }

  if (!window.L || !L.markerClusterGroup) {
    errorElement.hidden = false;
    errorElement.textContent = "La carte n’a pas pu être chargée. Vérifiez votre connexion internet puis actualisez la page.";
    return;
  }

  const cols = JSON.parse(dataElement.textContent);
  map = L.map(mapElement, { preferCanvas: true }).setView([45.5, 5], 6);

  const tileLayer = L.tileLayer("/map-tiles/{z}/{x}/{y}.png?source=osmfr-hot", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &middot; Tiles style by <a href="https://www.hotosm.org/">HOT</a>, hosted by <a href="https://www.openstreetmap.fr/">OpenStreetMap France</a>'
  }).addTo(map);
  tileLayer.on("tileerror", function () {
    errorElement.hidden = false;
    errorElement.textContent = "Le fond de carte n’a pas pu être chargé. Vérifiez votre connexion internet puis actualisez la page.";
  });
  tileLayer.on("load", function () {
    errorElement.hidden = true;
  });

  const typeNames = {
    R: "Route",
    P: "Piste",
    S: "Sentier",
    O: "Autre"
  };
  const typeLayers = {};
  const countries = new Map();
  const departments = new Map();

  Object.keys(typeNames).forEach(function (type) {
    typeLayers[type] = L.markerClusterGroup({
      chunkedLoading: true,
      showCoverageOnHover: false
    });
  });

  cols.forEach(function (col) {
    countries.set(col.country_code, col.country_name);
    if (!departments.has(col.country_code)) {
      departments.set(col.country_code, new Map());
    }
    departments.get(col.country_code).set(
      col.department_code,
      col.department_name
    );
  });

  Array.from(countries.entries())
    .sort(function (left, right) {
      return left[1].localeCompare(right[1], "fr");
    })
    .forEach(function (country) {
      countryFilter.add(new Option(country[1], country[0]));
    });

  function populateDepartments(countryCode) {
    departmentFilter.replaceChildren();
    if (!countryCode) {
      departmentFilter.add(new Option("Choisissez un pays", ""));
      departmentFilter.disabled = true;
      return;
    }

    departmentFilter.add(new Option("Tous les départements", ""));
    const countryDepartments = departments.get(countryCode);
    Array.from(countryDepartments.entries())
      .sort(function (left, right) {
        return left[1].localeCompare(right[1], "fr");
      })
      .forEach(function (department) {
        departmentFilter.add(new Option(department[1], department[0]));
      });
    departmentFilter.disabled = countryDepartments.size === 0;
  }

  function createIcon(passed) {
    const stateClass = passed ? "col-marker-passed" : "col-marker-unpassed";
    return L.divIcon({
      className: "",
      html: '<span class="col-marker ' + stateClass + '" aria-hidden="true"><span>⚑</span></span>' +
        (passed ? '<span class="col-marker-check" aria-hidden="true">✓</span>' : ''),
      iconSize: [27, 31],
      iconAnchor: [13, 30],
      popupAnchor: [0, -27]
    });
  }

  function createPopup(col) {
    const content = document.createElement("div");
    const title = document.createElement("strong");
    title.className = "popup-title";
    title.textContent = col.name;
    const detail = document.createElement("span");
    detail.textContent = col.altitude === null
      ? "Altitude non renseignée"
      : Math.round(Number(col.altitude)) + " m";
    content.append(title, detail);
    if (col.passed) {
      const activitiesLink = document.createElement("a");
      activitiesLink.className = "popup-activities-link";
      activitiesLink.href = "/cols/" + encodeURIComponent(col.code) + "/activities/";
      activitiesLink.textContent = "Voir les activités";
      content.appendChild(activitiesLink);
    }
    return content;
  }

  const markers = cols.map(function (col) {
    const type = Object.prototype.hasOwnProperty.call(typeLayers, col.type)
      ? col.type
      : "O";
    const marker = L.marker([col.latitude, col.longitude], {
      icon: createIcon(col.passed),
      title: col.name,
      alt: col.name
    });
    marker.bindPopup(createPopup(col));
    return { col: col, marker: marker, type: type };
  });

  const overlays = {};
  Object.keys(typeLayers).forEach(function (type) {
    typeLayers[type].addTo(map);
    overlays[typeNames[type]] = typeLayers[type];
  });
  L.control.layers(null, overlays, { collapsed: window.innerWidth < 600 }).addTo(map);

  function updateMarkers() {
    Object.keys(typeLayers).forEach(function (type) {
      typeLayers[type].clearLayers();
    });

    const selectedCountry = countryFilter.value;
    const selectedDepartment = departmentFilter.value;
    const bounds = [];
    let visibleCount = 0;

    markers.forEach(function (entry) {
      const col = entry.col;
      if (selectedCountry && col.country_code !== selectedCountry) {
        return;
      }
      if (selectedDepartment && col.department_code !== selectedDepartment) {
        return;
      }

      typeLayers[entry.type].addLayer(entry.marker);
      bounds.push([col.latitude, col.longitude]);
      visibleCount += 1;
    });

    mapVisibleCount = visibleCount;
    filterPassedCols();
    refreshTotal();
    currentBounds = bounds;
    fitCurrentBounds();
  }

  function lastVisitedDepartmentBounds() {
    let lastCol = null;
    let lastTime = NaN;
    cols.forEach(function (col) {
      const time = Date.parse(col.last_passage_date);
      if (!Number.isNaN(time) && (Number.isNaN(lastTime) || time > lastTime)) {
        lastCol = col;
        lastTime = time;
      }
    });
    if (!lastCol) {
      return [];
    }
    return cols
      .filter(function (col) {
        return col.country_code === lastCol.country_code &&
          col.department_code === lastCol.department_code;
      })
      .map(function (col) {
        return [col.latitude, col.longitude];
      });
  }

  populateDepartments("");
  countryFilter.addEventListener("change", function () {
    populateDepartments(countryFilter.value);
    updateMarkers();
  });
  departmentFilter.addEventListener("change", function () {
    updateMarkers();
    saveViewRegion();
  });
  updateMarkers();

  const savedRegion = JSON.parse(document.getElementById("view-region").textContent);
  let initialBounds = savedRegion
    ? departmentBounds(savedRegion.country_code, savedRegion.region_code)
    : [];
  if (!initialBounds.length) {
    initialBounds = lastVisitedDepartmentBounds();
  }
  if (initialBounds.length) {
    currentBounds = initialBounds;
    fitCurrentBounds();
  }

  window.requestAnimationFrame(function () {
    map.invalidateSize();
    fitCurrentBounds();
  });
  window.addEventListener("resize", function () {
    if (!mapPanel.hidden) {
      map.invalidateSize();
      fitCurrentBounds();
    }
  });

  function departmentBounds(countryCode, departmentCode) {
    return cols
      .filter(function (col) {
        return col.country_code === countryCode && col.department_code === departmentCode;
      })
      .map(function (col) {
        return [col.latitude, col.longitude];
      });
  }

  function saveViewRegion() {
    const countryCode = countryFilter.value;
    const departmentCode = departmentFilter.value;
    if (!countryCode || !departmentCode) {
      return;
    }
    const csrfInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    fetch("/vue/departement/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfInput ? csrfInput.value : ""
      },
      body: JSON.stringify({ country_code: countryCode, region_code: departmentCode })
    }).catch(function () {});
  }
})();
