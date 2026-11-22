(function () {
  "use strict";

  const table = document.getElementById("dashboard-performances");
  if (table) {
    const rows = Array.from(table.tBodies[0].rows);
    const dateFilter = document.getElementById("performance-date-filter");
    const segmentFilter = document.getElementById("performance-segment-filter");
    const noMatch = document.getElementById("performance-no-match");
    function filterRows() {
      const date = dateFilter.value.trim().toLocaleLowerCase("fr");
      const segment = segmentFilter.value.trim().toLocaleLowerCase("fr");
      let visible = 0;
      rows.forEach((row) => {
        row.hidden = !row.cells[0].textContent.toLocaleLowerCase("fr").includes(date) ||
          !row.cells[1].textContent.toLocaleLowerCase("fr").includes(segment);
        if (!row.hidden) visible += 1;
      });
      noMatch.hidden = visible !== 0;
    }
    dateFilter.addEventListener("input", filterRows);
    segmentFilter.addEventListener("input", filterRows);
    table.querySelectorAll("th button").forEach((button) => {
      button.addEventListener("click", () => {
        const header = button.parentElement;
        const ascending = header.getAttribute("aria-sort") !== "ascending";
        const column = Number(button.dataset.sortColumn);
        rows.sort((a, b) => {
          const first = a.cells[column].dataset.sort;
          const second = b.cells[column].dataset.sort;
          if (!first || !second) return first ? -1 : second ? 1 : 0;
          const result = button.dataset.sortType === "number"
            ? Number(first) - Number(second)
            : first.localeCompare(second, "fr");
          return ascending ? result : -result;
        });
        table.querySelectorAll("th[aria-sort]").forEach((item) => item.removeAttribute("aria-sort"));
        header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        rows.forEach((row) => table.tBodies[0].appendChild(row));
      });
    });
  }

  const canvas = document.getElementById("history-chart");
  if (canvas) {
    const data = JSON.parse(document.getElementById("history-data").textContent)
      .sort((a, b) => Number(a.year) - Number(b.year));
    const context = canvas.getContext("2d");
    const padding = 60;
    const width = canvas.width - 2 * padding;
    const height = canvas.height - 2 * padding;
    const values = data.map((item) => item.seconds);
    const minimum = Math.min(...values);
    const maximum = Math.max(...values);
    const margin = Math.max(10, (maximum - minimum) * 0.1);
    const low = minimum - margin;
    const range = maximum - minimum + 2 * margin;
    const format = (seconds) => {
      const value = Math.max(0, Math.round(seconds));
      return `${Math.floor(value / 3600)}:${String(Math.floor(value / 60) % 60).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
    };
    context.font = "13px sans-serif";
    context.strokeStyle = "#555";
    context.fillStyle = "#ddd";
    for (let i = 0; i <= 4; i += 1) {
      const y = padding + (i / 4) * height;
      context.beginPath();
      context.moveTo(padding, y);
      context.lineTo(padding + width, y);
      context.stroke();
      context.textAlign = "right";
      context.fillText(format(low + range * i / 4), padding - 8, y + 4);
    }
    const points = data.map((item, index) => ({
      x: padding + (data.length === 1 ? width / 2 : index * width / (data.length - 1)),
      y: padding + (item.seconds - low) / range * height,
      year: item.year,
    }));
    context.strokeStyle = "#4fc3f7";
    context.fillStyle = "#4fc3f7";
    context.lineWidth = 2;
    context.beginPath();
    points.forEach((point, index) => {
      if (index === 0) context.moveTo(point.x, point.y);
      else context.lineTo(point.x, point.y);
    });
    context.stroke();
    points.forEach((point) => {
      context.beginPath();
      context.arc(point.x, point.y, 4, 0, 2 * Math.PI);
      context.fill();
      context.textAlign = "center";
      context.fillText(point.year, point.x, canvas.height - padding + 20);
    });
  }
})();
