const socket = io();
const activeMicAdjustments = new Set();
let roleDescriptions = {};

function getBatteryIcon(device) {
  if (device.battery_powered !== "1") return '';

  const v = parseInt(device.battery_voltage, 10);
  let bars = 0;
  let levelClass = '';

  if (v >= 8000) {
    bars = 5;
    levelClass = 'battery-good';
  } else if (v >= 7675) {
    bars = 4;
    levelClass = 'battery-good';
  } else if (v >= 7350) {
    bars = 3;
    levelClass = 'battery-warn';
  } else if (v >= 7025) {
    bars = 2;
    levelClass = 'battery-warn';
  } else if (v >= 6700) {
    bars = 1;
    levelClass = 'battery-warn';
  } else {
    bars = 0;
    levelClass = 'battery-critical';
  }

  return `
    <div class="battery ${levelClass}" data-voltage="${v}">
      <div class="battery-body">
        ${bars > 0
          ? [1, 2, 3, 4, 5].map(i =>
              `<div class="battery-bar ${bars >= i ? 'on' : ''}"></div>`
            ).join('')
          : `<div class="battery-label">LOW</div>`
        }
      </div>
      <div class="battery-tip"></div>
    </div>
  `;
}

function getWifiClass(level) {
  if (typeof level !== "string") return "wifi-unknown";

  const match = level.match(/-?\d+/); // extract just the number
  if (!match) return "wifi-unknown";

  const signal = parseInt(match[0], 10);

  if (signal >= -50) return "wifi-excellent";
  if (signal >= -65) return "wifi-good";
  if (signal >= -80) return "wifi-weak";
  return "wifi-poor";
}

function safeNumber(val, fallback = -1) {
  const num = Number(val);
  return Number.isFinite(num) ? num : fallback;
}

function buildDeviceHTML(deviceName, d) {
  const typeClass = d.device_type ? `type-${d.device_type.toLowerCase()}` : '';
  const battery = getBatteryIcon(d);
  const deviceData = JSON.stringify(d).replace(/"/g, '&quot;');
  let micLevel = safeNumber(d.mic_level);
  const isInMenu = Number(d.in_menu) === 1;
  const allowMicChange = Number(d.allow_mic_level_change) === 1;
  const micDisabled = !(allowMicChange && !isInMenu);
  const micDisabledAttr = micDisabled ? "disabled" : "";



  return `
    <div class="device-card ${typeClass}" data-device="${deviceName}">
      <div class="device-header">
        <div class="device-name">
          ${deviceName}
          <i class="fas fa-pen edit-icon" data-device='${deviceData}' data-tooltip="Edit device settings"></i>
        </div>
        <div class="device-state ${d.state.toLowerCase()}">${d.state.toUpperCase()}</div>
      </div>
      <div class="device-meta-row">
        <span class="device-role ${!d.device_role ? 'unassigned' : ''}">
          ${d.device_role?.trim() || "Pending Setup"}
        </span>
        <div class="battery-wrapper">${battery}</div>
      </div>
      
      <div class="device-info-row">
        <span class="device-ip">
          ${d.device_ip || "N/A"}
        </span>
        ${
          d.device_type?.toLowerCase() === "beltpack"
            ? `<span class="device-wifi">
                <i class="fas fa-wifi"></i>
                <span class="wifi-signal ${getWifiClass(d.wifi_signal_level)}">
                  ${d.wifi_signal_level || "N/A"}
                </span>
              </span>`
            : ""
        }
      </div>

      <div class="device-audio-row">
        <div class="mic" ${micDisabled ? 'data-remote-disabled="true"' : ''}>
          <i class="fas fa-microphone"></i>
          <input
            type="range"
            min="0"
            max="150"
            step="5"
            value="${micLevel}"
            class="mic-slider-input"
            data-device="${deviceName}"
            ${micDisabledAttr}
            ${!micDisabled ? 'data-tooltip="Adjust microphone input level for this device."' : ''}
          />
          <span class="mic-value">${micLevel === -1 ? "N/A" : micLevel}</span>
        </div>
        <div class="hs-audio">
          ${
            d.device_type?.toLowerCase() === "basestation" && d.headset_state === "0"
              ? `<i class="fas fa-volume-up"></i>
                <span class="hs-value">${safeNumber(d.speaker_audio_level) === -1 ? "N/A" : safeNumber(d.speaker_audio_level)}</span>`
              : `<i class="fas fa-headphones"></i>
                <span class="hs-value">${safeNumber(d.hs_audio_level) === -1 ? "N/A" : safeNumber(d.hs_audio_level)}</span>`
          }
        </div>
      </div>
      <ul class="device-data">
        <li class="talk">${d.talk && d.talk.toUpperCase() !== 'NOT TALKING'
          ? `Talking to: ${d.talk.replace(/,/g, ', ')}`
          : 'Not talking'}</li>
      </ul>
    </div>
  `;
}

function bindSliderEventsForDevice(deviceName) {
  const slider = document.querySelector(`.mic-slider-input[data-device="${deviceName}"]`);
  if (!slider) return;

  slider.addEventListener("input", function () {
    this.nextElementSibling.textContent = this.value;
  });

  slider.addEventListener("mousedown", function () {
    activeMicAdjustments.add(deviceName);
  });

  slider.addEventListener("change", function () {
    if (this.disabled) return;

    const value = this.value;
    activeMicAdjustments.delete(deviceName);
    this.nextElementSibling.textContent = value;

    socket.emit("set_mic_level", {
      device: deviceName,
      level: parseInt(value, 10)
    });
  });
}

socket.on("roles", function (data) {
  roleDescriptions = data;
});

socket.on("update", function (devices) {
  const deviceGrid = document.querySelector(".device-grid");
  const noDevicesMsg = document.getElementById("no-devices-message");

  if (!deviceGrid) {
    document.getElementById("device-list").innerHTML = `<div class="device-grid"></div>`;
  }

  const deviceNames = Object.keys(devices);
  if (deviceNames.length === 0) {
    noDevicesMsg.classList.remove("hidden");
  } else {
    noDevicesMsg.classList.add("hidden");
  }

  for (const [deviceName, d] of Object.entries(devices)) {
    const existing = document.querySelector(`.device-card[data-device="${deviceName}"]`);
    const newHTML = buildDeviceHTML(deviceName, d);

    if (activeMicAdjustments.has(deviceName)) continue;

    if (existing) {
      existing.outerHTML = newHTML;
    } else {
      document.querySelector(".device-grid").insertAdjacentHTML("beforeend", newHTML);
    }

    bindSliderEventsForDevice(deviceName);
  }
});

document.addEventListener("click", e => {
  if (e.target.classList.contains("edit-icon")) {
    const deviceData = JSON.parse(e.target.getAttribute("data-device"));
    deviceData.device_id = e.target.closest(".device-card")?.querySelector(".device-name")?.childNodes[0]?.nodeValue?.trim() || "Unknown";
    openModal(deviceData);
  }

  if (e.target.id === "close-modal") {
    document.getElementById("edit-modal").classList.add("hidden");
  }
});

document.getElementById("save-role-config").addEventListener("click", () => {
  const deviceId = document.getElementById("modal-device-name").textContent.trim();
  const role = document.getElementById("device-role-select").value;
  const toggles = document.querySelectorAll(".toggle-box");

  const channels = {};

  toggles.forEach(toggle => {
    const channel = toggle.getAttribute("data-channel");
    const role = toggle.getAttribute("data-role");

    if (!channels[channel]) channels[channel] = [];

    if (toggle.classList.contains("selected")) {
      channels[channel].push(role);
    }
  });

  socket.emit("save_device_config", {
    device: deviceId,
    role,
    channels
  });

  document.getElementById("edit-modal").classList.add("hidden");
});


function openModal(device) {
  const modal = document.getElementById("edit-modal");
  const content = document.getElementById("modal-content");
  const deviceNameEl = document.getElementById("modal-device-name");
  const roleSelect = document.getElementById("device-role-select");
  const tbody = document.getElementById("role-channel-body");

  // Set styling
  content.classList.remove("type-beltpack", "type-basestation");
  if (device.device_type) {
    content.classList.add(`type-${device.device_type.toLowerCase()}`);
  }

  // Set device name
  deviceNameEl.textContent = device.device_id || device.device_name || "Unknown";

  // Populate role dropdown
  const currentRole = device.device_role;
  const hasValidRole = currentRole && roleDescriptions.hasOwnProperty(currentRole);

  roleSelect.innerHTML =
    (!hasValidRole ? `<option value="" selected>Not Set</option>` : "") +
    Object.keys(roleDescriptions).map(role =>
      `<option value="${role}" ${role === currentRole ? "selected" : ""}>${role}</option>`
  ).join("");

  if (!hasValidRole) {
    roleSelect.classList.add("unassigned");
  } else {
    roleSelect.classList.remove("unassigned");
  }

  let channels = [];
  const channelCount = parseInt(device.device_channels, 10);

  if (Number.isFinite(channelCount) && channelCount > 0) {
    channels = Array.from({ length: channelCount }, (_, i) => String(i + 1));
  } else if (device.channels && typeof device.channels === 'object') {
    channels = Object.keys(device.channels);
  }
  const roleKeys = Object.keys(roleDescriptions);
  
  // Add channel headers
  const thead = document.querySelector(".channel-role-table thead tr");
  thead.innerHTML = `<th>Role</th>` +
    channels.map(ch => `<th>CH ${ch}</th>`).join("") +
    `<th>Description</th>`;

  // Build body
  tbody.innerHTML = roleKeys.map(role => {

    const assignedChannels = channels.map(ch => {
      const roles = device.channels?.[ch];
      const roleArray = Array.isArray(roles) ? roles : (typeof roles === "string" ? roles.split(",") : []);
      const selected = roleArray.includes(role);
      return `<td><div class="toggle-box ${selected ? "selected" : ""}" data-role="${role}" data-channel="${ch}"></div></td>`;
    }).join("");

    return `<tr>
      <td class="role-name">${role}</td>
      ${assignedChannels}
      <td class="role-desc">${roleDescriptions[role]}</td>
    </tr>`;
    }).join("");
  
    modal.classList.remove("hidden");
  
    // Toggle handler
    document.querySelectorAll(".toggle-box").forEach(box => {
      box.addEventListener("click", () => {
        box.classList.toggle("selected");
      });
    });
  }

document.addEventListener("DOMContentLoaded", () => {
  const tooltip = document.getElementById("custom-tooltip");
  const deviceList = document.getElementById("device-list");

  if (!tooltip || !deviceList) return;

  deviceList.addEventListener("mouseover", e => {
    const batteryEl = e.target.closest(".battery");
    const micDisabledEl = e.target.closest(".mic[data-remote-disabled='true']");
    const tooltipText = e.target.getAttribute("data-tooltip");
  
    if (batteryEl && deviceList.contains(batteryEl)) {
      tooltip.textContent = `${batteryEl.getAttribute("data-voltage")} mV`;
      tooltip.classList.remove("hidden");
      tooltip.classList.add("visible");
    } else if (micDisabledEl && deviceList.contains(micDisabledEl)) {
      tooltip.textContent = "Device offline, in menu or remote disabled";
      tooltip.classList.remove("hidden");
      tooltip.classList.add("visible");
    } else if (tooltipText) {
      tooltip.textContent = tooltipText;
      tooltip.classList.remove("hidden");
      tooltip.classList.add("visible");
    }
  });

  deviceList.addEventListener("mousemove", e => {
    if (tooltip.classList.contains("visible")) {
      tooltip.style.top = `${e.clientY + 10}px`;
      tooltip.style.left = `${e.clientX + 10}px`;
    }
  });

  deviceList.addEventListener("mouseout", e => {
    const tooltip = document.getElementById("custom-tooltip");
    const fromEl = e.target;
    const toEl = e.relatedTarget;

    const wasTooltipSource =
      fromEl.closest(".battery") ||
      fromEl.closest(".mic[data-remote-disabled='true']") ||
      fromEl.getAttribute("data-tooltip");

    const stillInsideTooltipSource =
      toEl &&
      (toEl.closest(".battery") ||
      toEl.closest(".mic[data-remote-disabled='true']") ||
      toEl.getAttribute("data-tooltip"));

    if (wasTooltipSource && !stillInsideTooltipSource) {
      tooltip.classList.remove("visible");
      tooltip.classList.add("hidden");
    }
  });
  
});

document.addEventListener("mouseover", e => {
  const tooltipText = e.target.getAttribute("data-tooltip");
  const tooltip = document.getElementById("custom-tooltip");
  if (tooltipText && tooltip) {
    tooltip.textContent = tooltipText;
    tooltip.classList.remove("hidden");
    tooltip.classList.add("visible");
  }
});

document.addEventListener("mousemove", e => {
  const tooltip = document.getElementById("custom-tooltip");
  if (tooltip && tooltip.classList.contains("visible")) {
    tooltip.style.top = `${e.clientY + 10}px`;
    tooltip.style.left = `${e.clientX + 10}px`;
  }
});

document.addEventListener("mouseout", e => {
  const tooltip = document.getElementById("custom-tooltip");
  if (e.target.getAttribute("data-tooltip") && tooltip) {
    tooltip.classList.remove("visible");
    tooltip.classList.add("hidden");
  }
});
