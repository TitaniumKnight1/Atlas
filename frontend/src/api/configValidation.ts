export type ConfigFindingType =
  | "DANGLING_RESOURCE_REFERENCE"
  | "MISSING_MANIFEST"
  | "ABSOLUTE_PATH"
  | "INLINE_SECRET";

export type StructuralValidationStatus = "not_run" | "validated" | "skipped_no_server_cfg";

export interface ConfigFindingRemediation {
  auto_fix_available: boolean;
  auto_fix_kind?: string | null;
  prompt_exportable: boolean;
  requires_confirmation?: boolean;
}

export interface ConfigFinding {
  finding_id: string;
  type: ConfigFindingType;
  severity: string;
  path: string;
  line: number | null;
  message: string;
  remediation: ConfigFindingRemediation;
  context: Record<string, unknown>;
}

export interface ConfigValidationBlock {
  status: StructuralValidationStatus;
  finding_count: number;
  server_cfg_path: string | null;
  findings: ConfigFinding[];
  prompts_available?: boolean;
  fix_prompts?: Record<string, string>;
  all_issues_prompt?: string;
}

export function formatFindingLocation(finding: ConfigFinding): string {
  return finding.line != null ? `${finding.path}:${finding.line}` : finding.path;
}

export function findingTypeLabel(type: ConfigFindingType): string {
  switch (type) {
    case "DANGLING_RESOURCE_REFERENCE":
      return "Dangling resource";
    case "MISSING_MANIFEST":
      return "Missing manifest";
    case "ABSOLUTE_PATH":
      return "Absolute path";
    case "INLINE_SECRET":
      return "Inline secret";
    default:
      return type;
  }
}
