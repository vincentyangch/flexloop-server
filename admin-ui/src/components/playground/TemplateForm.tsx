/**
 * Variable form for template mode in the playground.
 *
 * Given a list of variable names (from the template's {{...}} extraction),
 * renders one text input per variable. Returns the current values via
 * a controlled callback.
 */
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = {
  variables: string[];
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
};

export function TemplateForm({ variables, values, onChange }: Props) {
  if (variables.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        This template has no variables.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {variables.map((v) => (
        <div key={v} className="space-y-1.5">
          <Label htmlFor={`var-${v}`}>{v}</Label>
          <Input
            id={`var-${v}`}
            value={values[v] ?? ""}
            onChange={(e) =>
              onChange({ ...values, [v]: e.target.value })
            }
          />
        </div>
      ))}
    </div>
  );
}
