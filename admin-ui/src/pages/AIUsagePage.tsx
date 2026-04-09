/**
 * AI Usage dashboard.
 *
 * Replaces the phase-2 CRUD shell with a read-oriented dashboard:
 * - Stat cards for the current month's totals
 * - 12-month stacked bar chart of input/output tokens
 * - Filterable, sortable per-user-per-month table
 *
 * Cost is computed at read time on the server using settings.ai_model.
 * Unknown models show "—" - the UI never pretends to know.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type StatsResponse = components["schemas"]["StatsResponse"];
type PricingDbEntry = components["schemas"]["PricingDbEntry"];
type PricingListResponse = components["schemas"]["PricingListResponse"];
type UsageRow = components["schemas"]["UsageRow"];

type SortKey =
  | "month"
  | "user_id"
  | "input_tokens"
  | "output_tokens"
  | "call_count"
  | "estimated_cost";

type SortDir = "asc" | "desc";

const chartConfig = {
  input_tokens: {
    label: "Input",
    color: "var(--chart-1)",
  },
  output_tokens: {
    label: "Output",
    color: "var(--chart-2)",
  },
} satisfies ChartConfig;

const SANITY_THRESHOLD = 1_000;

function formatCost(cost: number | null | undefined): string {
  if (cost === null || cost === undefined) return "—";
  if (cost === 0) return "$0.00";
  if (cost < 0.01) return "<$0.01";
  return `$${cost.toFixed(2)}`;
}

function formatTokens(value: number): string {
  return value.toLocaleString("en-US");
}

function formatAxisTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(value);
}

function sortRows(rows: UsageRow[], sortKey: SortKey, sortDir: SortDir): UsageRow[] {
  return [...rows].sort((leftRow, rightRow) => {
    const left = leftRow[sortKey];
    const right = rightRow[sortKey];

    if (left === null && right === null) return 0;
    if (left === null) return sortDir === "asc" ? 1 : -1;
    if (right === null) return sortDir === "asc" ? -1 : 1;

    if (typeof left === "number" && typeof right === "number") {
      return sortDir === "asc" ? left - right : right - left;
    }

    const leftValue = String(left);
    const rightValue = String(right);
    return sortDir === "asc"
      ? leftValue.localeCompare(rightValue)
      : rightValue.localeCompare(leftValue);
  });
}

export function AIUsagePage() {
  const queryClient = useQueryClient();
  const [monthFrom, setMonthFrom] = useState("");
  const [monthTo, setMonthTo] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("month");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [pricingOpen, setPricingOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<PricingDbEntry | "new" | null>(null);
  const [editName, setEditName] = useState("");
  const [editInput, setEditInput] = useState("");
  const [editOutput, setEditOutput] = useState("");
  const [editCacheRead, setEditCacheRead] = useState("");
  const [editCacheWrite, setEditCacheWrite] = useState("");

  const statsQuery = useQuery({
    queryKey: [
      "admin",
      "ai",
      "usage",
      "stats",
      { month_from: monthFrom, month_to: monthTo, user_id: userFilter },
    ],
    queryFn: () => {
      const params = new URLSearchParams();
      if (monthFrom) params.set("month_from", monthFrom);
      if (monthTo) params.set("month_to", monthTo);
      if (userFilter) params.set("user_id", userFilter);
      const queryString = params.toString();
      return api.get<StatsResponse>(
        queryString
          ? `/api/admin/ai/usage/stats?${queryString}`
          : "/api/admin/ai/usage/stats",
      );
    },
  });

  const toggleSort = (nextKey: SortKey) => {
    if (sortKey === nextKey) {
      setSortDir((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(nextKey);
    setSortDir("desc");
  };

  const pricingQuery = useQuery({
    queryKey: ["admin", "ai", "pricing"],
    queryFn: () => api.get<PricingListResponse>("/api/admin/ai/pricing"),
    enabled: pricingOpen,
  });

  const upsertPricing = useMutation({
    mutationFn: (args: {
      model_name: string;
      input_per_million: number;
      output_per_million: number;
      cache_read_per_million: number | null;
      cache_write_per_million: number | null;
    }) =>
      api.put<PricingDbEntry>(
        `/api/admin/ai/pricing/${encodeURIComponent(args.model_name)}`,
        {
          input_per_million: args.input_per_million,
          output_per_million: args.output_per_million,
          cache_read_per_million: args.cache_read_per_million,
          cache_write_per_million: args.cache_write_per_million,
        },
      ),
    onSuccess: () => {
      toast.success("Pricing saved");
      queryClient.invalidateQueries({ queryKey: ["admin", "ai", "pricing"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "ai", "usage", "stats"] });
      setEditTarget(null);
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Pricing save failed"),
  });

  const deletePricing = useMutation({
    mutationFn: (modelName: string) =>
      api.delete(`/api/admin/ai/pricing/${encodeURIComponent(modelName)}`),
    onSuccess: () => {
      toast.success("Pricing deleted");
      queryClient.invalidateQueries({ queryKey: ["admin", "ai", "pricing"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "ai", "usage", "stats"] });
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : "Pricing delete failed"),
  });

  const openEdit = (entry: PricingDbEntry | "new") => {
    setEditTarget(entry);
    if (entry === "new") {
      setEditName("");
      setEditInput("");
      setEditOutput("");
      setEditCacheRead("");
      setEditCacheWrite("");
      return;
    }

    setEditName(entry.model_name);
    setEditInput(String(entry.input_per_million));
    setEditOutput(String(entry.output_per_million));
    setEditCacheRead(entry.cache_read_per_million?.toString() ?? "");
    setEditCacheWrite(entry.cache_write_per_million?.toString() ?? "");
  };

  const submitEdit = () => {
    const modelName = editName.trim();
    const inputPerMillion = Number(editInput);
    const outputPerMillion = Number(editOutput);
    const cacheReadPerMillion =
      editCacheRead === "" ? null : Number(editCacheRead);
    const cacheWritePerMillion =
      editCacheWrite === "" ? null : Number(editCacheWrite);

    if (!modelName) {
      toast.error("Model name is required");
      return;
    }
    if (!Number.isFinite(inputPerMillion) || !Number.isFinite(outputPerMillion)) {
      toast.error("Input and output prices must be valid numbers");
      return;
    }
    if (
      (cacheReadPerMillion !== null && !Number.isFinite(cacheReadPerMillion))
      || (cacheWritePerMillion !== null && !Number.isFinite(cacheWritePerMillion))
    ) {
      toast.error("Cache prices must be valid numbers");
      return;
    }

    if (
      inputPerMillion > SANITY_THRESHOLD
      || outputPerMillion > SANITY_THRESHOLD
      || (cacheReadPerMillion !== null && cacheReadPerMillion > SANITY_THRESHOLD)
      || (cacheWritePerMillion !== null && cacheWritePerMillion > SANITY_THRESHOLD)
    ) {
      toast.warning("These pricing values are unusually high. Saving anyway.");
    }

    upsertPricing.mutate({
      model_name: modelName,
      input_per_million: inputPerMillion,
      output_per_million: outputPerMillion,
      cache_read_per_million: cacheReadPerMillion,
      cache_write_per_million: cacheWritePerMillion,
    });
  };

  if (statsQuery.isLoading) {
    return <div className="p-6">Loading AI usage…</div>;
  }

  if (statsQuery.isError || !statsQuery.data) {
    return <div className="p-6">Failed to load AI usage.</div>;
  }

  const { current_month: currentMonth, last_12_months: last12Months, assumed_model: assumedModel } = statsQuery.data;
  const sortedRows = sortRows(statsQuery.data.rows, sortKey, sortDir);

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">AI Usage</h1>
          <Badge variant="secondary" className="font-mono">
            Assumed model: {assumedModel}
          </Badge>
        </div>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Cost estimates are recomputed on read using the currently configured model.
          Unknown-model usage stays explicit with an em dash instead of a fake zero. If you
          update the model in <Link to="/ai/config" className="underline underline-offset-2">Config</Link>,
          historical usage reprices on the next load.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card className="border-chart-1/30 bg-linear-to-br from-chart-1/10 via-card to-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Input tokens ({currentMonth.month})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold tracking-tight tabular-nums">
              {formatTokens(currentMonth.input_tokens)}
            </div>
            <p className="text-xs text-muted-foreground">
              Prompt and request volume across all users this month.
            </p>
          </CardContent>
        </Card>

        <Card className="border-chart-2/30 bg-linear-to-br from-chart-2/10 via-card to-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Output tokens ({currentMonth.month})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold tracking-tight tabular-nums">
              {formatTokens(currentMonth.output_tokens)}
            </div>
            <p className="text-xs text-muted-foreground">
              Response volume produced by the currently assumed model.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Calls ({currentMonth.month})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold tracking-tight tabular-nums">
              {formatTokens(currentMonth.call_count)}
            </div>
            <p className="text-xs text-muted-foreground">
              Aggregated request count from the monthly usage table.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Estimated cost ({currentMonth.month})
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="text-3xl font-semibold tracking-tight tabular-nums">
              {formatCost(currentMonth.estimated_cost)}
            </div>
            <p className="text-xs text-muted-foreground">
              Includes cache pricing only when the model pricing source exposes it.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Last 12 months</CardTitle>
        </CardHeader>
        <CardContent>
          <ChartContainer config={chartConfig} className="h-[320px] w-full">
            <BarChart data={last12Months} accessibilityLayer>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="month"
                axisLine={false}
                tickLine={false}
                tickMargin={10}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tickMargin={10}
                tickFormatter={formatAxisTokens}
              />
              <ChartTooltip
                cursor={false}
                content={
                  <ChartTooltipContent
                    formatter={(value, name) => [
                      formatTokens(Number(value)),
                      name === "input_tokens" ? "Input" : "Output",
                    ]}
                  />
                }
              />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar
                dataKey="input_tokens"
                stackId="tokens"
                fill="var(--color-input_tokens)"
                radius={[0, 0, 6, 6]}
              />
              <Bar
                dataKey="output_tokens"
                stackId="tokens"
                fill="var(--color-output_tokens)"
                radius={[6, 6, 0, 0]}
              />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="month_from">From month (YYYY-MM)</Label>
            <Input
              id="month_from"
              placeholder="2025-05"
              value={monthFrom}
              onChange={(event) => setMonthFrom(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="month_to">To month (YYYY-MM)</Label>
            <Input
              id="month_to"
              placeholder="2026-04"
              value={monthTo}
              onChange={(event) => setMonthTo(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="user_id_filter">User ID</Label>
            <Input
              id="user_id_filter"
              type="number"
              placeholder="Any"
              value={userFilter}
              onChange={(event) => setUserFilter(event.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Rows ({sortedRows.length})</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="p-2">
                  <button
                    type="button"
                    className="font-medium transition-colors hover:text-foreground"
                    onClick={() => toggleSort("month")}
                  >
                    Month{sortKey === "month" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                  </button>
                </th>
                <th className="p-2">
                  <button
                    type="button"
                    className="font-medium transition-colors hover:text-foreground"
                    onClick={() => toggleSort("user_id")}
                  >
                    User{sortKey === "user_id" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                  </button>
                </th>
                <th className="p-2 text-right">
                  <button
                    type="button"
                    className="font-medium transition-colors hover:text-foreground"
                    onClick={() => toggleSort("call_count")}
                  >
                    Calls{sortKey === "call_count" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                  </button>
                </th>
                <th className="p-2 text-right">
                  <button
                    type="button"
                    className="font-medium transition-colors hover:text-foreground"
                    onClick={() => toggleSort("input_tokens")}
                  >
                    Input{sortKey === "input_tokens" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                  </button>
                </th>
                <th className="p-2 text-right">
                  <button
                    type="button"
                    className="font-medium transition-colors hover:text-foreground"
                    onClick={() => toggleSort("output_tokens")}
                  >
                    Output{sortKey === "output_tokens" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                  </button>
                </th>
                <th className="p-2 text-right">Cache read</th>
                <th className="p-2 text-right">Cache write</th>
                <th className="p-2 text-right">
                  <button
                    type="button"
                    className="font-medium transition-colors hover:text-foreground"
                    onClick={() => toggleSort("estimated_cost")}
                  >
                    Est. cost{sortKey === "estimated_cost" ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr key={row.id} className="border-b border-border/60 hover:bg-muted/30">
                  <td className="p-2 font-mono tabular-nums">{row.month}</td>
                  <td className="p-2 font-mono tabular-nums">{row.user_id}</td>
                  <td className="p-2 text-right font-mono tabular-nums">
                    {formatTokens(row.call_count)}
                  </td>
                  <td className="p-2 text-right font-mono tabular-nums">
                    {formatTokens(row.input_tokens)}
                  </td>
                  <td className="p-2 text-right font-mono tabular-nums">
                    {formatTokens(row.output_tokens)}
                  </td>
                  <td className="p-2 text-right font-mono tabular-nums">
                    {formatTokens(row.cache_read_tokens)}
                  </td>
                  <td className="p-2 text-right font-mono tabular-nums">
                    {formatTokens(row.cache_write_tokens)}
                  </td>
                  <td className="p-2 text-right font-mono tabular-nums">
                    {formatCost(row.estimated_cost)}
                  </td>
                </tr>
              ))}
              {sortedRows.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-6 text-center text-muted-foreground">
                    No usage data for the current filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Model pricing</CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setPricingOpen((current) => !current)}
          >
            {pricingOpen ? "Hide" : "Manage"}
          </Button>
        </CardHeader>
        {pricingOpen && (
          <CardContent className="space-y-4">
            <div className="flex justify-end">
              <Button size="sm" onClick={() => openEdit("new")}>
                + Add custom pricing
              </Button>
            </div>

            {pricingQuery.isLoading && (
              <p className="text-sm text-muted-foreground">Loading pricing…</p>
            )}

            {pricingQuery.isError && (
              <p className="text-sm text-destructive">Failed to load pricing.</p>
            )}

            {pricingQuery.data && (
              <div className="space-y-5">
                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Custom (DB)</h3>
                  {pricingQuery.data.db_entries.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No custom pricing rows.
                    </p>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[720px] text-sm">
                        <thead>
                          <tr className="border-b text-left text-muted-foreground">
                            <th className="p-2">Model</th>
                            <th className="p-2 text-right">Input $/M</th>
                            <th className="p-2 text-right">Output $/M</th>
                            <th className="p-2 text-right">Cache read $/M</th>
                            <th className="p-2 text-right">Cache write $/M</th>
                            <th className="p-2" />
                          </tr>
                        </thead>
                        <tbody>
                          {pricingQuery.data.db_entries.map((entry) => (
                            <tr
                              key={entry.model_name}
                              className="border-b border-border/60 hover:bg-muted/30"
                            >
                              <td className="p-2 font-mono">{entry.model_name}</td>
                              <td className="p-2 text-right font-mono tabular-nums">
                                {entry.input_per_million.toFixed(2)}
                              </td>
                              <td className="p-2 text-right font-mono tabular-nums">
                                {entry.output_per_million.toFixed(2)}
                              </td>
                              <td className="p-2 text-right font-mono tabular-nums">
                                {entry.cache_read_per_million?.toFixed(2) ?? "—"}
                              </td>
                              <td className="p-2 text-right font-mono tabular-nums">
                                {entry.cache_write_per_million?.toFixed(2) ?? "—"}
                              </td>
                              <td className="p-2 text-right">
                                <div className="flex justify-end gap-2">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => openEdit(entry)}
                                  >
                                    Edit
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    disabled={deletePricing.isPending}
                                    onClick={() => deletePricing.mutate(entry.model_name)}
                                  >
                                    Delete
                                  </Button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div className="space-y-2">
                  <h3 className="text-sm font-medium">Built-in (static)</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[520px] text-sm">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="p-2">Model</th>
                          <th className="p-2 text-right">Input $/M</th>
                          <th className="p-2 text-right">Output $/M</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pricingQuery.data.static_entries.map((entry) => (
                          <tr
                            key={entry.model_name}
                            className="border-b border-border/60 hover:bg-muted/30"
                          >
                            <td className="p-2 font-mono">{entry.model_name}</td>
                            <td className="p-2 text-right font-mono tabular-nums">
                              {entry.input_per_million.toFixed(2)}
                            </td>
                            <td className="p-2 text-right font-mono tabular-nums">
                              {entry.output_per_million.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        )}
      </Card>

      <Dialog
        open={editTarget !== null}
        onOpenChange={(open) => {
          if (!open) setEditTarget(null);
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {editTarget === "new" ? "Add custom pricing" : `Edit ${editName}`}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="pricing_model_name">Model name</Label>
              <Input
                id="pricing_model_name"
                value={editName}
                placeholder="gpt-4.5-preview"
                disabled={editTarget !== "new"}
                onChange={(event) => setEditName(event.target.value)}
              />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="pricing_input">Input $/M</Label>
                <Input
                  id="pricing_input"
                  type="number"
                  step="0.01"
                  value={editInput}
                  onChange={(event) => setEditInput(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pricing_output">Output $/M</Label>
                <Input
                  id="pricing_output"
                  type="number"
                  step="0.01"
                  value={editOutput}
                  onChange={(event) => setEditOutput(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pricing_cache_read">Cache read $/M (optional)</Label>
                <Input
                  id="pricing_cache_read"
                  type="number"
                  step="0.01"
                  value={editCacheRead}
                  onChange={(event) => setEditCacheRead(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pricing_cache_write">Cache write $/M (optional)</Label>
                <Input
                  id="pricing_cache_write"
                  type="number"
                  step="0.01"
                  value={editCacheWrite}
                  onChange={(event) => setEditCacheWrite(event.target.value)}
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTarget(null)}>
              Cancel
            </Button>
            <Button onClick={submitEdit} disabled={upsertPricing.isPending}>
              {upsertPricing.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
