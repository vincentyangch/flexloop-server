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
  ShieldUser,
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
      { label: "Users", to: "/users", icon: Users },
      { label: "Plans", to: "/plans", icon: ClipboardList },
      { label: "Workouts", to: "/workouts", icon: Dumbbell },
      { label: "Measurements", to: "/measurements", icon: Ruler },
      { label: "Personal Records", to: "/prs", icon: Trophy },
    ],
  },
  {
    label: "Catalog",
    items: [{ label: "Exercises", to: "/exercises", icon: Library }],
  },
  {
    label: "AI",
    items: [
      { label: "Config", to: "/ai/config", icon: Settings },
      { label: "Prompts", to: "/ai/prompts", icon: FileText },
      { label: "Playground", to: "/ai/playground", icon: FlaskConical },
      { label: "Usage", to: "/ai/usage", icon: BarChart3 },
    ],
  },
  {
    label: "Operations",
    items: [
      { label: "Backup & Restore", to: "/ops/backup", icon: HardDriveDownload },
      { label: "Logs", to: "/ops/logs", icon: ScrollText },
      { label: "Triggers", to: "/ops/triggers", icon: Wrench },
    ],
  },
  {
    label: "",
    items: [
      { label: "Admin Users", to: "/admin-users", icon: ShieldUser },
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
