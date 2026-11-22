(function () {
  const mapElement = document.getElementById("activity-map");
  const dataElement = document.getElementById("route-points");
  if (!mapElement || !dataElement || !window.L) {
    if (mapElement) {
      mapElement.hidden = true;
    }
    return;
  }

  const points = JSON.parse(dataElement.textContent);
  const map = L.map(mapElement, { preferCanvas: true });

  L.tileLayer("https://tile.openstreetmap.de/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &middot; Tiles <a href="https://www.openstreetmap.de/">openstreetmap.de</a>'
  }).addTo(map);

  const route = L.polyline(points, { color: "#fc4c02", weight: 4, opacity: 0.9 }).addTo(map);
  L.circleMarker(points[0], { radius: 6, color: "#1a7f37", fillColor: "#1a7f37", fillOpacity: 1 }).addTo(map);
  L.circleMarker(points[points.length - 1], { radius: 6, color: "#b42318", fillColor: "#b42318", fillOpacity: 1 }).addTo(map);
  map.fitBounds(route.getBounds(), { padding: [24, 24] });

  const colsElement = document.getElementById("route-cols");
  const cols = colsElement ? JSON.parse(colsElement.textContent) : [];
  const colIcon = L.divIcon({
    className: "",
    html: '<span class="col-marker col-marker-passed" aria-hidden="true"><span>⚑</span></span>',
    iconSize: [27, 31],
    iconAnchor: [13, 30],
    popupAnchor: [0, -27]
  });
  cols.forEach(function (col) {
    const popup = document.createElement("strong");
    popup.textContent = col.altitude != null ? col.name + " - " + Math.round(col.altitude) + " m" : col.name;
    L.marker([col.latitude, col.longitude], { icon: colIcon, title: col.name }).bindPopup(popup).addTo(map);
  });
})();
