import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Database, HomeIcon, ListChecks, Moon, SettingsIcon } from "lucide-react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Connections } from "@/pages/Connections";
import { Home } from "@/pages/Home";
import { Query } from "@/pages/Query";
import { Queries } from "@/pages/Queries";
import { Settings } from "@/pages/Settings";

const queryClient = new QueryClient();

function Sidebar() {
  const items = [
    { to: "/", label: "Home", icon: HomeIcon },
    { to: "/connections", label: "连接管理", icon: Database },
    { to: "/queries", label: "Queries", icon: ListChecks },
    { to: "/settings", label: "Settings", icon: SettingsIcon },
  ];

  return (
    <aside className="fixed inset-y-0 left-0 hidden w-64 border-r bg-muted/30 md:block">
      <div className="flex h-14 items-center gap-2 border-b px-5">
        <span className="font-semibold tracking-tight">AgentLens</span>
      </div>
      <nav className="space-y-1 px-3 py-4">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                )
              }
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {item.label}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}

function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4 md:px-6">
      <div>
        <div className="font-semibold tracking-tight">AgentLens</div>
        <div className="hidden text-xs text-muted-foreground md:block">Trajectory Analysis</div>
      </div>
      <Button variant="outline" size="sm" className="gap-2" disabled>
        <Moon className="h-4 w-4" aria-hidden="true" />
        主题
      </Button>
    </header>
  );
}

function AppShell() {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col md:pl-64">
        <Header />
        <main className="flex-1 px-4 py-6 md:px-8">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/connections" element={<Connections />} />
            <Route path="/queries" element={<Queries />} />
            <Route path="/query" element={<Query />} />
            <Route path="/query/:queryId" element={<Query />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell />
        <Toaster richColors />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
