(function () {
  "use strict";

  const widget = document.getElementById("weather-widget");
  if (!widget) {
    return;
  }

  const locationElement = document.getElementById("weather-location");
  const iconElement = document.getElementById("weather-icon");
  const temperatureElement = document.getElementById("weather-temperature");
  const conditionElement = document.getElementById("weather-condition");
  const rangeElement = document.getElementById("weather-range");
  const noteElement = document.getElementById("weather-note");

  const conditions = {
    0: ["Dégagé", "☀️"],
    1: ["Principalement dégagé", "🌤️"],
    2: ["Partiellement nuageux", "⛅"],
    3: ["Couvert", "☁️"],
    45: ["Brouillard", "🌫️"],
    48: ["Brouillard givrant", "🌫️"],
    51: ["Bruine légère", "🌦️"],
    53: ["Bruine", "🌦️"],
    55: ["Bruine forte", "🌧️"],
    56: ["Bruine verglaçante", "🌧️"],
    57: ["Bruine verglaçante forte", "🌧️"],
    61: ["Pluie faible", "🌧️"],
    63: ["Pluie", "🌧️"],
    65: ["Pluie forte", "🌧️"],
    66: ["Pluie verglaçante", "🌧️"],
    67: ["Pluie verglaçante forte", "🌧️"],
    71: ["Neige faible", "🌨️"],
    73: ["Neige", "🌨️"],
    75: ["Neige forte", "❄️"],
    77: ["Grains de neige", "❄️"],
    80: ["Averses faibles", "🌦️"],
    81: ["Averses", "🌧️"],
    82: ["Averses fortes", "🌧️"],
    85: ["Averses de neige", "🌨️"],
    86: ["Averses de neige fortes", "❄️"],
    95: ["Orage", "⛈️"],
    96: ["Orage et grêle", "⛈️"],
    99: ["Orage et forte grêle", "⛈️"]
  };

  function displayUnavailable() {
    locationElement.textContent = "Localisation indisponible";
    iconElement.textContent = "⚠️";
    temperatureElement.textContent = "—°";
    conditionElement.textContent = "Météo indisponible";
    rangeElement.textContent = "Données météo indisponibles.";
    noteElement.textContent = "Autorisez la localisation ou vérifiez votre connexion.";
    noteElement.hidden = false;
    widget.setAttribute("aria-busy", "false");
  }

  function getBrowserLocation() {
    return new Promise(function (resolve, reject) {
      if (!navigator.geolocation) {
        reject(new Error("La géolocalisation du navigateur est indisponible."));
        return;
      }

      navigator.geolocation.getCurrentPosition(
        function (position) {
          resolve({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            label: "Ma position",
            note: "",
            source: "browser"
          });
        },
        reject,
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 }
      );
    });
  }

  async function getIpLocation() {
    const locationResponse = await fetch("https://ipapi.co/json/");
    if (!locationResponse.ok) {
      throw new Error("La géolocalisation par IP a échoué.");
    }

    const location = await locationResponse.json();
    const latitude = Number(location.latitude);
    const longitude = Number(location.longitude);
    if (
      location.error ||
      location.latitude == null ||
      location.longitude == null ||
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude)
    ) {
      throw new Error(location.reason || "La position IP est indisponible.");
    }

    return {
      latitude: latitude,
      longitude: longitude,
      label: [location.city, location.country_name].filter(Boolean).join(", ") || "Lieu estimé",
      note: "Localisation estimée par adresse IP.",
      source: "ip"
    };
  }

  async function getBrowserPlaceName(location) {
    const cacheKey =
      "portal-weather-place:" +
      location.latitude.toFixed(3) +
      ":" +
      location.longitude.toFixed(3);

    try {
      const cached = sessionStorage.getItem(cacheKey);
      if (cached) {
        const entry = JSON.parse(cached);
        if (entry.expiresAt > Date.now() && entry.label) {
          return entry.label;
        }
      }
    } catch (error) {
      console.warn("Impossible de lire le nom de lieu mémorisé.", error);
    }

    const parameters = new URLSearchParams({
      format: "jsonv2",
      lat: String(location.latitude),
      lon: String(location.longitude),
      zoom: "13",
      addressdetails: "1",
      "accept-language": "fr"
    });
    const response = await fetch(
      "https://nominatim.openstreetmap.org/reverse?" + parameters.toString(),
      { referrerPolicy: "strict-origin-when-cross-origin" }
    );
    if (!response.ok) {
      throw new Error("Le service de géocodage a renvoyé une erreur.");
    }

    const result = await response.json();
    const address = result.address || {};
    const placeName =
      address.city ||
      address.town ||
      address.village ||
      address.municipality ||
      address.city_district ||
      address.suburb;
    if (!placeName) {
      throw new Error("Aucun nom de commune n’a été trouvé pour cette position.");
    }

    const label = [placeName, address.country].filter(Boolean).join(", ");
    try {
      sessionStorage.setItem(
        cacheKey,
        JSON.stringify({ label: label, expiresAt: Date.now() + 86400000 })
      );
    } catch (error) {
      console.warn("Impossible de mémoriser le nom du lieu.", error);
    }
    return label;
  }

  async function loadWeather() {
    try {
      let location;
      try {
        location = await getBrowserLocation();
      } catch (error) {
        console.info("Position du navigateur indisponible ; utilisation de la localisation IP.", error);
        location = await getIpLocation();
      }

      const parameters = new URLSearchParams({
        latitude: String(location.latitude),
        longitude: String(location.longitude),
        current: "temperature_2m,weather_code",
        daily: "temperature_2m_min,temperature_2m_max",
        forecast_days: "1",
        timezone: "auto"
      });
      const weatherResponse = await fetch(
        "https://api.open-meteo.com/v1/forecast?" + parameters.toString()
      );
      if (!weatherResponse.ok) {
        throw new Error("Le service météo a renvoyé une erreur.");
      }

      const weather = await weatherResponse.json();
      const current = weather.current;
      const daily = weather.daily;
      const temperature = Number(current && current.temperature_2m);
      const minimum = Number(daily && daily.temperature_2m_min && daily.temperature_2m_min[0]);
      const maximum = Number(daily && daily.temperature_2m_max && daily.temperature_2m_max[0]);
      const weatherCode = Number(current && current.weather_code);
      if (![temperature, minimum, maximum, weatherCode].every(Number.isFinite)) {
        throw new Error("La réponse météo est incomplète.");
      }

      const condition = conditions[weatherCode] || ["Conditions météo inconnues", "☁️"];
      locationElement.textContent = location.label;
      iconElement.textContent = condition[1];
      temperatureElement.textContent = Math.round(temperature) + "°C";
      conditionElement.textContent = condition[0];
      rangeElement.textContent =
        "Min " + Math.round(minimum) + "° · Max " + Math.round(maximum) + "°";
      noteElement.textContent = location.note;
      noteElement.hidden = !location.note;
      widget.setAttribute("aria-busy", "false");

      if (location.source === "browser") {
        try {
          locationElement.textContent = await getBrowserPlaceName(location);
        } catch (error) {
          console.warn("Impossible de déterminer le nom du lieu.", error);
          noteElement.textContent = "Nom du lieu indisponible.";
          noteElement.hidden = false;
        }
      }
    } catch (error) {
      console.error("Impossible de charger la météo locale.", error);
      displayUnavailable();
    }
  }

  loadWeather();
})();
