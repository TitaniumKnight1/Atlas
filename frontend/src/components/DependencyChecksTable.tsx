import { Badge } from "./Badge";
import { EmptyState } from "./StateViews";
import type { DependencyCheck } from "../api/setup";

const DEV_DB_CHECK_KEYS = new Set(["docker_available", "dev_db_port_available", "dev_db_reachable"]);

export interface DependencyChecksTableProps {
  checks: DependencyCheck[];
  emptyDetail?: string;
}

export function DependencyChecksTable({
  checks,
  emptyDetail = "Run checks to record preflight results for this project."
}: DependencyChecksTableProps) {
  if (checks.length === 0) {
    return <EmptyState detail={emptyDetail} title="No dependency checks yet" />;
  }

  return (
    <div className="atlas-table-wrap">
      <table className="atlas-table">
        <thead>
          <tr>
            <th>Check</th>
            <th>Category</th>
            <th>Status</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((check) => (
            <tr key={check.dependency_check_id ?? check.check_key}>
              <td>
                <span className="atlas-row">
                  {check.check_key}
                  {DEV_DB_CHECK_KEYS.has(check.check_key) ? (
                    <Badge variant="neutral">dev DB</Badge>
                  ) : null}
                </span>
              </td>
              <td>{check.category}</td>
              <td>{check.status}</td>
              <td>{check.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
