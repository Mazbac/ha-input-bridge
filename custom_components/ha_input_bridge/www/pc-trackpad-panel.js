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
    this._narrow = narrow;
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

  _render() {
    if (this._card) return;

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          background: var(--primary-background-color);
          color: var(--primary-text-color);
          box-sizing: border-box;
        }

        .page {
          box-sizing: border-box;
          min-height: 100vh;
          padding: 16px;
          display: flex;
          justify-content: center;
          align-items: flex-start;
        }

        .shell {
          width: 100%;
          max-width: 720px;
        }

        .header {
          margin-bottom: 12px;
          padding: 0 4px;
        }

        .title {
          font-size: 22px;
          font-weight: 700;
          line-height: 1.2;
        }

        .subtitle {
          margin-top: 4px;
          font-size: 13px;
          opacity: 0.65;
        }

        pc-trackpad-card {
          display: block;
          width: 100%;
        }

        @media (max-width: 600px) {
          .page {
            padding: 8px;
          }

          .header {
            display: none;
          }

          .shell {
            max-width: none;
          }
        }
      </style>

      <div class="page">
        <div class="shell">
          <div class="header">
            <div class="title">PC Trackpad</div>
            <div class="subtitle">HA Input Bridge remote input panel</div>
          </div>

          <pc-trackpad-card></pc-trackpad-card>
        </div>
      </div>
    `;

    this._card = this.shadowRoot.querySelector("pc-trackpad-card");

    this._card.setConfig({
      service_domain: "ha_input_bridge",
      auto_focus_text_after_left_click: false,
      live_type: true,
      haptics: true,
    });

    if (this._hass) {
      this._card.hass = this._hass;
    }

    this._updateLayout();
  }

  _updateLayout() {
    if (!this.shadowRoot) return;

    const page = this.shadowRoot.querySelector(".page");
    if (!page) return;

    if (this._narrow) {
      page.style.padding = "8px";
    } else {
      page.style.padding = "16px";
    }
  }
}

customElements.define("ha-input-bridge-panel", HAInputBridgePanel);
