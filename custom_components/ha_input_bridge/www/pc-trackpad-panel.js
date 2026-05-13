import "./pc-trackpad-card.js";

class HAInputBridgePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });

    this._hass = null;
    this._narrow = false;
    this._route = null;
    this._panel = null;
    this._card = null;
  }

  set hass(hass) {
    this._hass = hass;

    if (this._card) {
      this._card.hass = hass;
    }
  }

  set narrow(narrow) {
    this._narrow = Boolean(narrow);
    this._updateLayout();
  }

  set route(route) {
    this._route = route;
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    this._render();
  }

  disconnectedCallback() {
    if (this._card && typeof this._card.disconnectedCallback === "function") {
      this._card.disconnectedCallback();
    }
  }

  _render() {
    if (this._card) {
      return;
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          background: var(--primary-background-color);
          color: var(--primary-text-color);
        }

        .page {
          box-sizing: border-box;
          width: 100%;
          max-width: 980px;
          margin: 0 auto;
          padding: 16px;
        }

        .header {
          margin: 4px 0 14px;
        }

        .title {
          font-size: 24px;
          font-weight: 650;
          line-height: 1.2;
        }

        .subtitle {
          margin-top: 4px;
          color: var(--secondary-text-color);
          font-size: 14px;
        }

        .safety {
          margin-bottom: 14px;
          padding: 12px 14px;
          border-radius: 14px;
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          font-size: 13px;
          line-height: 1.45;
        }

        .safety strong {
          font-weight: 650;
        }

        pc-trackpad-card {
          display: block;
        }

        @media (max-width: 520px) {
          .page {
            padding: 8px;
          }

          .title {
            font-size: 21px;
          }

          .safety {
            font-size: 12px;
          }
        }
      </style>

      <div class="page">
        <div class="header">
          <div class="title">PC Trackpad</div>
          <div class="subtitle">HA Input Bridge remote input panel</div>
        </div>

        <div class="safety">
          <strong>Safety:</strong>
          use <em>Cancel playback</em> when a script should stop,
          and <em>Release mouse</em> if a drag ever gets stuck.
        </div>

        <pc-trackpad-card></pc-trackpad-card>
      </div>
    `;

    this._card = this.shadowRoot.querySelector("pc-trackpad-card");

    this._card.setConfig({
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

      sensitivity: 2.8,
      frame_ms: 12,
      max_step: 650,

      scroll_gain: 3.2,
      scroll_max_step: 220,

      tap_max_ms: 320,
      multi_tap_max_ms: 420,
      tap_threshold_px: 14,
      multi_tap_threshold_px: 36,

      long_press_drag_ms: 520,
      drag_start_threshold_px: 28,

      auto_focus_text_after_left_click: false,
      clear_text_on_auto_focus: true,
      live_type: true,
      haptics: true,
    });

    if (this._hass) {
      this._card.hass = this._hass;
    }

    this._updateLayout();
  }

  _updateLayout() {
    if (!this.shadowRoot) {
      return;
    }

    const page = this.shadowRoot.querySelector(".page");

    if (!page) {
      return;
    }

    page.style.padding = this._narrow ? "8px" : "16px";
  }
}

customElements.define("ha-input-bridge-panel", HAInputBridgePanel);