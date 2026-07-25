import type { AgentDecision, AgentSpan, SigNozConfig } from "./domain";
import {
  buildSigNozLinks,
  filterLogs,
  spanTree
} from "./observability";

type InspectorTab = "details" | "trace" | "logs";
type LogFilter = "all" | "warnings-errors" | "selected-span";

export interface AgentInspector {
  show(agent: AgentDecision): void;
  selectTab(tab: InspectorTab): void;
  destroy(): void;
}

type LinkSet = {
  trace?: string;
  logs?: string;
  dashboard?: string;
  traceSearch?: string;
};

const typeLabel: Record<string, string> = {
  route_choice: "ROUTE CHOICE",
  eta_estimate: "ETA ESTIMATE",
  next_hop: "NEXT HOP"
};

const esc = (value: unknown) => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#39;");

const duration = (value: number) => value < 1 ? `${(value * 1000).toFixed(0)}µs` : `${value.toFixed(value < 10 ? 2 : 1)}ms`;
const severityClass = (severity: string) => severity.toLowerCase().replace(/[^a-z]/g, "");

export function createInspector(host: HTMLElement, config: SigNozConfig): AgentInspector {
  let agent: AgentDecision | undefined;
  let tab: InspectorTab = "details";
  let logFilter: LogFilter = "all";
  let selectedSpanId: string | undefined;
  let destroyed = false;

  const selectTab = (next: InspectorTab) => {
    if (destroyed || !agent) return;
    tab = next;
    render();
  };

  const copy = async (value: string, label: string) => {
    const live = host.querySelector<HTMLElement>("[data-copy-status]");
    try {
      await navigator.clipboard.writeText(value);
      if (live) live.textContent = `${label} copied`;
    } catch {
      if (live) live.textContent = `Could not copy ${label.toLowerCase()}`;
    }
  };

  const details = (current: AgentDecision, links: LinkSet) => {
    const source = current.observability.mode === "signoz" ? "SIGNOZ SYNCHRONIZED" : "REPLAY EVIDENCE";
    const fallback = links.traceSearch;
    return `
      <div class="inspector-evidence">
        <span class="evidence-badge ${current.observability.mode}">${source}</span>
        ${links.dashboard ? externalLink(links.dashboard, "Open dashboard in SigNoz") : ""}
      </div>
      <dl class="inspector-details">
        <div><dt>RESPONSE ID</dt><dd><code>${esc(current.response_id)}</code><button class="copy-button" type="button" data-copy-response-id>Copy</button></dd></div>
        <div><dt>DECISION</dt><dd>${typeLabel[current.decision_type]}</dd></div>
        <div><dt>MODEL</dt><dd>${esc(current.model.split("/").at(-1) ?? current.model)}</dd></div>
        <div><dt>GRADE</dt><dd class="${current.is_correct ? "good" : "bad"}">${current.is_correct ? "CORRECT" : "INCORRECT"}</dd></div>
        <div><dt>CHOICE</dt><dd>${esc(current.chosen)} <span class="detail-muted">/ expected ${esc(current.correct_answer)}</span></dd></div>
        <div><dt>COST</dt><dd>$${current.cost_usd.toFixed(6)}</dd></div>
      </dl>
      <div class="inspector-actions">
        ${links.trace ? externalLink(links.trace, "Open trace in SigNoz") : ""}
        ${links.logs ? externalLink(links.logs, "Open logs in SigNoz") : ""}
        ${fallback ? externalLink(fallback, "Find by response ID in SigNoz") : "<span class=\"fallback-hint\">Find by response ID in SigNoz</span>"}
      </div>
    `;
  };

  const trace = (current: AgentDecision, links: LinkSet) => {
    const rows: Array<{ span: AgentSpan; depth: number }> = [];
    const visit = (nodes: ReturnType<typeof spanTree>, depth: number) => {
      nodes.forEach((node) => {
        rows.push({ span: node.span, depth });
        visit(node.children, depth + 1);
      });
    };
    visit(spanTree(current.observability.spans), 0);
    const tree = rows.map(({ span, depth }) => `
      <button class="span-row" type="button" data-span-id="${esc(span.span_id)}" style="--depth:${depth}" aria-pressed="${selectedSpanId === span.span_id}">
        <span class="span-branch" aria-hidden="true"></span>
        <span class="span-name">${esc(span.name)}</span>
        <span class="span-source">${esc(span.source)}</span>
        <span class="span-status ${esc(span.status).toLowerCase()}">${esc(span.status)}</span>
        <span class="span-duration">${duration(span.duration_ms)}</span>
        ${span.linked_span_ids.length ? "<span class=\"reality-link\">REALITY GRADE LINK</span>" : ""}
      </button>
    `).join("");
    return `
      <div class="trace-actions">
        ${links.trace ? externalLink(links.trace, "Open trace in SigNoz") : "<span>Replay projection · no exact trace</span>"}
        ${current.observability.trace_id ? `<button class="copy-button" type="button" data-copy-trace-id>Copy trace ID</button>` : ""}
      </div>
      <div class="span-waterfall" aria-label="Trace span waterfall">${tree || "<p class=\"empty-state\">No spans captured for this decision.</p>"}</div>
    `;
  };

  const logs = (current: AgentDecision, links: LinkSet) => {
    const entries = filterLogs(current.observability.logs, logFilter, selectedSpanId);
    const empty = current.observability.mode === "signoz"
      ? "No trace-correlated logs returned by SigNoz"
      : "No replay logs projected for this decision";
    return `
      <div class="log-toolbar" aria-label="Log filters">
        ${(["all", "warnings-errors", "selected-span"] as const).map((filter) => `
          <button type="button" data-log-filter="${filter}" aria-pressed="${logFilter === filter}">${filter === "all" ? "All" : filter === "warnings-errors" ? "Warnings & errors" : "Selected span"}</button>
        `).join("")}
        ${links.logs ? externalLink(links.logs, "Open logs in SigNoz") : ""}
      </div>
      <div class="log-list">${entries.length ? entries.map((log) => `
        <article class="log-entry">
          <span class="log-severity ${severityClass(log.severity)}">${esc(log.severity)}</span>
          <p>${esc(log.body)}</p>
          <small>${esc(log.source)}${log.span_id ? ` · ${esc(log.span_id)}` : ""}</small>
        </article>
      `).join("") : `<p class="empty-state">${empty}</p>`}</div>
    `;
  };

  const render = () => {
    if (destroyed || !agent) return;
    const links = buildSigNozLinks(config, agent) as LinkSet;
    const panelId = "agent-observability-panel";
    const content = tab === "details" ? details(agent, links) : tab === "trace" ? trace(agent, links) : logs(agent, links);
    host.innerHTML = `
      <section class="agent-inspector" aria-label="Selected agent observability">
        <div class="inspector-header">
          <div><span>SELECTED AGENT</span><h2>${esc(agent.agent_id.toUpperCase())}</h2></div>
          <span class="agent-result ${agent.is_correct ? "good" : "bad"}">${agent.is_correct ? "CORRECT" : "WRONG"}</span>
        </div>
        <div class="inspector-tabs" role="tablist" aria-label="Agent observability">
          ${(["details", "trace", "logs"] as const).map((item) => `
            <button type="button" role="tab" id="agent-tab-${item}" data-tab="${item}" aria-selected="${tab === item}" aria-controls="${panelId}">${item.toUpperCase()}</button>
          `).join("")}
        </div>
        <div id="${panelId}" role="tabpanel" aria-labelledby="agent-tab-${tab}" class="inspector-panel">${content}</div>
        <p class="copy-status" data-copy-status aria-live="polite"></p>
      </section>
    `;
    host.querySelectorAll<HTMLButtonElement>("[data-tab]").forEach((button) => button.addEventListener("click", () => selectTab(button.dataset.tab as InspectorTab)));
    host.querySelectorAll<HTMLButtonElement>("[data-span-id]").forEach((button) => button.addEventListener("click", () => {
      selectedSpanId = button.dataset.spanId;
      tab = "trace";
      render();
    }));
    host.querySelectorAll<HTMLButtonElement>("[data-log-filter]").forEach((button) => button.addEventListener("click", () => {
      logFilter = button.dataset.logFilter as LogFilter;
      tab = "logs";
      render();
    }));
    host.querySelector<HTMLButtonElement>("[data-copy-response-id]")?.addEventListener("click", () => void copy(agent!.response_id, "Response ID"));
    host.querySelector<HTMLButtonElement>("[data-copy-trace-id]")?.addEventListener("click", () => {
      if (agent?.observability.trace_id) void copy(agent.observability.trace_id, "Trace ID");
    });
  };

  return {
    show(next) {
      if (destroyed) return;
      agent = next;
      tab = "details";
      logFilter = "all";
      selectedSpanId = undefined;
      render();
    },
    selectTab,
    destroy() {
      destroyed = true;
      host.replaceChildren();
    }
  };
}

function externalLink(url: string, label: string): string {
  return `<a class="inspector-link" href="${esc(url)}" target="_blank" rel="noreferrer">${label}</a>`;
}
