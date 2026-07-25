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
  `;

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
