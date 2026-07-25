import type { RaceRun } from "./domain";
import type { ReplayEvent } from "./replay";

export interface Hud {
  element: HTMLElement;
  apply(event: ReplayEvent): void;
  setState(label: string): void;
}

const usd = (value: number | null) => value === null ? "—" : `$${value.toFixed(6)}`;
const shortModel = (model: string) => model.split("/").at(-1)?.replaceAll("-", " ") ?? model;

export function createHud(parent: HTMLElement, run: RaceRun): Hud {
  const hud = document.createElement("aside");
  hud.className = "hud";
  hud.innerHTML = `
    <div class="eyebrow">GRADEBOOK · LIVE REPLAY</div>
    <div class="hud-title-row">
      <div>
        <h1>PUNE MODEL RACE</h1>
        <p>Shivajinagar → Deccan → Swargate</p>
      </div>
      <span class="live-pill"><i></i><span data-state>READY</span></span>
    </div>
    <div class="metrics">
      <div><span>DECISIONS</span><strong data-decisions>0/${run.totals.decisions}</strong></div>
      <div><span>CORRECT</span><strong data-correct>0</strong></div>
      <div><span>TOTAL COST</span><strong data-cost>$0.000000</strong></div>
      <div class="hero-metric"><span>COST / CORRECT</span><strong data-cpc>—</strong></div>
    </div>
    <div class="driver-list">
      ${run.drivers.map((driver) => `
        <article class="driver-row" data-driver-id="${driver.id}">
          <span class="driver-dot" style="--driver:${driver.color}"></span>
          <div class="driver-copy">
            <strong>${driver.id.toUpperCase()}</strong>
            <span>${shortModel(driver.model)}</span>
          </div>
          <div class="driver-score"><b data-driver-score>0/0</b><span data-driver-status>STAGED</span></div>
        </article>
      `).join("")}
    </div>
    <div class="event-log" data-event-log>
      <span>WAITING FOR REPLAY</span>
    </div>
  `;
  parent.appendChild(hud);

  const driverProgress = new Map<string, { decisions: number; correct: number }>();
  const setState = (label: string) => {
    const state = hud.querySelector<HTMLElement>("[data-state]");
    if (state) state.textContent = label;
  };

  return {
    element: hud,
    setState,
    apply(event) {
      const decisions = hud.querySelector<HTMLElement>("[data-decisions]");
      const correct = hud.querySelector<HTMLElement>("[data-correct]");
      const cost = hud.querySelector<HTMLElement>("[data-cost]");
      const cpc = hud.querySelector<HTMLElement>("[data-cpc]");
      if (decisions) decisions.textContent = `${event.totals.decisions}/${run.totals.decisions}`;
      if (correct) correct.textContent = String(event.totals.correct);
      if (cost) cost.textContent = usd(event.totals.totalCostUsd);
      if (cpc) cpc.textContent = usd(event.totals.costPerCorrectUsd);

      let message = "RACE INITIALIZED";
      if (event.kind === "decision") {
        const progress = driverProgress.get(event.driverId) ?? { decisions: 0, correct: 0 };
        progress.decisions += 1;
        progress.correct += Number(event.decision.correct);
        driverProgress.set(event.driverId, progress);
        const row = hud.querySelector<HTMLElement>(`[data-driver-id="${event.driverId}"]`);
        const score = row?.querySelector<HTMLElement>("[data-driver-score]");
        const status = row?.querySelector<HTMLElement>("[data-driver-status]");
        if (score) score.textContent = `${progress.correct}/${progress.decisions}`;
        if (status) {
          status.textContent = `${event.decision.junction} · ${event.decision.chosen}`;
          status.className = event.decision.correct ? "good" : "bad";
        }
        message = `${event.driverId} chose ${event.decision.chosen} at ${event.decision.junction} · ${event.decision.correct ? "MATH-CORRECT" : `WRONG · FASTEST ${event.decision.true_fastest}`}`;
      } else if (event.kind === "outcome") {
        message = `REALITY GRADE → ${event.driverId} · ${event.decision.junction} · ${event.onTime ? "ON TIME" : "LATE"}`;
      } else if (event.kind === "complete") {
        message = "REPLAY COMPLETE · EVIDENCE RECONCILED";
        setState("COMPLETE");
      } else if (event.kind === "start") {
        setState("RUNNING");
      }
      const log = hud.querySelector<HTMLElement>("[data-event-log]");
      if (log) log.innerHTML = `<span>${message}</span>`;
    }
  };
}
