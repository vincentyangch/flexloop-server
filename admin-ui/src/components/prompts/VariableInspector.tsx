/**
 * Right-sidebar variable inspector.
 *
 * Parses ``{{variable_name}}`` from the current editor buffer and lists
 * them so the admin knows what context the prompt expects. Updates live
 * as the user types (no backend round-trip).
 */
const VAR_RE = /\{\{(\w+)\}\}/g;

function extractVariables(content: string): string[] {
  const seen = new Set<string>();
  for (const match of content.matchAll(VAR_RE)) {
    seen.add(match[1]);
  }
  return [...seen].sort();
}

type Props = {
  content: string;
};

export function VariableInspector({ content }: Props) {
  const variables = extractVariables(content);
  return (
    <div className="border rounded-md p-3 text-sm space-y-2">
      <div className="font-medium">Variables</div>
      {variables.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          No <code>{"{{variables}}"}</code> in this template.
        </p>
      ) : (
        <ul className="space-y-1">
          {variables.map((v) => (
            <li key={v}>
              <code className="text-xs px-1 py-0.5 rounded bg-muted">
                {`{{${v}}}`}
              </code>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
