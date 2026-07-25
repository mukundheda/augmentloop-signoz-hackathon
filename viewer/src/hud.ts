import type { AgentDecision, CoverageState, RaceRun, SigNozConfig } from "./domain";
import { createInspector, type AgentInspector } from "./inspector";

export interface HudProgress {
  completed: number;
  correct: number;
  cost: number;
  wave: number;
  waves: number;
}

export interface Hud {
  element: HTMLElement;
  update(progress: HudProgress): void;
  showAgent(agent: AgentDecision): void;
  setState(state: string): void;
  setCoverage(coverage: CoverageState): void;
}

const usd = (value: number | null) => value === null ? "—" : `$${value.toFixed(6)}`;
const pct = (part: number, total: number) => total ? `${((part / total) * 100).toFixed(1)}%` : "—";
const typeLabel: Record<string, string> = {
  route_choice: "ROUTE CHOICE",
  eta_estimate: "ETA ESTIMATE",
  next_hop: "NEXT HOP"
};

const fallbackConfig: SigNozConfig = {
  signoz_origin: null,
  dashboard_path: null,
  service_names: []
};

export function createHud(parent: HTMLElement, run: RaceRun, config: SigNozConfig = fallbackConfig): Hud {
  const models = Object.entries(run.totals.by_model);
  const hud = document.createElement("aside");
  hud.className = "hud";
  hud.innerHTML = `
    <div class="eyebrow">GRADEBOOK · TOY WORLD / PUNE</div>
    <div class="hud-title-row">
      <div><h1>AGENT ROAD NETWORK</h1><p>20 junctions · 180 decisions · real road geometry</p></div>
      <div class="hud-statuses"><span class="coverage-pill offline" data-coverage>REPLAY MODE · SIGNOZ OFFLINE</span><span class="live-pill"><i></i><span data-state>READY</span></span></div>
    </div>
    <div class="metrics">
      <div><span>DECISIONS</span><strong data-decisions>0/${run.totals.decisions}</strong></div>
      <div><span>CORRECT RATE</span><strong data-rate>0.0%</strong></div>
      <div><span>TOTAL COST</span><strong data-cost>$0.000000</strong></div>
      <div class="hero-metric"><span>COST / CORRECT</span><strong data-cpc>—</strong></div>
    </div>
    <div class="wave-line"><span>ACTIVE WAVE</span><b data-wave>0/0</b></div>
    <div class="type-grid">
      ${(["route_choice", "eta_estimate", "next_hop"] as const).map((type) => `
        <div data-type="${type}"><span>${typeLabel[type]}</span><b>${run.totals.by_type[type] ?? 0}</b></div>
      `).join("")}
    </div>
    <div class="model-list">
      ${models.map(([model, count]) => `
        <div><span class="model-swatch" style="--model:${run.agents.find((agent) => agent.model === model)?.color ?? "#fff"}"></span><span>${model.split("/").at(-1)}</span><b>${count}</b></div>
      `).join("")}
    </div>
    <section class="agent-drawer" data-agent-drawer>
      <div class="drawer-empty">SELECT OR HOVER AN AGENT</div>
    </section>
    <div class="event-log" data-event-log>MAP READY · WAITING FOR REPLAY</div>
  `;
  parent.appendChild(hud);

  const find = (selector: string) => hud.querySelector<HTMLElement>(selector);
  const drawer = find("[data-agent-drawer]");
  const inspector: AgentInspector | undefined = drawer ? createInspector(drawer, config) : undefined;
  return {
    element: hud,
    setState(state) {
      const target = find("[data-state]");
      if (target) target.textContent = state;
    },
    setCoverage(coverage) {
      const target = find("[data-coverage]");
      if (!target) return;
      target.textContent = coverage.kind === "connected"
        ? `SIGNOZ CONNECTED · ${coverage.matched}/${coverage.total}`
        : coverage.kind === "partial"
          ? `SIGNOZ PARTIAL · ${coverage.matched}/${coverage.total}`
          : "REPLAY MODE · SIGNOZ OFFLINE";
      target.className = `coverage-pill ${coverage.kind}`;
    },
    update(progress) {
      const decisions = find("[data-decisions]");
      const rate = find("[data-rate]");
      const cost = find("[data-cost]");
      const cpc = find("[data-cpc]");
      const wave = find("[data-wave]");
      if (decisions) decisions.textContent = `${progress.completed}/${run.totals.decisions}`;
      if (rate) rate.textContent = pct(progress.correct, progress.completed);
      if (cost) cost.textContent = usd(progress.cost);
      if (cpc) cpc.textContent = usd(progress.correct ? progress.cost / progress.correct : null);
      if (wave) wave.textContent = `${progress.wave}/${progress.waves}`;
    },
    showAgent(agent) {
      inspector?.show(agent);
      const log = find("[data-event-log]");
      if (log) log.textContent = `${agent.agent_id} · ${typeLabel[agent.decision_type]} · ${agent.is_correct ? "CORRECT" : "WRONG"}`;
    }
  };
}
