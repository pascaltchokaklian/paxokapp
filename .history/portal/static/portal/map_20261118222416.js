(function () {
  "use strict";

  document.body.classList.toggle("embedded", window.self !== window.top);

  const mapElement = document.getElementById("map");
  const errorElement = document.getElementById("map-error");
  const dataElement = document.getElementById("map-cols");
  const countryFilter = document.getElementById("country-filter");
  const departmentFilter = document.getElementById("department-filter");
  const totalElement = document.getElementById("map-total-count");
  const mapPanel = document.getElementById("map-panel");
  const passedColsPanel = document.getElementById("passed-cols-panel");
  const mapTab = document.getElementById("map-tab");
  const passedColsTab = document.getElementById("passed-cols-tab");
  const passedYearOnly = document.getElementById("passed-year-only");
  const passedVisibleCount = document.getElementById("passed-visible-count");
  const passedFilterEmpty = document.getElementById("passed-filter-empty");
  let map = null;
  let currentBounds = [];

  function fitCurrentBounds() {
    if (currentBounds.length > 1) {
      map.fitBounds(currentBounds, { padding: [24, 24], maxZoom: 7 });
    } else if (currentBounds.length === 1) {
      map.setView(currentBounds[0], 9);
    }
  }

  function showPassedCols(showPassedCols) {
    mapPanel.hidden = showPassedCols;
    passedColsPanel.hidden = !showPassedCols;
    mapTab.setAttribute("aria-pressed", String(!showPassedCols));
    passedColsTab.setAttribute("aria-pressed", String(showPassedCols));
    if (!showPassedCols && map) {
      window.requestAnimationFrame(function () {
        map.invalidateSize();
        fitCurrentBounds();
      });
    }
  }

  mapTab.addEventListener("click", function () {
    showPassedCols(false);
  });
  passedColsTab.addEventListener("click", function () {
    showPassedCols(true);
  });
  if (window.location.hash === "#cols-franchis") {
    showPassedCols(true);
  }

  function filterPassedCols() {
    if (!passedYearOnly) {
      return;
    }

    const rows = Array.from(
      document.querySelectorAll(".passed-cols-table tbody tr")
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
      const matches = !passedYearOnly.checked || Number(row.dataset.yearCount) > 0;
      row.hidden = !matches;
      if (matches) {
        visibleCount += 1;
      }
    });

    passedVisibleCount.textContent = String(visibleCount);
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

  L.tileLayer("https://tile.openstreetmap.de/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &middot; Tiles <a href="https://www.openstreetmap.de/">openstreetmap.de</a>'
  }).addTo(map);

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
      html: '<span class="col-marker ' + stateClass + '" aria-hidden="true"><span>⚑</span></span>',
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

    totalElement.textContent = String(visibleCount);
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
  departmentFilter.addEventListener("change", updateMarkers);
  updateMarkers();

  const lastDepartmentBounds = lastVisitedDepartmentBounds();
  if (lastDepartmentBounds.length) {
    currentBounds = lastDepartmentBounds;
    fitCurrentBounds();
  }
})();
