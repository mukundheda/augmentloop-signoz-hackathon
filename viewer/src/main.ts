import "./styles.css";
import type { PuneMap, RoadMapping } from "./domain";
import { createHud, type HudProgress } from "./hud";
import { parseRaceData } from "./replay";
import { RaceScene, type CameraPreset } from "./scene";

async function loadJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url} (${response.status})`);
  return response.json() as Promise<T>;
}

const INTRO_STORAGE_KEY = "toyworld-intro-dismissed-v1";

function readIntroDismissed(): boolean {
  try {
    return window.localStorage.getItem(INTRO_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeIntroDismissed(): void {
  try {
    window.localStorage.setItem(INTRO_STORAGE_KEY, "1");
  } catch {
    // Private browsing / storage disabled: overlay just reappears next visit, which is fine.
  }
}

/**
 * First-ten-seconds orientation overlay. Shows once per browser (via localStorage)
 * so repeat visitors are not nagged; a small "?" button always re-opens it on demand.
 * Never blocks interaction permanently: dismissible by button, backdrop click, or Escape,
 * and the replay keeps running underneath it the whole time.
 */
function setupIntro(app: HTMLElement): void {
  const overlay = app.querySelector<HTMLElement>("[data-intro-overlay]");
  const helpButton = app.querySelector<HTMLButtonElement>("[data-intro-help]");
  const dismissButton = app.querySelector<HTMLButtonElement>("[data-intro-dismiss]");
  const skipButton = app.querySelector<HTMLButtonElement>("[data-intro-skip]");
  if (!overlay || !helpButton || !dismissButton || !skipButton) return;

  const close = () => {
    overlay.hidden = true;
    writeIntroDismissed();
  };
  const open = () => {
    overlay.hidden = false;
    const card = overlay.querySelector<HTMLElement>(".intro-card");
    if (card) card.scrollTop = 0;
    dismissButton.focus({ preventScroll: true });
  };

  dismissButton.addEventListener("click", close);
  skipButton.addEventListener("click", close);
  helpButton.addEventListener("click", open);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlay.hidden) close();
  });

  if (!readIntroDismissed()) open();
}

async function boot() {
  const app = document.querySelector<HTMLElement>("#app")!;
  app.innerHTML = `
    <main class="shell">
      <section class="viewport" aria-label="3D Pune toy-world road simulation">
        <div class="city-badge"><span>PUNE · OSM ROAD NETWORK</span><b>20-JUNCTION TOY WORLD</b></div>
        <div class="legend">
          <span><i class="active"></i>ACTIVE MODEL</span>
          <span><i class="correct"></i>CORRECT</span>
          <span><i class="wrong"></i>WRONG</span>
          <span><i class="ghost"></i>OPTIMAL GHOST</span>
        </div>
      </section>
      <section class="side-panel"></section>
      <div class="controls">
        <button data-play>▶ PLAY</button>
        <button data-pause>Ⅱ PAUSE</button>
        <button data-restart>↻ RESTART</button>
        <label>SPEED
          <select data-speed>
            <option value=".5">0.5×</option>
            <option value="1" selected>1×</option>
            <option value="2">2×</option>
            <option value="4">4×</option>
          </select>
        </label>
        <label>CAMERA
          <select data-camera>
            <option value="overview">OVERVIEW</option>
            <option value="top">TOP DOWN</option>
            <option value="chase">STREET</option>
            <option value="follow">FOLLOW SELECTED</option>
          </select>
        </label>
      </div>
      <a class="attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>
    </main>
    <button class="intro-help" type="button" data-intro-help title="What am I looking at?" aria-label="Show orientation overlay">?</button>
    <div class="intro-overlay" data-intro-overlay hidden role="dialog" aria-modal="true" aria-labelledby="intro-title">
      <div class="intro-card">
        <div class="eyebrow">FIRST TIME HERE?</div>
        <h1 id="intro-title">You're watching 420 real AI routing decisions replay on actual Pune roads</h1>
        <p class="intro-lede">This is a recorded run, not a live simulation - every agent, route, and dollar figure below already happened once and is being replayed so you can watch it unfold.</p>
        <ul class="intro-list">
          <li><i>AI</i><span>Each moving dot is one AI model answering a routing question. 7 models, 420 decisions total, replaying in waves of 24.</span></li>
          <li><i>3x</i><span><b>Route choice</b> (pick the full path), <b>ETA estimate</b> (guess the fastest travel time), or <b>next hop</b> (pick one road to turn onto) - click any agent to see which, in the drawer on the right.</span></li>
          <li><i>&#9679;</i><span>Routes resolve <span class="intro-dot correct"></span><b>green</b> when the model got it right, <span class="intro-dot wrong"></span><b>red</b> when wrong, with a <span class="intro-dot ghost"></span><b>yellow ghost</b> line showing the optimal path it should have taken.</span></li>
          <li><i>$</i><span>The panel on the right keeps score live: decisions completed, correct rate, total spend, and the number that matters most - <b>cost per correct decision</b>.</span></li>
          <li><i>&#9654;</i><span>PLAY / PAUSE / SPEED / CAMERA controls sit bottom-left. The replay is already running behind this card.</span></li>
        </ul>
        <div class="intro-actions">
          <button type="button" class="intro-skip" data-intro-skip>Skip</button>
          <button type="button" class="intro-dismiss" data-intro-dismiss>GOT IT - WATCH</button>
        </div>
      </div>
    </div>
  `;

  setupIntro(app);

  try {
    const [rawRun, map, roads] = await Promise.all([
      loadJson<unknown>("/data/run.json"),
      loadJson<PuneMap>("/data/pune-map.geojson"),
      loadJson<RoadMapping>("/data/toyworld-roads.json")
    ]);
    const run = parseRaceData(rawRun);
    const viewport = app.querySelector<HTMLElement>(".viewport")!;
    const panel = app.querySelector<HTMLElement>(".side-panel")!;
    const scene = new RaceScene(viewport, map, roads);
    const hud = createHud(panel, run);
    let speed = 1;
    let progress: HudProgress = { completed: 0, correct: 0, cost: 0, wave: 0, waves: 0 };

    const callbacks = {
      onAgent: (agent: typeof run.agents[number]) => hud.showAgent(agent),
      onProgress: (agent: typeof run.agents[number], wave: number, waves: number) => {
        progress = {
          completed: progress.completed + 1,
          correct: progress.correct + Number(agent.is_correct),
          cost: progress.cost + agent.cost_usd,
          wave,
          waves
        };
        hud.update(progress);
      },
      onComplete: () => {
        hud.setState("COMPLETE");
        hud.update({
          completed: run.totals.decisions,
          correct: run.totals.correct,
          cost: run.totals.total_cost_usd,
          wave: Math.ceil(run.agents.length / 24),
          waves: Math.ceil(run.agents.length / 24)
        });
      }
    };

    const play = () => {
      progress = { completed: 0, correct: 0, cost: 0, wave: 0, waves: Math.ceil(run.agents.length / 24) };
      hud.update(progress);
      hud.setState("RUNNING");
      scene.play(run, speed, callbacks);
    };
    app.querySelector("[data-play]")?.addEventListener("click", play);
    app.querySelector("[data-pause]")?.addEventListener("click", () => {
      scene.pause();
      hud.setState("PAUSED");
    });
    app.querySelector("[data-restart]")?.addEventListener("click", play);
    app.querySelector<HTMLSelectElement>("[data-speed]")?.addEventListener("change", (event) => {
      speed = Number((event.target as HTMLSelectElement).value);
      play();
    });
    app.querySelector<HTMLSelectElement>("[data-camera]")?.addEventListener("change", (event) => {
      scene.setCameraPreset((event.target as HTMLSelectElement).value as CameraPreset);
    });
    window.addEventListener("resize", () => scene.resize());
    play();
  } catch (error) {
    app.innerHTML = `
      <div class="fatal">
        <span>VIEWER OFFLINE</span>
        <h1>Road simulation could not be loaded</h1>
        <pre>${error instanceof Error ? error.message : String(error)}</pre>
      </div>
    `;
  }
}

void boot();
