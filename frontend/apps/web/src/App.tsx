import { QueryClientProvider } from "@tanstack/react-query";
import { Database, HomeIcon, Languages, ListChecks, Moon, SettingsIcon } from "lucide-react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { queryClient } from "@/api/queryClient";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { NetworkBanner } from "@/components/common/NetworkBanner";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { isProductLanguage, type ProductLanguage } from "@/lib/productLanguage";
import { cn } from "@/lib/utils";
import { Connections } from "@/pages/Connections";
import { Home } from "@/pages/Home";
import { Query } from "@/pages/Query";
import { Queries } from "@/pages/Queries";
import { Settings } from "@/pages/Settings";
import { useProductLanguageStore } from "@/stores/productLanguageStore";

const APP_COPY: Record<
  ProductLanguage,
  {
    nav: {
      home: string;
      connections: string;
      queries: string;
      settings: string;
    };
    tagline: string;
    theme: string;
    language: string;
    languageOptions: Record<ProductLanguage, string>;
  }
> = {
  "zh-CN": {
    nav: {
      home: "首页",
      connections: "连接管理",
      queries: "查询",
      settings: "设置",
    },
    tagline: "Trajectory 分析",
    theme: "主题",
    language: "语言",
    languageOptions: {
      "zh-CN": "中文",
      "en-US": "English",
    },
  },
  "en-US": {
    nav: {
      home: "Home",
      connections: "Connections",
      queries: "Queries",
      settings: "Settings",
    },
    tagline: "Trajectory Analysis",
    theme: "Theme",
    language: "Language",
    languageOptions: {
      "zh-CN": "中文",
      "en-US": "English",
    },
  },
};

function Sidebar() {
  const language = useProductLanguageStore((state) => state.language);
  const copy = APP_COPY[language];
  const items = [
    { to: "/", label: copy.nav.home, icon: HomeIcon },
    { to: "/connections", label: copy.nav.connections, icon: Database },
    { to: "/queries", label: copy.nav.queries, icon: ListChecks },
    { to: "/settings", label: copy.nav.settings, icon: SettingsIcon },
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
  const language = useProductLanguageStore((state) => state.language);
  const copy = APP_COPY[language];

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4 md:px-6">
      <div>
        <div className="font-semibold tracking-tight">AgentLens</div>
        <div className="hidden text-xs text-muted-foreground md:block">{copy.tagline}</div>
      </div>
      <div className="flex items-center gap-2">
        <ProductLanguageSelect />
        <Button variant="outline" size="sm" className="gap-2" disabled>
          <Moon className="h-4 w-4" aria-hidden="true" />
          {copy.theme}
        </Button>
      </div>
    </header>
  );
}

function ProductLanguageSelect() {
  const language = useProductLanguageStore((state) => state.language);
  const setLanguage = useProductLanguageStore((state) => state.setLanguage);
  const copy = APP_COPY[language];

  function handleChange(value: string) {
    if (isProductLanguage(value)) {
      setLanguage(value);
    }
  }

  return (
    <Select value={language} onValueChange={handleChange}>
      <SelectTrigger className="h-9 w-32" aria-label={copy.language}>
        <div className="flex min-w-0 items-center gap-2">
          <Languages className="h-4 w-4 shrink-0" aria-hidden="true" />
          <SelectValue placeholder={copy.language} />
        </div>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="zh-CN">{copy.languageOptions["zh-CN"]}</SelectItem>
        <SelectItem value="en-US">{copy.languageOptions["en-US"]}</SelectItem>
      </SelectContent>
    </Select>
  );
}

function AppShell() {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col md:pl-64">
        <NetworkBanner />
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
      <ErrorBoundary>
        <BrowserRouter>
          <AppShell />
          <Toaster richColors />
        </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  );
}
