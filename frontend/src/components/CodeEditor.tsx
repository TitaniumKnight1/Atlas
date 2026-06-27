import type { TextareaHTMLAttributes } from "react";

interface CodeEditorProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  note?: string;
}

export function CodeEditor({ label, note, className, ...props }: CodeEditorProps) {
  return (
    <div className="atlas-code-editor">
      {label ? <p className="eyebrow">{label}</p> : null}
      {note ? <p className="muted-copy atlas-code-editor__note">{note}</p> : null}
      <textarea
        className={["atlas-textarea atlas-code-editor__area", className ?? ""].filter(Boolean).join(" ")}
        spellCheck={false}
        {...props}
      />
    </div>
  );
}
