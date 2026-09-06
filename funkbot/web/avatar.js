/* FunkBot animated avatar.
 *
 *   const av = new FunkAvatar(document.getElementById('avatar'));
 *   av.state = 'thinking';        // idle | listening | thinking | tool | speaking
 *   av.pulse();                   // one-shot flare, e.g. on a tool call
 *
 * Drop a portrait at web/funkbot.png and it fills the ring; without one the
 * built-in cyborg silhouette is used. Pure SVG + CSS — no libraries, no images
 * required, animates at any size.
 */

const NS = 'http://www.w3.org/2000/svg';

const SVG = `
<svg viewBox="0 0 200 200" class="fb-svg" aria-hidden="true">
  <defs>
    <radialGradient id="fb-eye">
      <stop offset="0%"  stop-color="#dfffe9"/>
      <stop offset="35%" stop-color="#2bff9e"/>
      <stop offset="100%" stop-color="#0b5c39"/>
    </radialGradient>
    <linearGradient id="fb-chrome" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%"  stop-color="#cbb8e6"/>
      <stop offset="45%" stop-color="#7a5fa8"/>
      <stop offset="100%" stop-color="#3a2a55"/>
    </linearGradient>
    <filter id="fb-glow" x="-70%" y="-70%" width="240%" height="240%">
      <feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="fb-clip"><circle cx="100" cy="100" r="62"/></clipPath>
  </defs>

  <!-- rotating HUD rings -->
  <g class="fb-rings" fill="none" stroke-linecap="round">
    <circle class="fb-ring fb-ring-a" cx="100" cy="100" r="92"
            stroke-width="2" stroke-dasharray="46 18 8 18"/>
    <circle class="fb-ring fb-ring-b" cx="100" cy="100" r="82"
            stroke-width="1.5" stroke-dasharray="4 10"/>
    <circle class="fb-ring fb-ring-c" cx="100" cy="100" r="72"
            stroke-width="3" stroke-dasharray="30 140"/>
    <circle class="fb-ring-still" cx="100" cy="100" r="66" stroke-width="1"/>
  </g>

  <!-- portrait well -->
  <circle class="fb-well" cx="100" cy="100" r="62"/>
  <g clip-path="url(#fb-clip)">
    <image class="fb-photo" x="38" y="38" width="124" height="124"
           preserveAspectRatio="xMidYMid slice"/>

    <g class="fb-face">
      <!-- flesh-and-beard half (viewer's left) -->
      <path class="fb-skin" d="M64 84c0-18 14-30 36-30v104c-22-6-36-26-36-52z"/>
      <path class="fb-beard"
            d="M66 104c-2 22 4 40 14 52 6 7 13 11 20 12v-72c-13 1-25 4-34 8z"/>
      <path class="fb-beard-hi" d="M78 118c4 18 10 30 22 36"/>
      <rect class="fb-shade" x="63" y="86" width="37" height="14" rx="6"/>
      <path class="fb-shade-hi" d="M67 90h26"/>

      <!-- chrome half (viewer's right) -->
      <path class="fb-chrome" d="M100 54c25 0 41 13 41 32 0 32-12 60-41 66V54z"/>
      <path class="fb-plate" d="M104 60h30v9h-30zM104 112h33v8h-33zM104 126h26v6h-26z"/>
      <path class="fb-seam" d="M100 54v112"/>
      <path class="fb-vent" d="M108 138h22M108 145h18M108 152h13"/>

      <!-- hat: crown then brim, drawn over both halves -->
      <path class="fb-hat" d="M50 74c2-26 22-40 50-40s48 14 50 40c-16-9-32-13-50-13s-34 4-50 13z"/>
      <path class="fb-hat-brim" d="M32 74h136c0 7-6 11-18 11H50c-12 0-18-4-18-11z"/>
      <path class="fb-hat-rim" d="M52 70c14-7 30-10 48-10s34 3 48 10"/>

      <!-- neural cables off the chrome side -->
      <path class="fb-cable" d="M138 68c14-6 22 0 25 12"/>
      <path class="fb-cable" d="M141 82c16-4 23 4 24 16"/>
      <path class="fb-cable" d="M139 96c18 0 25 10 24 22"/>
    </g>
  </g>

  <!-- the eye -->
  <g class="fb-eye" filter="url(#fb-glow)">
    <circle class="fb-eye-outer" cx="121" cy="93" r="13"/>
    <circle class="fb-eye-iris"  cx="121" cy="93" r="8" fill="url(#fb-eye)"/>
    <circle class="fb-eye-core"  cx="121" cy="93" r="3.4"/>
  </g>

  <!-- scan sweep during thinking -->
  <g clip-path="url(#fb-clip)">
    <rect class="fb-scan" x="38" y="0" width="124" height="10"/>
  </g>

  <!-- activity bars -->
  <g class="fb-bars">
    <rect x="76"  y="170" width="5" height="10" rx="2"/>
    <rect x="86"  y="170" width="5" height="10" rx="2"/>
    <rect x="96"  y="170" width="5" height="10" rx="2"/>
    <rect x="106" y="170" width="5" height="10" rx="2"/>
    <rect x="116" y="170" width="5" height="10" rx="2"/>
  </g>
</svg>`;

/* Framing for a portrait dropped into the ring. The source is usually a wide
 * shot, not a square headshot, so these say which part of it fills the circle:
 * zoom 1 fits the whole frame, higher crops in; x/y are the focal point in
 * percent (50/50 = dead center). Override per-avatar via setPhoto(). */
const DEFAULT_FRAME = { zoom: 2.6, x: 52, y: 27 };

export class FunkAvatar {
  constructor(host, { label = true, src = 'funkbot.png', frame = {} } = {}) {
    host.classList.add('fb-avatar');
    host.innerHTML = SVG + (label ? '<div class="fb-label">STANDBY</div>' : '');
    this.host = host;
    this.labelEl = host.querySelector('.fb-label');
    this.imgEl = host.querySelector('.fb-photo');
    this.frame = { ...DEFAULT_FRAME, ...frame };

    this.setPhoto(src);
    this._state = 'idle';
    this.state = 'idle';
  }

  /** Point the ring at a portrait. Falls back to the drawn face if it 404s. */
  setPhoto(src, frame = {}) {
    this.frame = { ...this.frame, ...frame };
    const { zoom, x, y } = this.frame;

    // The clip circle spans 38..162. Scale the image up by `zoom` and slide it
    // so the focal point sits at the circle's center.
    const side = 124 * zoom;
    this.imgEl.setAttribute('width', side);
    this.imgEl.setAttribute('height', side);
    this.imgEl.setAttribute('x', 100 - side * (x / 100));
    this.imgEl.setAttribute('y', 100 - side * (y / 100));

    // Let the glowing eye land on the portrait's own eye.
    if (this.frame.eye) {
      const g = this.host.querySelector('.fb-eye');
      g.setAttribute('transform',
        `translate(${this.frame.eye.x - 121} ${this.frame.eye.y - 93})`);
      g.style.transformOrigin = `${this.frame.eye.x}px ${this.frame.eye.y}px`;
    }

    const probe = new Image();
    probe.onload = () => {
      this.imgEl.setAttribute('href', src);
      this.host.classList.add('has-photo');
    };
    probe.onerror = () => this.host.classList.remove('has-photo');
    probe.src = src + (src.includes('?') ? '&' : '?') + 'v=' + Date.now();
  }

  static LABELS = {
    idle: 'STANDBY', listening: 'LISTENING', thinking: 'PROCESSING',
    tool: 'EXECUTING', speaking: 'TRANSMITTING',
  };

  get state() { return this._state; }

  set state(next) {
    if (next === this._state) return;
    this.host.classList.remove('is-' + this._state);
    this.host.classList.add('is-' + next);
    this._state = next;
    if (this.labelEl) this.labelEl.textContent = FunkAvatar.LABELS[next] || next;
  }

  /** One-shot flare — a tool fired, a message landed. */
  pulse() {
    this.host.classList.remove('fb-flare');
    void this.host.offsetWidth;          // restart the animation
    this.host.classList.add('fb-flare');
  }
}

/* Convenience: <div data-funkbot-avatar></div> auto-mounts. */
export function mountAll() {
  return [...document.querySelectorAll('[data-funkbot-avatar]')]
    .map(el => new FunkAvatar(el));
}
