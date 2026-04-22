import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Database, HomeIcon, ListChecks } from "lucide-react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { Home } from "@/pages/Home";
import { QueryPlaceholder } from "@/pages/QueryPlaceholder";
import { Queries } from "@/pages/Queries";

const queryClient = new QueryClient();

function Sidebar() {
  return (
    <aside className="hidden w-64 shrink-0 border-r bg-muted/30 md:block">
      <div className="flex h-14 items-center gap-2 border-b px-5">
        <Database className="h-5 w-5" aria-hidden="true" />
        <span className="font-semibold">AgentLens</span>
      </div>
      <nav className="px-3 py-4">
        <Link
          to="/"
          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <HomeIcon className="h-4 w-4" aria-hidden="true" />
          Home
        </Link>
        <Link
          to="/queries"
          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <ListChecks className="h-4 w-4" aria-hidden="true" />
          Queries
        </Link>
      </nav>
    </aside>
  );
}

function Header() {
  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4 md:px-6">
      <div className="font-semibold md:hidden">AgentLens</div>
      <div className="hidden text-sm text-muted-foreground md:block">Trajectory Analysis</div>
    </header>
  );
}

function AppShell() {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header />
        <main className="flex-1 px-4 py-6 md:px-8">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/queries" element={<Queries />} />
            <Route path="/query" element={<QueryPlaceholder mode="new" />} />
            <Route path="/query/:queryId" element={<QueryPlaceholder mode="detail" />} />
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
