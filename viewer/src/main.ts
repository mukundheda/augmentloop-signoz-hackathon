import "./styles.css";
import type { FeatureCollection } from "./domain";
import { createHud } from "./hud";
import { buildTimeline, parseRaceData } from "./replay";
import { RaceScene } from "./scene";

async function loadJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not load ${url} (${response.status})`);
  return response.json() as Promise<T>;
}

async function boot() {
  const app = document.querySelector<HTMLElement>("#app")!;
  app.innerHTML = `
    <main class="shell">
      <section class="viewport" aria-label="3D Pune route race">
        <div class="city-badge"><span>PUNE · 18.5204° N</span><b>AI DECISION CORRIDOR</b></div>
        <div class="legend"><span><i class="correct"></i>MATH-CORRECT</span><span><i class="wrong"></i>WRONG</span><span><i class="ghost"></i>FASTEST GHOST</span></div>
      </section>
      <section class="side-panel"></section>
      <div class="controls">
        <button data-play>▶ PLAY</button>
        <button data-restart>↻ RESTART</button>
        <button data-camera>⌖ RESET VIEW</button>
        <label>SPEED <select data-speed><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label>
      </div>
      <a class="attribution" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>
    </main>
  `;

  try {
    const [rawRun, world, context] = await Promise.all([
      loadJson<unknown>("/data/run.json"),
      loadJson<FeatureCollection>("/data/world.geojson"),
      loadJson<FeatureCollection>("/data/pune-context.geojson")
    ]);
    const run = parseRaceData(rawRun);
    const viewport = app.querySelector<HTMLElement>(".viewport")!;
    const panel = app.querySelector<HTMLElement>(".side-panel")!;
    const scene = new RaceScene(viewport, world, context, run);
    const hud = createHud(panel, run);
    const timeline = buildTimeline(run);
    let timers: number[] = [];
    let speed = 1;

    const stop = () => {
      timers.forEach(clearTimeout);
      timers = [];
    };
    const play = () => {
      stop();
      hud.setState("RUNNING");
      timeline.forEach((event) => {
        timers.push(window.setTimeout(() => {
          hud.apply(event);
          scene.apply(event);
        }, event.at / speed));
      });
    };
    app.querySelector("[data-play]")?.addEventListener("click", play);
    app.querySelector("[data-restart]")?.addEventListener("click", play);
    app.querySelector("[data-camera]")?.addEventListener("click", () => scene.resetCamera());
    app.querySelector<HTMLSelectElement>("[data-speed]")?.addEventListener("change", (event) => {
      speed = Number((event.target as HTMLSelectElement).value);
      play();
    });
    window.addEventListener("resize", () => scene.resize());
    play();
  } catch (error) {
    app.innerHTML = `<div class="fatal"><span>VIEWER OFFLINE</span><h1>Race data could not be loaded</h1><pre>${error instanceof Error ? error.message : String(error)}</pre></div>`;
  }
}

void boot();
