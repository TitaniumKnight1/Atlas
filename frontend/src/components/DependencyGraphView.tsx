import type { GraphEdge, GraphFinding } from "../api/resources";
import { Alert, Badge } from ".";

interface DependencyGraphViewProps {
  nodes: string[];
  edges: GraphEdge[];
  findings: GraphFinding[];
  topologicalOrder: string[] | null;
  isHealthy: boolean;
  selectedNode?: string | null;
  onSelectNode?: (node: string) => void;
}

const NODE_WIDTH = 120;
const NODE_HEIGHT = 36;
const H_GAP = 48;
const V_GAP = 56;
const PAD = 24;

export function DependencyGraphView({
  nodes,
  edges,
  findings,
  topologicalOrder,
  isHealthy,
  selectedNode,
  onSelectNode
}: DependencyGraphViewProps) {
  const layout = buildLayout(nodes, topologicalOrder);
  const width = Math.max(320, PAD * 2 + layout.columns * (NODE_WIDTH + H_GAP) - H_GAP);
  const height = Math.max(180, PAD * 2 + layout.rows * (NODE_HEIGHT + V_GAP) - V_GAP);

  return (
    <div className="dependency-graph">
      <div className="atlas-row" style={{ justifyContent: "space-between" }}>
        <p className="muted-copy">Dependency graph (requires → provider). Findings surface cycles, missing deps, and conflicts.</p>
        <Badge variant={isHealthy ? "success" : "danger"}>{isHealthy ? "Healthy" : "Issues detected"}</Badge>
      </div>

      {findings.length > 0 ? (
        <div className="atlas-stack">
          {findings.map((finding, index) => (
            <Alert key={`${finding.finding_type}-${index}`} severity={finding.severity === "error" ? "danger" : "warn"} title={finding.finding_type}>
              {finding.message}
              {finding.nodes.length > 0 ? ` — nodes: ${finding.nodes.join(", ")}` : ""}
            </Alert>
          ))}
        </div>
      ) : null}

      {nodes.length === 0 ? (
        <p className="muted-copy">No resources in the graph yet. Scan or install resources to populate dependencies.</p>
      ) : (
        <svg aria-label="Resource dependency graph" className="dependency-graph__svg" height={height} role="img" viewBox={`0 0 ${width} ${height}`} width="100%">
          <defs>
            <marker id="dep-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="6" refY="4">
              <path d="M0,0 L8,4 L0,8 Z" fill="var(--atlas-text-faint)" />
            </marker>
          </defs>
          {edges.map((edge, index) => {
            const source = layout.positions[edge.source];
            const target = layout.positions[edge.target];
            if (!source || !target) {
              return null;
            }
            const x1 = source.x + NODE_WIDTH / 2;
            const y1 = source.y + NODE_HEIGHT;
            const x2 = target.x + NODE_WIDTH / 2;
            const y2 = target.y;
            return (
              <line
                key={`${edge.source}-${edge.target}-${index}`}
                markerEnd="url(#dep-arrow)"
                stroke="var(--atlas-border-strong)"
                strokeWidth="1.5"
                x1={x1}
                x2={x2}
                y1={y1}
                y2={y2}
              />
            );
          })}
          {nodes.map((node) => {
            const pos = layout.positions[node];
            if (!pos) {
              return null;
            }
            const active = selectedNode === node;
            return (
              <g key={node} onClick={() => onSelectNode?.(node)} style={{ cursor: onSelectNode ? "pointer" : "default" }}>
                <rect
                  fill={active ? "var(--atlas-accent-soft)" : "var(--atlas-surface-2)"}
                  height={NODE_HEIGHT}
                  rx="8"
                  stroke={active ? "var(--atlas-accent-border)" : "var(--atlas-border-subtle)"}
                  strokeWidth={active ? 2 : 1}
                  width={NODE_WIDTH}
                  x={pos.x}
                  y={pos.y}
                />
                <text
                  dominantBaseline="middle"
                  fill="var(--atlas-text-strong)"
                  fontFamily="var(--font-mono)"
                  fontSize="11"
                  textAnchor="middle"
                  x={pos.x + NODE_WIDTH / 2}
                  y={pos.y + NODE_HEIGHT / 2}
                >
                  {truncate(node, 14)}
                </text>
              </g>
            );
          })}
        </svg>
      )}

      {topologicalOrder && topologicalOrder.length > 0 ? (
        <p className="muted-copy">
          Safe start order: {topologicalOrder.join(" → ")}
        </p>
      ) : null}
    </div>
  );
}

function buildLayout(nodes: string[], topologicalOrder: string[] | null) {
  const ordered = topologicalOrder && topologicalOrder.length > 0 ? topologicalOrder.filter((node) => nodes.includes(node)) : [...nodes].sort();
  const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(ordered.length))));
  const positions: Record<string, { x: number; y: number }> = {};
  ordered.forEach((node, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    positions[node] = {
      x: PAD + col * (NODE_WIDTH + H_GAP),
      y: PAD + row * (NODE_HEIGHT + V_GAP)
    };
  });
  const rows = Math.max(1, Math.ceil(ordered.length / columns));
  return { positions, columns, rows };
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}
