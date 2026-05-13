class PcTrackpadCard extends HTMLElement {
  setConfig(config) {
    this.storageKey = config.storage_key || "pc-trackpad-card-settings-v3";

    const saved = this._loadSavedSettings();

    this.config = {
      sensitivity: 2.8,
      frame_ms: 12,
      max_step: 650,

      tap_max_ms: 320,
      multi_tap_max_ms: 420,
      tap_threshold_px: 14,
      multi_tap_threshold_px: 36,

      long_press_drag_ms: 520,
      drag_start_threshold_px: 28,

      scroll_gain: 3.2,
      scroll_max_step: 220,

      haptics: true,
      live_type: true,
      auto_focus_text_after_left_click: false,
      clear_text_on_auto_focus: true,

      service_domain: "ha_input_bridge",
      service_arm: "arm",
      service_position: "position",
      service_state: "state",
      service_cancel: "cancel",
      service_move: "move",
      service_move_relative: "move_relative",
      service_click: "click",
      service_mouse_down: "mouse_down",
      service_mouse_up: "mouse_up",
      service_release_all: "release_all",
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
      auto_focus_text_after_left_click: Boolean(
        this.config.auto_focus_text_after_left_click
      ),
      clear_text_on_auto_focus: Boolean(this.config.clear_text_on_auto_focus),
    };

    this._hass = null;

    this._gesture = null;
    this._pointerDragging = false;
    this._lastX = null;
    this._lastY = null;

    this._pendingDx = 0;
    this._pendingDy = 0;
    this._pendingScroll = 0;

    this._moveTimer = null;
    this._moveInFlight = false;
    this._scrollInFlight = false;

    this._armPromise = null;
    this._armedUntilMs = 0;

    this._dragActive = false;
    this._dragStartPromise = null;
    this._longPressTimer = null;

    this._keyboardQueue = Promise.resolve();
    this._liveTextValue = "";
    this._suppressInput = false;
    this._lastSpecialKeyMs = 0;

    this._ignorePointerUntil = 0;
    this._lastStatusText = "";
    this._statusClearTimer = null;

    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  getCardSize() {
    return 8;
  }

  disconnectedCallback() {
    this._clearLongPressTimer();
    this._stopLoop();

    if (this._dragActive) {
      this._dragActive = false;
      this._safeMouseUp();
    }
  }

  _loadSavedSettings() {
    try {
      const raw = window.localStorage.getItem(this.storageKey);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
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
          auto_focus_text_after_left_click:
            this.settings.auto_focus_text_after_left_click,
          clear_text_on_auto_focus: this.settings.clear_text_on_auto_focus,
        })
      );
    } catch (_) {}
  }

  _render() {
    this.innerHTML = `
      <ha-card>
        <style>
          :host {
            display: block;
          }

          .card {
            padding: 16px;
          }

          .header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 12px;
          }

          .title {
            font-size: 20px;
            font-weight: 650;
            line-height: 1.2;
          }

          .subtitle {
            margin-top: 4px;
            color: var(--secondary-text-color);
            font-size: 13px;
          }

          .status {
            min-height: 20px;
            color: var(--secondary-text-color);
            font-size: 12px;
            text-align: right;
          }

          .pad-wrap {
            position: relative;
          }

          .pad {
            height: 310px;
            border-radius: 22px;
            background:
              radial-gradient(circle at 25% 20%, rgba(255,255,255,0.16), transparent 34%),
              linear-gradient(145deg, var(--primary-color), var(--accent-color, var(--primary-color)));
            color: var(--text-primary-color, #fff);
            display: flex;
            align-items: center;
            justify-content: center;
            user-select: none;
            touch-action: none;
            overflow: hidden;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
          }

          .pad.active {
            filter: brightness(1.05);
          }

          .pad.dragging {
            box-shadow:
              inset 0 0 0 3px rgba(255,255,255,0.55),
              0 0 0 2px rgba(255,255,255,0.18);
          }

          .pad-content {
            text-align: center;
            pointer-events: none;
            padding: 18px;
          }

          .pad-title {
            font-size: 18px;
            font-weight: 650;
            margin-bottom: 8px;
          }

          .pad-help {
            font-size: 13px;
            opacity: 0.92;
            line-height: 1.45;
          }

          .drag-badge {
            position: absolute;
            top: 14px;
            right: 14px;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(0,0,0,0.35);
            color: #fff;
            font-size: 12px;
            font-weight: 650;
            opacity: 0;
            transform: translateY(-4px);
            transition: opacity 120ms ease, transform 120ms ease;
            pointer-events: none;
          }

          .drag-badge.visible {
            opacity: 1;
            transform: translateY(0);
          }

          .row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
          }

          .section {
            margin-top: 14px;
          }

          .section-title {
            font-size: 13px;
            color: var(--secondary-text-color);
            margin-bottom: 8px;
            font-weight: 650;
          }

          button {
            appearance: none;
            border: none;
            border-radius: 12px;
            padding: 10px 12px;
            background: var(--secondary-background-color);
            color: var(--primary-text-color);
            font: inherit;
            cursor: pointer;
          }

          button.primary {
            background: var(--primary-color);
            color: var(--text-primary-color, #fff);
          }

          button.warning {
            background: var(--error-color, #b00020);
            color: #fff;
          }

          button:active {
            transform: translateY(1px);
          }

          .keyboard-panel {
            margin-top: 14px;
          }

          textarea {
            width: 100%;
            min-height: 92px;
            box-sizing: border-box;
            border-radius: 14px;
            border: 1px solid var(--divider-color);
            padding: 12px;
            background: var(--card-background-color);
            color: var(--primary-text-color);
            font: inherit;
            resize: vertical;
          }

          details {
            margin-top: 14px;
            border-top: 1px solid var(--divider-color);
            padding-top: 12px;
          }

          summary {
            cursor: pointer;
            color: var(--primary-text-color);
            font-weight: 650;
          }

          .setting {
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 10px;
            align-items: center;
            margin-top: 12px;
          }

          .setting label {
            color: var(--primary-text-color);
          }

          .setting small {
            color: var(--secondary-text-color);
            display: block;
            margin-top: 2px;
          }

          input[type="range"] {
            width: 170px;
          }

          .toggles {
            display: grid;
            gap: 8px;
            margin-top: 12px;
          }

          .toggle {
            display: flex;
            gap: 8px;
            align-items: center;
          }

          .footer-note {
            color: var(--secondary-text-color);
            font-size: 12px;
            margin-top: 10px;
            line-height: 1.35;
          }

          @media (max-width: 520px) {
            .card {
              padding: 12px;
            }

            .pad {
              height: 275px;
            }

            .header {
              display: block;
            }

            .status {
              margin-top: 8px;
              text-align: left;
            }

            input[type="range"] {
              width: 140px;
            }
          }
        </style>

        <div class="card">
          <div class="header">
            <div>
              <div class="title">PC Trackpad</div>
              <div class="subtitle">HA Input Bridge integration mode</div>
            </div>
            <div id="status" class="status"></div>
          </div>

          <div class="pad-wrap">
            <div id="pad" class="pad">
              <div class="pad-content">
                <div class="pad-title">Trackpad</div>
                <div class="pad-help">
                  1 vinger bewegen · tap links<br>
                  1 vinger vasthouden + slepen = drag<br>
                  2 vingers scroll · 2 vingers tap rechts<br>
                  3 vingers tap midden
                </div>
              </div>
            </div>
            <div id="dragBadge" class="drag-badge">Dragging</div>
          </div>

          <div class="section">
            <div class="section-title">Playback safety</div>
            <div class="row">
              <button id="cancelPlayback" class="warning">Cancel playback</button>
              <button id="releaseAll">Release mouse</button>
              <button id="getState">State</button>
              <button id="getPosition">Position</button>
            </div>
          </div>

          <div class="section">
            <div class="section-title">Mouse</div>
            <div class="row">
              <button data-click="left" class="primary">Left</button>
              <button data-click="right">Right</button>
              <button data-click="middle">Middle</button>
              <button data-scroll="360">Scroll ↑</button>
              <button data-scroll="-360">Scroll ↓</button>
            </div>
          </div>

          <div class="section">
            <div class="section-title">Keyboard</div>
            <div class="row">
              <button id="openKeyboard">Open keyboard</button>
              <button data-key="enter">Enter</button>
              <button data-key="backspace">Backspace</button>
              <button data-key="delete">Delete</button>
              <button data-key="esc">Esc</button>
              <button data-key="space">Space</button>
            </div>
            <div class="row">
              <button data-key="left">←</button>
              <button data-key="right">→</button>
              <button data-key="up">↑</button>
              <button data-key="down">↓</button>
              <button data-hotkey="ctrl,a">Ctrl+A</button>
              <button data-hotkey="ctrl,c">Ctrl+C</button>
              <button data-hotkey="ctrl,v">Ctrl+V</button>
              <button data-hotkey="ctrl,l">Ctrl+L</button>
              <button data-hotkey="alt,tab">Alt+Tab</button>
            </div>
          </div>

          <details id="keyboardPanel" class="keyboard-panel">
            <summary>Text input</summary>
            <div class="footer-note">
              Live typen stuurt tekst direct naar de PC. Gebruik dit niet voor wachtwoorden of tokens.
            </div>
            <textarea id="textInput" autocomplete="off" autocapitalize="none" spellcheck="false"></textarea>
            <div class="row">
              <button id="sendText" class="primary">Typ</button>
              <button id="clearText">Clear lokaal</button>
            </div>
          </details>

          <details>
            <summary>Snelheid en gedrag</summary>

            <div class="setting">
              <label>
                Mouse speed
                <small id="sensitivityValue">${this.settings.sensitivity.toFixed(2)}x</small>
              </label>
              <input id="sensitivitySlider" type="range" min="0.4" max="8" step="0.1" value="${this.settings.sensitivity}">
            </div>

            <div class="setting">
              <label>
                Scroll speed
                <small id="scrollGainValue">${this.settings.scroll_gain.toFixed(2)}x</small>
              </label>
              <input id="scrollGainSlider" type="range" min="0.5" max="12" step="0.1" value="${this.settings.scroll_gain}">
            </div>

            <div class="setting">
              <label>
                Max mouse step
                <small id="maxStepValue">${this.settings.max_step}px</small>
              </label>
              <input id="maxStepSlider" type="range" min="80" max="1000" step="10" value="${this.settings.max_step}">
            </div>

            <div class="setting">
              <label>
                Max scroll step
                <small id="scrollMaxStepValue">${this.settings.scroll_max_step}</small>
              </label>
              <input id="scrollMaxStepSlider" type="range" min="40" max="2000" step="20" value="${this.settings.scroll_max_step}">
            </div>

            <div class="setting">
              <label>
                Frame interval
                <small id="frameValue">${this.settings.frame_ms}ms</small>
              </label>
              <input id="frameSlider" type="range" min="8" max="40" step="1" value="${this.settings.frame_ms}">
            </div>

            <div class="toggles">
              <label class="toggle">
                <input id="hapticsToggle" type="checkbox" ${this.settings.haptics ? "checked" : ""}>
                Haptic feedback
              </label>

              <label class="toggle">
                <input id="liveTypeToggle" type="checkbox" ${this.settings.live_type ? "checked" : ""}>
                Live typen naar PC
              </label>

              <label class="toggle">
                <input id="autoFocusToggle" type="checkbox" ${this.settings.auto_focus_text_after_left_click ? "checked" : ""}>
                Auto-open keyboard na left click
              </label>

              <label class="toggle">
                <input id="clearOnFocusToggle" type="checkbox" ${this.settings.clear_text_on_auto_focus ? "checked" : ""}>
                Clear lokaal tekstveld bij auto-open
              </label>
            </div>

            <div class="row">
              <button id="testHaptic">Test haptic</button>
              <button id="resetSettings">Reset snelheden</button>
            </div>
          </details>
        </div>
      </ha-card>
    `;

    this._bindPad();
    this._bindButtons();
    this._bindTextInput();
    this._bindSettings();
    this._setStatus("");
  }

  _bindPad() {
    const pad = this.querySelector("#pad");
    if (!pad) return;

    pad.addEventListener("contextmenu", (ev) => ev.preventDefault());

    pad.addEventListener("touchstart", (ev) => this._touchStart(ev), {
      passive: false,
    });
    pad.addEventListener("touchmove", (ev) => this._touchMove(ev), {
      passive: false,
    });
    pad.addEventListener("touchend", (ev) => this._touchEnd(ev), {
      passive: false,
    });
    pad.addEventListener("touchcancel", (ev) => this._touchCancel(ev), {
      passive: false,
    });

    pad.addEventListener("pointerdown", (ev) => this._pointerDown(ev));
    pad.addEventListener("pointermove", (ev) => this._pointerMove(ev));
    pad.addEventListener("pointerup", (ev) => this._pointerUp(ev));
    pad.addEventListener("pointercancel", (ev) => this._pointerUp(ev));
  }

  _bindButtons() {
    this.querySelector("#cancelPlayback")?.addEventListener("click", () => {
      this._cancelPlayback();
    });

    this.querySelector("#releaseAll")?.addEventListener("click", () => {
      this._releaseAll();
    });

    this.querySelector("#getState")?.addEventListener("click", () => {
      this._showBridgeState();
    });

    this.querySelector("#getPosition")?.addEventListener("click", () => {
      this._showPosition();
    });

    this.querySelector("#openKeyboard")?.addEventListener("click", () => {
      const panel = this.querySelector("#keyboardPanel");
      if (panel) panel.open = true;
      this._focusTextInput(false);
      this._haptic("selection");
    });

    this.querySelector("#testHaptic")?.addEventListener("click", () => {
      this._haptic("heavy");
    });

    this.querySelector("#resetSettings")?.addEventListener("click", () => {
      try {
        window.localStorage.removeItem(this.storageKey);
      } catch (_) {}

      this.settings.sensitivity = 2.8;
      this.settings.frame_ms = 12;
      this.settings.max_step = 650;
      this.settings.scroll_gain = 3.2;
      this.settings.scroll_max_step = 220;
      this.settings.haptics = true;
      this.settings.live_type = true;
      this.settings.auto_focus_text_after_left_click = false;
      this.settings.clear_text_on_auto_focus = true;

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
      btn.addEventListener("click", () => {
        this._hotkey(btn.dataset.hotkey.split(","));
      });
    });

    this.querySelector("#sendText")?.addEventListener("click", async () => {
      const input = this.querySelector("#textInput");
      if (!input) return;

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

    this.querySelector("#clearText")?.addEventListener("click", () => {
      const input = this.querySelector("#textInput");
      if (!input) return;

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

    sensitivitySlider?.addEventListener("input", () => {
      this.settings.sensitivity = Number(sensitivitySlider.value);
      this.querySelector("#sensitivityValue").textContent =
        `${this.settings.sensitivity.toFixed(2)}x`;
      this._saveSettings();
    });

    scrollGainSlider?.addEventListener("input", () => {
      this.settings.scroll_gain = Number(scrollGainSlider.value);
      this.querySelector("#scrollGainValue").textContent =
        `${this.settings.scroll_gain.toFixed(2)}x`;
      this._saveSettings();
    });

    maxStepSlider?.addEventListener("input", () => {
      this.settings.max_step = Number(maxStepSlider.value);
      this.querySelector("#maxStepValue").textContent =
        `${this.settings.max_step}px`;
      this._saveSettings();
    });

    scrollMaxStepSlider?.addEventListener("input", () => {
      this.settings.scroll_max_step = Number(scrollMaxStepSlider.value);
      this.querySelector("#scrollMaxStepValue").textContent =
        `${this.settings.scroll_max_step}`;
      this._saveSettings();
    });

    frameSlider?.addEventListener("input", () => {
      this.settings.frame_ms = Number(frameSlider.value);
      this.querySelector("#frameValue").textContent =
        `${this.settings.frame_ms}ms`;

      if (this._moveTimer) {
        this._stopLoop();
        this._startLoop();
      }

      this._saveSettings();
    });

    hapticsToggle?.addEventListener("change", () => {
      this.settings.haptics = hapticsToggle.checked;
      if (this.settings.haptics) this._haptic("medium");
      this._saveSettings();
    });

    liveTypeToggle?.addEventListener("change", () => {
      const input = this.querySelector("#textInput");
      this.settings.live_type = liveTypeToggle.checked;
      this._liveTextValue = input ? input.value : "";
      this._haptic(this.settings.live_type ? "medium" : "selection");
      this._saveSettings();
    });

    autoFocusToggle?.addEventListener("change", () => {
      this.settings.auto_focus_text_after_left_click = autoFocusToggle.checked;
      this._haptic(
        this.settings.auto_focus_text_after_left_click ? "medium" : "selection"
      );
      this._saveSettings();
    });

    clearOnFocusToggle?.addEventListener("change", () => {
      this.settings.clear_text_on_auto_focus = clearOnFocusToggle.checked;
      this._haptic(
        this.settings.clear_text_on_auto_focus ? "medium" : "selection"
      );
      this._saveSettings();
    });
  }

  _bindTextInput() {
    const input = this.querySelector("#textInput");
    if (!input) return;

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

  _callBridge(service, data = {}) {
    if (!this._hass) {
      return Promise.reject(new Error("Home Assistant object is not available"));
    }

    return this._hass.callService(this.config.service_domain, service, data);
  }

  _setStatus(text, clearAfterMs = 0) {
    const status = this.querySelector("#status");
    if (!status) return;

    this._lastStatusText = text || "";
    status.textContent = this._lastStatusText;

    if (this._statusClearTimer) {
      window.clearTimeout(this._statusClearTimer);
      this._statusClearTimer = null;
    }

    if (clearAfterMs > 0) {
      this._statusClearTimer = window.setTimeout(() => {
        const current = this.querySelector("#status");
        if (current && current.textContent === this._lastStatusText) {
          current.textContent = "";
        }
      }, clearAfterMs);
    }
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

  _setDragging(active) {
    const pad = this.querySelector("#pad");
    const badge = this.querySelector("#dragBadge");

    if (active) {
      pad?.classList.add("dragging");
      badge?.classList.add("visible");
      this._setStatus("Dragging");
    } else {
      pad?.classList.remove("dragging");
      badge?.classList.remove("visible");
      if (this._lastStatusText === "Dragging") {
        this._setStatus("");
      }
    }
  }

  _clearLongPressTimer() {
    if (!this._longPressTimer) return;
    window.clearTimeout(this._longPressTimer);
    this._longPressTimer = null;
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
    } catch (err) {
      this._handleServiceError(err);
    } finally {
      this._moveInFlight = false;
    }
  }

  async _flushScroll() {
    if (this._scrollInFlight) return;

    const maxStep = Number(this.settings.scroll_max_step) || 220;
    let amount = Math.round(this._pendingScroll);

    if (amount === 0) return;

    amount = Math.max(-maxStep, Math.min(maxStep, amount));
    this._pendingScroll -= amount;
    this._scrollInFlight = true;

    try {
      await this._ensureArmed(30);
      await this._callBridge(this.config.service_scroll, { amount });
    } catch (err) {
      this._handleServiceError(err);
    } finally {
      this._scrollInFlight = false;
    }
  }

  _touchStart(ev) {
    ev.preventDefault();
    ev.stopPropagation();

    this._ignorePointerUntil = Date.now() + 800;
    this._clearLongPressTimer();

    const fingers = ev.touches.length;
    const center = this._centerOfTouches(ev.touches);

    this._gesture = {
      type: "touch",
      fingers,
      lastX: center.x,
      lastY: center.y,
      startX: center.x,
      startY: center.y,
      startTime: Date.now(),
      totalMove: 0,
      dragEligible: fingers === 1,
      dragActive: false,
    };

    this._pendingDx = 0;
    this._pendingDy = 0;
    this._pendingScroll = 0;

    this._setActive(true);

    if (fingers === 1) {
      this._haptic("selection");
      this._longPressTimer = window.setTimeout(() => {
        this._startTouchDragIfEligible();
      }, Number(this.config.long_press_drag_ms) || 520);
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
      this._clearLongPressTimer();
      this._gesture.fingers = fingers;
      this._gesture.lastX = center.x;
      this._gesture.lastY = center.y;
      this._gesture.dragEligible = false;
      return;
    }

    const rawDx = center.x - this._gesture.lastX;
    const rawDy = center.y - this._gesture.lastY;

    this._gesture.lastX = center.x;
    this._gesture.lastY = center.y;
    this._gesture.totalMove += Math.abs(rawDx) + Math.abs(rawDy);

    if (
      this._gesture.dragEligible &&
      !this._dragActive &&
      this._gesture.totalMove > Number(this.config.drag_start_threshold_px)
    ) {
      this._clearLongPressTimer();
      this._gesture.dragEligible = false;
    }

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

    if (ev.touches.length > 0) {
      return;
    }

    const gesture = this._gesture;

    this._clearLongPressTimer();
    this._stopLoop();
    this._setActive(false);
    this._gesture = null;

    if (this._dragActive) {
      await this._endDrag();
      return;
    }

    const duration = Date.now() - gesture.startTime;
    const moved = gesture.totalMove;
    const fingers = gesture.fingers;

    const threshold =
      fingers === 1
        ? Number(this.config.tap_threshold_px)
        : Number(this.config.multi_tap_threshold_px);

    const maxMs =
      fingers === 1
        ? Number(this.config.tap_max_ms)
        : Number(this.config.multi_tap_max_ms);

    const isTap = duration <= maxMs && moved <= threshold;

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

    this._clearLongPressTimer();
    this._gesture = null;
    this._setActive(false);
    this._stopLoop();

    if (this._dragActive) {
      this._endDrag();
    }
  }

  async _startTouchDragIfEligible() {
    if (!this._gesture) return;
    if (!this._gesture.dragEligible) return;
    if (this._gesture.fingers !== 1) return;
    if (this._dragActive) return;

    if (
      this._gesture.totalMove > Number(this.config.drag_start_threshold_px)
    ) {
      return;
    }

    await this._startDrag();
  }

  async _startDrag() {
    if (this._dragActive || this._dragStartPromise) return this._dragStartPromise;

    this._dragStartPromise = (async () => {
      try {
        await this._ensureArmed(30);
        await this._flushMove();
        await this._callBridge(this.config.service_mouse_down, {
          button: "left",
        });

        this._dragActive = true;
        this._setDragging(true);
        this._haptic("heavy");
      } catch (err) {
        this._handleServiceError(err);
      } finally {
        this._dragStartPromise = null;
      }
    })();

    return this._dragStartPromise;
  }

  async _endDrag() {
    if (!this._dragActive) return;

    try {
      await this._flushMove();
      await this._callBridge(this.config.service_mouse_up, {
        button: "left",
      });
    } catch (err) {
      this._handleServiceError(err);

      try {
        await this._callBridge(this.config.service_release_all, {});
      } catch (_) {}
    } finally {
      this._dragActive = false;
      this._setDragging(false);
      this._haptic("selection");
    }
  }

  async _safeMouseUp() {
    try {
      await this._callBridge(this.config.service_mouse_up, {
        button: "left",
      });
    } catch (_) {
      try {
        await this._callBridge(this.config.service_release_all, {});
      } catch (_) {}
    }
  }

  _pointerDown(ev) {
    if (Date.now() < this._ignorePointerUntil) return;
    if (ev.pointerType === "touch") return;

    ev.preventDefault();

    const pad = this.querySelector("#pad");
    try {
      pad.setPointerCapture(ev.pointerId);
    } catch (_) {}

    this._setActive(true);
    this._pointerDragging = true;
    this._lastX = ev.clientX;
    this._lastY = ev.clientY;
    this._pendingDx = 0;
    this._pendingDy = 0;
    this._haptic("selection");
    this._ensureArmed(30);
    this._startLoop();
  }

  _pointerMove(ev) {
    if (Date.now() < this._ignorePointerUntil) return;
    if (!this._pointerDragging) return;

    ev.preventDefault();

    const rawDx = ev.clientX - this._lastX;
    const rawDy = ev.clientY - this._lastY;

    this._lastX = ev.clientX;
    this._lastY = ev.clientY;

    this._pendingDx += rawDx * this.settings.sensitivity;
    this._pendingDy += rawDy * this.settings.sensitivity;
  }

  async _pointerUp(ev) {
    if (Date.now() < this._ignorePointerUntil) return;
    if (!this._pointerDragging) return;

    ev.preventDefault();

    this._stopLoop();
    this._setActive(false);
    this._pointerDragging = false;
    this._lastX = null;
    this._lastY = null;
  }

  async _ensureArmed(seconds = 30) {
    const now = Date.now();

    if (now < this._armedUntilMs - 2000) {
      return;
    }

    if (!this._armPromise) {
      this._armPromise = this._callBridge(this.config.service_arm, {
        seconds,
        cancel_on_manual_mouse: true,
        manual_mouse_cancel_threshold_px: 8,
        manual_mouse_grace_ms: 250,
      })
        .then(() => {
          this._armedUntilMs = Date.now() + seconds * 1000;
        })
        .catch((err) => {
          this._handleServiceError(err);
        })
        .finally(() => {
          this._armPromise = null;
        });
    }

    await this._armPromise;
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

    try {
      await this._ensureArmed(10);
      await this._callBridge(this.config.service_click, {
        button,
        clicks: 1,
      });
    } catch (err) {
      this._handleServiceError(err);
    }
  }

  async _scroll(amount) {
    this._haptic("selection");

    try {
      await this._ensureArmed(10);
      await this._callBridge(this.config.service_scroll, {
        amount,
      });
    } catch (err) {
      this._handleServiceError(err);
    }
  }

  async _releaseAll() {
    this._clearLongPressTimer();

    try {
      await this._callBridge(this.config.service_release_all, {});
      this._dragActive = false;
      this._setDragging(false);
      this._haptic("success");
      this._setStatus("Mouse buttons released", 1800);
    } catch (err) {
      this._handleServiceError(err);
    }
  }

  async _cancelPlayback() {
    this._clearLongPressTimer();

    try {
      await this._callBridge(this.config.service_cancel, {});
      this._dragActive = false;
      this._setDragging(false);
      this._armedUntilMs = 0;
      this._haptic("warning");
      this._setStatus("Playback cancelled", 1800);
    } catch (err) {
      try {
        await this._callBridge(this.config.service_release_all, {});
        this._setStatus("Cancel failed; mouse released", 2200);
      } catch (_) {
        this._handleServiceError(err);
      }
    }
  }

  async _showBridgeState() {
    try {
      const result = await this._callBridge(this.config.service_state, {});
      const active = Boolean(result.playback_active);
      const armed = Boolean(result.armed);
      const cancelled = Boolean(result.cancelled);
      this._setStatus(
        `State: active=${active}, armed=${armed}, cancelled=${cancelled}`,
        3500
      );
      this._haptic("selection");
    } catch (err) {
      this._handleServiceError(err);
    }
  }

  async _showPosition() {
    try {
      const result = await this._callBridge(this.config.service_position, {});
      this._setStatus(`Position: x=${result.x}, y=${result.y}`, 3500);
      this._haptic("selection");
    } catch (err) {
      this._handleServiceError(err);
    }
  }

  _queueKeyboard(task) {
    const run = async () => {
      try {
        await task();
      } catch (err) {
        this._handleServiceError(err);
      }
    };

    this._keyboardQueue = this._keyboardQueue.then(run, run);
    return this._keyboardQueue;
  }

  async _keyboardWriteNow(text) {
    const safeText = this._sanitizeTextForBridge(text);
    if (!safeText) return;

    await this._ensureArmed(10);
    await this._callBridge(this.config.service_write, {
      text: safeText,
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

    try {
      await this._ensureArmed(10);
      await this._callBridge(this.config.service_hotkey, {
        keys,
      });
    } catch (err) {
      this._handleServiceError(err);
    }
  }

  async _write(text) {
    if (!text) return;

    this._haptic("light");
    return this._queueKeyboard(() => this._keyboardWriteNow(text));
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

  _sanitizeTextForBridge(text) {
    let output = "";

    for (const char of String(text || "")) {
      if (char === "\r" || char === "\n" || char === "\t") {
        output += char;
        continue;
      }

      if (char.length > 1) {
        continue;
      }

      const code = char.charCodeAt(0);

      if (code < 32) {
        continue;
      }

      if (code >= 0xd800 && code <= 0xdfff) {
        continue;
      }

      output += char;
    }

    return output;
  }

  _haptic(pattern = "light") {
    if (!this.settings.haptics) return;

    let hapticType = "light";

    if (typeof pattern === "string") {
      hapticType = pattern;
    } else if (Array.isArray(pattern)) {
      hapticType = "medium";
    } else if (typeof pattern === "number") {
      hapticType =
        pattern >= 40
          ? "heavy"
          : pattern >= 25
          ? "medium"
          : pattern >= 10
          ? "light"
          : "selection";
    }

    const validTypes = [
      "success",
      "warning",
      "failure",
      "light",
      "medium",
      "heavy",
      "selection",
    ];

    if (!validTypes.includes(hapticType)) {
      hapticType = "light";
    }

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

  _handleServiceError(err) {
    const message = String(err && err.message ? err.message : err || "");

    if (
      message.includes("cancelled") ||
      message.includes("409") ||
      message.includes("PlaybackCancelled")
    ) {
      this._armedUntilMs = 0;
      this._dragActive = false;
      this._setDragging(false);
      this._haptic("warning");
      this._setStatus("Playback cancelled", 2500);
      return;
    }

    if (
      message.includes("not armed") ||
      message.includes("423") ||
      message.includes("BridgeNotArmed")
    ) {
      this._armedUntilMs = 0;
      this._setStatus("Bridge is not armed", 2500);
      return;
    }

    this._setStatus("Bridge command failed", 2500);
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