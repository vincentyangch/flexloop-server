import { NavLink } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import {
  LayoutDashboard,
  Users,
  ClipboardList,
  Dumbbell,
  Ruler,
  Trophy,
  Library,
  Settings,
  FileText,
  FlaskConical,
  BarChart3,
  HardDriveDownload,
  ScrollText,
  Wrench,
  Activity,
} from "lucide-react";

type Item = {
  label: string;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  disabled?: boolean;
};
type Group = { label?: string; items: Item[] };

// Phase 1 enables Dashboard and Health. Everything else is visible but
// disabled so the final IA is visible from day one.
const groups: Group[] = [
  {
    items: [
      { label: "Dashboard", to: "/", icon: LayoutDashboard },
      { label: "Health", to: "/health", icon: Activity },
    ],
  },
  {
    label: "User Data",
    items: [
      { label: "Users", to: "/users", icon: Users, disabled: true },
      { label: "Plans", to: "/plans", icon: ClipboardList, disabled: true },
      { label: "Workouts", to: "/workouts", icon: Dumbbell, disabled: true },
      { label: "Measurements", to: "/measurements", icon: Ruler, disabled: true },
      { label: "Personal Records", to: "/prs", icon: Trophy, disabled: true },
    ],
  },
  {
    label: "Catalog",
    items: [{ label: "Exercises", to: "/exercises", icon: Library, disabled: true }],
  },
  {
    label: "AI",
    items: [
      { label: "Config", to: "/ai/config", icon: Settings, disabled: true },
      { label: "Prompts", to: "/ai/prompts", icon: FileText, disabled: true },
      { label: "Playground", to: "/ai/playground", icon: FlaskConical, disabled: true },
      { label: "Usage", to: "/ai/usage", icon: BarChart3, disabled: true },
    ],
  },
  {
    label: "Operations",
    items: [
      { label: "Backup & Restore", to: "/ops/backup", icon: HardDriveDownload, disabled: true },
      { label: "Logs", to: "/ops/logs", icon: ScrollText, disabled: true },
      { label: "Triggers", to: "/ops/triggers", icon: Wrench, disabled: true },
    ],
  },
];

export function AppSidebar() {
  return (
    <Sidebar>
      <SidebarHeader>
        <div className="px-2 py-3 font-semibold">FlexLoop Admin</div>
      </SidebarHeader>
      <SidebarContent>
        {groups.map((group, gi) => (
          <SidebarGroup key={gi}>
            {group.label && <SidebarGroupLabel>{group.label}</SidebarGroupLabel>}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild disabled={item.disabled}>
                      {item.disabled ? (
                        <span className="opacity-40 cursor-not-allowed flex items-center gap-2">
                          <item.icon className="h-4 w-4" />
                          {item.label}
                        </span>
                      ) : (
                        <NavLink
                          to={item.to}
                          end
                          className={({ isActive }) =>
                            isActive ? "font-medium" : ""
                          }
                        >
                          <item.icon className="h-4 w-4" />
                          {item.label}
                        </NavLink>
                      )}
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
    </Sidebar>
  );
}
