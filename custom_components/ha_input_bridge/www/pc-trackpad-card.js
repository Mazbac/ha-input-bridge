class PcTrackpadCard extends HTMLElement {
  setConfig(config) {
    this.storageKey = config.storage_key || "pc-trackpad-card-settings-v2";

    const saved = this._loadSavedSettings();

    this.config = {
      sensitivity: 2.2,
      frame_ms: 16,
      max_step: 220,

      tap_max_ms: 260,
      tap_threshold_px: 10,

      scroll_gain: 3.0,
      scroll_max_step: 80,

      haptics: true,
      live_type: true,

      auto_focus_text_after_left_click: false,
      clear_text_on_auto_focus: true,

      service_domain: "ha_input_bridge",

      service_arm: "arm",
      service_position: "position",
      service_move: "move",
      service_move_relative: "move_relative",
      service_click: "click",
      service_scroll: "scroll",
      service_write: "write",
      service_press: "press",
      service_hotkey: "hotkey",

      ...config,
      ...saved,
    };

    this.settings = {
      sensitivity: Number(this.config.sensitivity),
      frame_ms: Number(this.config.frame_ms),
      max_step: Number(this.config.max_step),
      scroll_gain: Number(this.config.scroll_gain),
      scroll_max_step: Number(this.config.scroll_max_step),
      haptics: Boolean(this.config.haptics),
      live_type: Boolean(this.config.live_type),
      auto_focus_text_after_left_click: Boolean(this.config.auto_focus_text_after_left_click),
      clear_text_on_auto_focus: Boolean(this.config.clear_text_on_auto_focus),
    };

    this._gesture = null;
    this._dragging = false;

    this._lastX = null;
    this._lastY = null;
    this._totalMove = 0;

    this._pendingDx = 0;
    this._pendingDy = 0;
    this._pendingScroll = 0;

    this._moveTimer = null;
    this._moveInFlight = false;
    this._scrollInFlight = false;

    this._armPromise = null;
    this._armedUntilMs = 0;

    this._keyboardQueue = Promise.resolve();
    this._liveTextValue = "";
    this._suppressInput = false;
    this._lastSpecialKeyMs = 0;

    this._ignorePointerUntil = 0;

    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  getCardSize() {
    return 8;
  }

  _loadSavedSettings() {
    try {
      const raw = window.localStorage.getItem(this.storageKey);
      if (!raw) return {};
      return JSON.parse(raw) || {};
    } catch (_) {
      return {};
    }
  }

  _saveSettings() {
    try {
      window.localStorage.setItem(
        this.storageKey,
        JSON.stringify({
          sensitivity: this.settings.sensitivity,
          frame_ms: this.settings.frame_ms,
          max_step: this.settings.max_step,
          scroll_gain: this.settings.scroll_gain,
          scroll_max_step: this.settings.scroll_max_step,
          haptics: this.settings.haptics,
          live_type: this.settings.live_type,
          auto_focus_text_after_left_click: this.settings.auto_focus_text_after_left_click,
          clear_text_on_auto_focus: this.settings.clear_text_on_auto_focus,
        })
      );
    } catch (_) {}
  }

  _render() {
    this.innerHTML = `
      <ha-card>
        <div class="wrap">
          <div class="topbar">
            <div>
              <div class="title">PC Trackpad</div>
              <div class="subtitle">HA Input Bridge integration mode</div>
            </div>
          </div>

          <div id="pad" class="pad">
            <div class="pad-center">
              <div class="hint">Trackpad</div>
              <div class="subhint">1 vinger muis · tap left · 2 vingers scroll/right · 3 vingers middle</div>
            </div>
          </div>

          <div class="dock">
            <button id="openKeyboard" class="dock-button">⌨ Typen</button>
            <button data-key="enter" class="dock-button">Enter</button>
            <button data-key="backspace" class="dock-button">⌫</button>
            <button data-click="right" class="dock-button">Right</button>
          </div>

          <details id="keyboardPanel" class="panel">
            <summary>Keyboard</summary>

            <div class="text-panel">
              <input
                id="textInput"
                placeholder="Typ naar actieve venster"
                autocomplete="off"
                autocorrect="off"
                autocapitalize="none"
                spellcheck="false"
                enterkeyhint="enter"
              />

              <label class="live-row">
                <input id="liveTypeToggle" type="checkbox" ${this.settings.live_type ? "checked" : ""}>
                Live typen naar PC
              </label>

              <div class="text-actions">
                <button id="sendText">Typ</button>
                <button data-key="enter">Enter</button>
                <button id="clearText">Clear lokaal</button>
              </div>
            </div>
          </details>

          <details class="panel">
            <summary>Quick keys</summary>

            <div class="edit-grid">
              <button data-key="left" class="big">←</button>
              <button data-key="right" class="big">→</button>
              <button data-key="up" class="big">↑</button>
              <button data-key="down" class="big">↓</button>
              <button data-key="backspace" class="big">Backspace</button>
              <button data-key="delete" class="big">Delete</button>
            </div>

            <div class="primary-grid">
              <button data-hotkey="ctrl,a" class="big">Ctrl+A</button>
              <button data-hotkey="ctrl,c" class="big">Ctrl+C</button>
              <button data-hotkey="ctrl,v" class="big">Ctrl+V</button>
            </div>

            <div class="secondary-grid">
              <button data-click="left">Left</button>
              <button data-click="right">Right</button>
              <button data-click="middle">Middle</button>
              <button data-scroll="25">Scroll ↑</button>
              <button data-scroll="-25">Scroll ↓</button>
              <button data-hotkey="ctrl,l">Ctrl+L</button>
              <button data-hotkey="alt,tab">Alt+Tab</button>
              <button data-key="esc">Esc</button>
              <button data-key="space">Space</button>
            </div>
          </details>

          <details class="panel settings">
            <summary>Snelheid en gedrag</summary>

            <div class="slider-row">
              <label>
                Mouse speed
                <span id="sensitivityValue">${this.settings.sensitivity.toFixed(2)}x</span>
              </label>
              <input id="sensitivitySlider" type="range" min="0.4" max="5.0" step="0.05" value="${this.settings.sensitivity}">
            </div>

            <div class="slider-row">
              <label>
                Scroll speed
                <span id="scrollGainValue">${this.settings.scroll_gain.toFixed(2)}x</span>
              </label>
              <input id="scrollGainSlider" type="range" min="0.1" max="8.0" step="0.1" value="${this.settings.scroll_gain}">
            </div>

            <div class="slider-row">
              <label>
                Max mouse step
                <span id="maxStepValue">${this.settings.max_step}px</span>
              </label>
              <input id="maxStepSlider" type="range" min="30" max="300" step="5" value="${this.settings.max_step}">
            </div>

            <div class="slider-row">
              <label>
                Max scroll step
                <span id="scrollMaxStepValue">${this.settings.scroll_max_step}</span>
              </label>
              <input id="scrollMaxStepSlider" type="range" min="5" max="80" step="1" value="${this.settings.scroll_max_step}">
            </div>

            <div class="slider-row">
              <label>
                Frame interval
                <span id="frameValue">${this.settings.frame_ms}ms</span>
              </label>
              <input id="frameSlider" type="range" min="10" max="35" step="1" value="${this.settings.frame_ms}">
            </div>

            <label class="toggle-row">
              <input id="hapticsToggle" type="checkbox" ${this.settings.haptics ? "checked" : ""}>
              Haptic feedback
            </label>

            <label class="toggle-row">
              <input id="autoFocusToggle" type="checkbox" ${this.settings.auto_focus_text_after_left_click ? "checked" : ""}>
              Auto-open keyboard na left click
            </label>

            <label class="toggle-row">
              <input id="clearOnFocusToggle" type="checkbox" ${this.settings.clear_text_on_auto_focus ? "checked" : ""}>
              Clear lokaal tekstveld bij auto-open
            </label>

            <div class="settings-actions">
              <button id="testHaptic">Test haptic</button>
              <button id="resetSettings">Reset snelheden</button>
            </div>
          </details>
        </div>
      </ha-card>

      <style>
        .wrap {
          padding: 12px;
          user-select: none;
          -webkit-user-select: none;
        }

        .topbar {
          margin-bottom: 10px;
        }

        .title {
          font-size: 18px;
          font-weight: 700;
          line-height: 1.2;
        }

        .subtitle {
          font-size: 12px;
          opacity: 0.65;
          margin-top: 2px;
        }

        .pad {
          height: min(52vh, 440px);
          min-height: 310px;
          border: 1px solid var(--divider-color);
          border-radius: 24px;
          background: var(--ha-card-background, var(--card-background-color));
          display: flex;
          align-items: center;
          justify-content: center;
          touch-action: none;
          cursor: crosshair;
          overflow: hidden;
        }

        .pad.active {
          outline: 2px solid var(--primary-color);
          background:
            linear-gradient(
              135deg,
              color-mix(in srgb, var(--primary-color) 10%, transparent),
              transparent 55%
            ),
            var(--ha-card-background, var(--card-background-color));
        }

        .pad-center {
          text-align: center;
          pointer-events: none;
          padding: 14px;
        }

        .hint {
          font-size: 19px;
          font-weight: 700;
          opacity: 0.85;
        }

        .subhint {
          font-size: 12px;
          opacity: 0.55;
          margin-top: 5px;
          max-width: 260px;
        }

        .dock {
          position: sticky;
          bottom: 0;
          z-index: 2;
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 8px;
          margin-top: 10px;
          padding: 8px 0 2px;
          background: var(--ha-card-background, var(--card-background-color));
        }

        .dock-button {
          min-height: 52px;
          font-weight: 700;
        }

        .panel {
          margin-top: 10px;
          padding: 10px;
          border: 1px solid var(--divider-color);
          border-radius: 16px;
          background: color-mix(in srgb, var(--ha-card-background, var(--card-background-color)) 92%, var(--secondary-background-color));
        }

        .panel summary {
          cursor: pointer;
          font-weight: 700;
          font-size: 14px;
          min-height: 36px;
          display: flex;
          align-items: center;
        }

        .text-panel {
          display: grid;
          grid-template-columns: 1fr;
          gap: 8px;
          padding-top: 8px;
        }

        #textInput {
          border: 1px solid var(--divider-color);
          border-radius: 14px;
          padding: 14px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          font-size: 16px;
          min-width: 0;
        }

        #textInput:focus {
          outline: 2px solid var(--primary-color);
        }

        .live-row,
        .toggle-row {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          opacity: 0.85;
          padding-left: 2px;
        }

        .text-actions,
        .edit-grid,
        .primary-grid,
        .secondary-grid,
        .settings-actions {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          margin-top: 8px;
        }

        button {
          border: 1px solid var(--divider-color);
          border-radius: 14px;
          padding: 12px 8px;
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          font-size: 14px;
          min-height: 44px;
        }

        button.big {
          font-size: 15px;
          font-weight: 650;
          min-height: 50px;
        }

        button:active {
          transform: scale(0.985);
        }

        .slider-row {
          margin-top: 12px;
        }

        .slider-row label {
          display: flex;
          justify-content: space-between;
          font-size: 13px;
          opacity: 0.85;
        }

        .slider-row input[type="range"] {
          width: 100%;
          margin-top: 5px;
        }

        @media (max-width: 420px) {
          .wrap {
            padding: 10px;
          }

          .pad {
            height: min(50vh, 410px);
            min-height: 285px;
          }

          button {
            font-size: 13px;
            padding-left: 6px;
            padding-right: 6px;
          }
        }
      </style>
    `;

    const pad = this.querySelector("#pad");

    pad.addEventListener("contextmenu", (ev) => ev.preventDefault());

    pad.addEventListener("touchstart", (ev) => this._touchStart(ev), { passive: false });
    pad.addEventListener("touchmove", (ev) => this._touchMove(ev), { passive: false });
    pad.addEventListener("touchend", (ev) => this._touchEnd(ev), { passive: false });
    pad.addEventListener("touchcancel", (ev) => this._touchCancel(ev), { passive: false });

    pad.addEventListener("pointerdown", (ev) => this._pointerDown(ev));
    pad.addEventListener("pointermove", (ev) => this._pointerMove(ev));
    pad.addEventListener("pointerup", (ev) => this._pointerUp(ev));
    pad.addEventListener("pointercancel", (ev) => this._pointerUp(ev));

    this._bindSettings();
    this._bindButtons();
    this._bindTextInput();
  }

  _callBridge(service, data = {}) {
    return this._hass.callService(this.config.service_domain, service, data);
  }

  _bindTextInput() {
    const input = this.querySelector("#textInput");

    input.addEventListener("keydown", (ev) => {
      if (!this.settings.live_type) return;

      if (ev.key === "Enter") {
        ev.preventDefault();
        this._sendSpecialKeyFromTextInput("enter");
        return;
      }

      if (ev.key === "Backspace" && input.value.length === 0) {
        ev.preventDefault();
        this._sendSpecialKeyFromTextInput("backspace");
        return;
      }

      if (ev.key === "Delete" && input.value.length === 0) {
        ev.preventDefault();
        this._sendSpecialKeyFromTextInput("delete");
        return;
      }
    });

    input.addEventListener("beforeinput", (ev) => {
      if (!this.settings.live_type) return;
      if (this._suppressInput) return;

      const type = ev.inputType;

      if (type === "insertLineBreak" || type === "insertParagraph") {
        ev.preventDefault();
        this._sendSpecialKeyFromTextInput("enter");
        return;
      }

      if (type === "deleteContentBackward" && input.value.length === 0) {
        ev.preventDefault();
        this._sendSpecialKeyFromTextInput("backspace");
        return;
      }

      if (type === "deleteContentForward" && input.value.length === 0) {
        ev.preventDefault();
        this._sendSpecialKeyFromTextInput("delete");
        return;
      }
    });

    input.addEventListener("input", () => {
      if (this._suppressInput) return;

      if (this.settings.live_type) {
        this._syncLiveText(input.value);
      }
    });

    input.addEventListener("change", () => {
      if (this._suppressInput) return;

      if (this.settings.live_type) {
        this._syncLiveText(input.value);
      }
    });
  }

  _sendSpecialKeyFromTextInput(key) {
    const now = Date.now();

    if (now - this._lastSpecialKeyMs < 60) {
      return;
    }

    this._lastSpecialKeyMs = now;
    this._haptic("selection");
    this._queueKeyboard(() => this._keyboardPressNow(key));
  }

  _bindButtons() {
    this.querySelector("#openKeyboard").addEventListener("click", () => {
      const panel = this.querySelector("#keyboardPanel");
      panel.open = true;
      this._focusTextInput(false);
      this._haptic("selection");
    });

    this.querySelector("#testHaptic").addEventListener("click", () => {
      this._haptic("heavy");
    });

    this.querySelector("#resetSettings").addEventListener("click", () => {
      try {
        window.localStorage.removeItem(this.storageKey);
      } catch (_) {}

      this.settings.sensitivity = 2.2;
      this.settings.frame_ms = 16;
      this.settings.max_step = 220;
      this.settings.scroll_gain = 3.0;
      this.settings.scroll_max_step = 80;

      this._saveSettings();
      this._render();
      this._haptic("medium");
    });

    this.querySelectorAll("[data-click]").forEach((btn) => {
      btn.addEventListener("click", () => this._click(btn.dataset.click));
    });

    this.querySelectorAll("[data-scroll]").forEach((btn) => {
      btn.addEventListener("click", () => this._scroll(Number(btn.dataset.scroll)));
    });

    this.querySelectorAll("[data-key]").forEach((btn) => {
      btn.addEventListener("click", () => this._press(btn.dataset.key));
    });

    this.querySelectorAll("[data-hotkey]").forEach((btn) => {
      btn.addEventListener("click", () => this._hotkey(btn.dataset.hotkey.split(",")));
    });

    this.querySelector("#sendText").addEventListener("click", async () => {
      const input = this.querySelector("#textInput");

      if (this.settings.live_type) {
        this._focusTextInput(false);
        this._haptic("selection");
        return;
      }

      const text = input.value;
      this._clearLocalText(input);

      if (text) {
        await this._write(text);
      }
    });

    this.querySelector("#clearText").addEventListener("click", () => {
      const input = this.querySelector("#textInput");
      this._clearLocalText(input);
      this._haptic("selection");
      this._focusTextInput(false);
    });
  }

  _bindSettings() {
    const sensitivitySlider = this.querySelector("#sensitivitySlider");
    const scrollGainSlider = this.querySelector("#scrollGainSlider");
    const maxStepSlider = this.querySelector("#maxStepSlider");
    const scrollMaxStepSlider = this.querySelector("#scrollMaxStepSlider");
    const frameSlider = this.querySelector("#frameSlider");
    const hapticsToggle = this.querySelector("#hapticsToggle");
    const liveTypeToggle = this.querySelector("#liveTypeToggle");
    const autoFocusToggle = this.querySelector("#autoFocusToggle");
    const clearOnFocusToggle = this.querySelector("#clearOnFocusToggle");

    sensitivitySlider.addEventListener("input", () => {
      this.settings.sensitivity = Number(sensitivitySlider.value);
      this.querySelector("#sensitivityValue").textContent =
        `${this.settings.sensitivity.toFixed(2)}x`;
      this._saveSettings();
    });

    scrollGainSlider.addEventListener("input", () => {
      this.settings.scroll_gain = Number(scrollGainSlider.value);
      this.querySelector("#scrollGainValue").textContent =
        `${this.settings.scroll_gain.toFixed(2)}x`;
      this._saveSettings();
    });

    maxStepSlider.addEventListener("input", () => {
      this.settings.max_step = Number(maxStepSlider.value);
      this.querySelector("#maxStepValue").textContent =
        `${this.settings.max_step}px`;
      this._saveSettings();
    });

    scrollMaxStepSlider.addEventListener("input", () => {
      this.settings.scroll_max_step = Number(scrollMaxStepSlider.value);
      this.querySelector("#scrollMaxStepValue").textContent =
        `${this.settings.scroll_max_step}`;
      this._saveSettings();
    });

    frameSlider.addEventListener("input", () => {
      this.settings.frame_ms = Number(frameSlider.value);
      this.querySelector("#frameValue").textContent =
        `${this.settings.frame_ms}ms`;

      if (this._moveTimer) {
        this._stopLoop();
        this._startLoop();
      }

      this._saveSettings();
    });

    hapticsToggle.addEventListener("change", () => {
      this.settings.haptics = hapticsToggle.checked;
      if (this.settings.haptics) this._haptic("medium");
      this._saveSettings();
    });

    liveTypeToggle.addEventListener("change", () => {
      const input = this.querySelector("#textInput");

      this.settings.live_type = liveTypeToggle.checked;
      this._liveTextValue = input.value;

      this._haptic(this.settings.live_type ? "medium" : "selection");
      this._saveSettings();
    });

    autoFocusToggle.addEventListener("change", () => {
      this.settings.auto_focus_text_after_left_click = autoFocusToggle.checked;
      this._haptic(this.settings.auto_focus_text_after_left_click ? "medium" : "selection");
      this._saveSettings();
    });

    clearOnFocusToggle.addEventListener("change", () => {
      this.settings.clear_text_on_auto_focus = clearOnFocusToggle.checked;
      this._haptic(this.settings.clear_text_on_auto_focus ? "medium" : "selection");
      this._saveSettings();
    });
  }

  _focusTextInput(clearFirst = false) {
    const input = this.querySelector("#textInput");
    const panel = this.querySelector("#keyboardPanel");

    if (!input) return;

    if (panel) {
      panel.open = true;
    }

    if (clearFirst) {
      this._clearLocalText(input);
    }

    try {
      input.focus({ preventScroll: true });
    } catch (_) {
      input.focus();
    }

    try {
      const len = input.value.length;
      input.setSelectionRange(len, len);
    } catch (_) {}
  }

  _clearLocalText(input) {
    this._suppressInput = true;
    input.value = "";
    this._liveTextValue = "";

    window.setTimeout(() => {
      this._suppressInput = false;
    }, 0);
  }

  _commonPrefixLength(a, b) {
    const len = Math.min(a.length, b.length);
    let i = 0;

    while (i < len && a[i] === b[i]) {
      i += 1;
    }

    return i;
  }

  _syncLiveText(newText) {
    const oldText = this._liveTextValue || "";

    if (newText === oldText) return;

    const prefixLen = this._commonPrefixLength(oldText, newText);
    const oldTail = oldText.slice(prefixLen);
    const newTail = newText.slice(prefixLen);

    const backspaces = oldTail.length;
    const textToWrite = newTail;

    this._liveTextValue = newText;

    this._queueKeyboard(async () => {
      await this._ensureArmed(10);

      for (let i = 0; i < backspaces; i += 1) {
        await this._keyboardPressNow("backspace");
      }

      if (textToWrite) {
        await this._keyboardWriteNow(textToWrite);
      }
    });
  }

  _queueKeyboard(task) {
    const run = async () => {
      try {
        await task();
      } catch (_) {}
    };

    this._keyboardQueue = this._keyboardQueue.then(run, run);
    return this._keyboardQueue;
  }

  _haptic(pattern = "light") {
    if (!this.settings.haptics) return;

    let hapticType = "light";

    if (typeof pattern === "string") {
      hapticType = pattern;
    } else if (Array.isArray(pattern)) {
      hapticType = "medium";
    } else if (typeof pattern === "number") {
      hapticType = pattern >= 40 ? "heavy" : pattern >= 25 ? "medium" : pattern >= 10 ? "light" : "selection";
    }

    const validTypes = ["success", "warning", "failure", "light", "medium", "heavy", "selection"];
    if (!validTypes.includes(hapticType)) hapticType = "light";

    try {
      this.dispatchEvent(
        new CustomEvent("hass-action", {
          bubbles: true,
          composed: true,
          detail: {
            config: {
              tap_action: {
                action: "none",
                haptic: hapticType,
              },
            },
            action: "tap",
          },
        })
      );
    } catch (_) {}

    try {
      this.dispatchEvent(
        new CustomEvent("haptic", {
          bubbles: true,
          composed: true,
          detail: hapticType,
        })
      );
    } catch (_) {}

    try {
      if ("vibrate" in navigator) {
        const patterns = {
          selection: 8,
          light: 20,
          medium: 35,
          heavy: 55,
          success: [20, 30, 20],
          warning: [30, 40, 30],
          failure: [50, 40, 50],
        };
        navigator.vibrate(patterns[hapticType] || 20);
      }
    } catch (_) {}
  }

  async _ensureArmed(seconds = 30) {
    const now = Date.now();

    if (now < this._armedUntilMs - 2000) {
      return;
    }

    if (!this._armPromise) {
      this._armPromise = this
        ._callBridge(this.config.service_arm, { seconds })
        .then(() => {
          this._armedUntilMs = Date.now() + seconds * 1000;
        })
        .catch(() => {})
        .finally(() => {
          this._armPromise = null;
        });
    }

    await this._armPromise;
  }

  _setActive(active) {
    const pad = this.querySelector("#pad");
    if (!pad) return;

    if (active) {
      pad.classList.add("active");
    } else {
      pad.classList.remove("active");
    }
  }

  _centerOfTouches(touches) {
    let x = 0;
    let y = 0;

    for (const touch of touches) {
      x += touch.clientX;
      y += touch.clientY;
    }

    return {
      x: x / touches.length,
      y: y / touches.length,
    };
  }

  _startLoop() {
    if (this._moveTimer) return;

    this._moveTimer = window.setInterval(() => {
      this._flushMove();
      this._flushScroll();
    }, this.settings.frame_ms);
  }

  _stopLoop() {
    if (!this._moveTimer) return;

    window.clearInterval(this._moveTimer);
    this._moveTimer = null;

    this._flushMove();
    this._flushScroll();
  }

  async _flushMove() {
    if (this._moveInFlight) return;

    const maxStep = Number(this.settings.max_step) || 150;

    let dx = Math.round(this._pendingDx);
    let dy = Math.round(this._pendingDy);

    if (dx === 0 && dy === 0) return;

    dx = Math.max(-maxStep, Math.min(maxStep, dx));
    dy = Math.max(-maxStep, Math.min(maxStep, dy));

    this._pendingDx -= dx;
    this._pendingDy -= dy;

    this._moveInFlight = true;

    try {
      await this._ensureArmed(30);
      await this._callBridge(this.config.service_move_relative, { dx, dy });
    } catch (_) {
    } finally {
      this._moveInFlight = false;
    }
  }

  async _flushScroll() {
    if (this._scrollInFlight) return;

    const maxStep = Number(this.settings.scroll_max_step) || 80;

    let amount = Math.round(this._pendingScroll);

    if (amount === 0) return;

    amount = Math.max(-maxStep, Math.min(maxStep, amount));

    this._pendingScroll -= amount;
    this._scrollInFlight = true;

    try {
      await this._ensureArmed(30);
      await this._callBridge(this.config.service_scroll, { amount });
    } catch (_) {
    } finally {
      this._scrollInFlight = false;
    }
  }

  _touchStart(ev) {
    ev.preventDefault();
    ev.stopPropagation();

    this._ignorePointerUntil = Date.now() + 800;

    const fingers = ev.touches.length;
    const center = this._centerOfTouches(ev.touches);

    this._gesture = {
      fingers,
      lastX: center.x,
      lastY: center.y,
      startTime: Date.now(),
      totalMove: 0,
    };

    this._pendingDx = 0;
    this._pendingDy = 0;
    this._pendingScroll = 0;

    this._setActive(true);

    if (fingers === 1) {
      this._haptic("selection");
    } else if (fingers === 2) {
      this._haptic("light");
    } else {
      this._haptic("medium");
    }

    this._ensureArmed(30);
    this._startLoop();
  }

  _touchMove(ev) {
    ev.preventDefault();
    ev.stopPropagation();

    if (!this._gesture || ev.touches.length === 0) return;

    const fingers = ev.touches.length;
    const center = this._centerOfTouches(ev.touches);

    if (fingers !== this._gesture.fingers) {
      this._gesture.fingers = fingers;
      this._gesture.lastX = center.x;
      this._gesture.lastY = center.y;
      return;
    }

    const rawDx = center.x - this._gesture.lastX;
    const rawDy = center.y - this._gesture.lastY;

    this._gesture.lastX = center.x;
    this._gesture.lastY = center.y;
    this._gesture.totalMove += Math.abs(rawDx) + Math.abs(rawDy);

    if (fingers === 1) {
      this._pendingDx += rawDx * this.settings.sensitivity;
      this._pendingDy += rawDy * this.settings.sensitivity;
    }

    if (fingers === 2) {
      this._pendingScroll += rawDy * this.settings.scroll_gain;
    }
  }

  async _touchEnd(ev) {
    ev.preventDefault();
    ev.stopPropagation();

    if (!this._gesture) {
      this._setActive(false);
      this._stopLoop();
      return;
    }

    if (ev.touches.length > 0) return;

    this._stopLoop();
    this._setActive(false);

    const duration = Date.now() - this._gesture.startTime;
    const moved = this._gesture.totalMove;
    const fingers = this._gesture.fingers;

    const isTap =
      duration <= this.config.tap_max_ms &&
      moved <= this.config.tap_threshold_px;

    this._gesture = null;

    if (!isTap) return;

    if (fingers === 1) {
      this._haptic("light");
      await this._click("left");
    } else if (fingers === 2) {
      this._haptic("medium");
      await this._click("right");
    } else if (fingers >= 3) {
      this._haptic("heavy");
      await this._click("middle");
    }
  }

  _touchCancel(ev) {
    ev.preventDefault();
    ev.stopPropagation();

    this._gesture = null;
    this._setActive(false);
    this._stopLoop();
  }

  _pointerDown(ev) {
    if (Date.now() < this._ignorePointerUntil) return;
    if (ev.pointerType === "touch") return;

    ev.preventDefault();

    const pad = this.querySelector("#pad");
    pad.setPointerCapture(ev.pointerId);

    this._setActive(true);

    this._dragging = true;
    this._lastX = ev.clientX;
    this._lastY = ev.clientY;
    this._totalMove = 0;
    this._pendingDx = 0;
    this._pendingDy = 0;

    this._haptic("selection");
    this._ensureArmed(30);
    this._startLoop();
  }

  _pointerMove(ev) {
    if (Date.now() < this._ignorePointerUntil) return;
    if (!this._dragging) return;

    ev.preventDefault();

    const rawDx = ev.clientX - this._lastX;
    const rawDy = ev.clientY - this._lastY;

    this._lastX = ev.clientX;
    this._lastY = ev.clientY;
    this._totalMove += Math.abs(rawDx) + Math.abs(rawDy);

    this._pendingDx += rawDx * this.settings.sensitivity;
    this._pendingDy += rawDy * this.settings.sensitivity;
  }

  async _pointerUp(ev) {
    if (Date.now() < this._ignorePointerUntil) return;
    if (!this._dragging) return;

    ev.preventDefault();

    this._stopLoop();
    this._setActive(false);

    const wasTap = this._totalMove <= this.config.tap_threshold_px;

    this._dragging = false;
    this._lastX = null;
    this._lastY = null;

    if (wasTap) {
      this._haptic("light");
      await this._click("left");
    }
  }

  async _click(button) {
    if (button === "left") {
      this._haptic("light");

      if (this.settings.auto_focus_text_after_left_click) {
        this._focusTextInput(this.settings.clear_text_on_auto_focus);
      }
    } else if (button === "right") {
      this._haptic("medium");
    } else {
      this._haptic("heavy");
    }

    await this._ensureArmed(10);
    await this._callBridge(this.config.service_click, {
      button,
      clicks: 1,
    });
  }

  async _scroll(amount) {
    this._haptic("selection");

    await this._ensureArmed(10);
    await this._callBridge(this.config.service_scroll, {
      amount,
    });
  }

  async _keyboardWriteNow(text) {
    if (!text) return;

    await this._ensureArmed(10);
    await this._callBridge(this.config.service_write, {
      text,
      interval: 0,
    });
  }

  async _keyboardPressNow(key) {
    await this._ensureArmed(10);
    await this._callBridge(this.config.service_press, {
      key,
    });
  }

  async _press(key) {
    this._haptic("light");
    return this._queueKeyboard(() => this._keyboardPressNow(key));
  }

  async _hotkey(keys) {
    this._haptic("medium");

    await this._ensureArmed(10);
    await this._callBridge(this.config.service_hotkey, {
      keys,
    });
  }

  async _write(text) {
    if (!text) return;

    this._haptic("light");
    return this._queueKeyboard(() => this._keyboardWriteNow(text));
  }
}

customElements.define("pc-trackpad-card", PcTrackpadCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "pc-trackpad-card",
  name: "PC Trackpad Card",
  preview: false,
  description: "Mobile-first trackpad for HA Input Bridge integration.",
});
