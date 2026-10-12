/**
 * VeriDictum AI — App Shell Layout (Sidebar + Topbar)
 */

import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Briefcase,
  BarChart3,
  Settings,
  LogOut,
  Menu,
  X,
  ChevronRight,
  Shield,
  Bell,
  Search,
  Sun,
  Moon,
} from "lucide-react";
import { clsx } from "clsx";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";
import { authApi, notificationsApi } from "@/services/api";
import { useUserNotifications } from "@/hooks/useWebSocket";
import { CommandPalette } from "@/components/organisms/CommandPalette";
import { useThemeStore } from "@/store/themeStore";
import { useTheme } from "@/hooks/useTheme";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Cases", href: "/cases", icon: Briefcase },
  { name: "Reports", href: "/reports", icon: BarChart3 },
];

/**
 * True when `path` is the active route for nav item `href`.
 * Avoid `startsWith` collisions (e.g. `/cases/xyz/reports` highlighting both
 * Cases AND Reports). A route is active if it equals `href` or is a real sub-
 * path of `href` (`/cases/123`), never if it merely shares a string prefix.
 */
function isNavActive(pathname: string, href: string): boolean {
  if (pathname === href) return true;
  return pathname.startsWith(href + "/");
}

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const { user, refreshToken, logout } = useAuthStore();
  const { isDark } = useTheme();
  const toggleTheme = useThemeStore((s) => s.toggle);

  const { data: unreadData } = useQuery({
    queryKey: ["unread-count"],
    queryFn: () => notificationsApi.unreadCount().then((r) => r.data),
    refetchInterval: 60_000,
  });
  const unreadCount: number = (unreadData as any)?.unread_count ?? 0;

  useUserNotifications(user?.id);

  const handleLogout = async () => {
    try {
      if (refreshToken) await authApi.logout(refreshToken);
    } finally {
      logout();
      navigate("/login");
    }
  };

  const SidebarContent = () => (
    <div className="flex flex-col h-full bg-navy-600 dark:bg-navy-900 dark:border-r dark:border-navy-700">
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-navy-500 dark:border-navy-700">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-gold-500">
          <Shield className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-white font-bold text-sm leading-tight">Sarvam Nyaya</p>
          <p className="text-navy-200 text-xs">Legal Intelligence</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto" aria-label="Primary">
        {navigation.map((item) => {
          const isActive = isNavActive(location.pathname, item.href);
          return (
            <Link
              key={item.name}
              to={item.href}
              onClick={() => setSidebarOpen(false)}
              aria-current={isActive ? "page" : undefined}
              className={clsx(
                "relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                isActive
                  ? "bg-white/15 text-white shadow-sm before:absolute before:inset-y-1 before:left-0 before:w-1 before:rounded-r-full before:bg-gold-500"
                  : "text-navy-200 hover:bg-white/5 hover:text-white"
              )}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              <span>{item.name}</span>
              {isActive && <ChevronRight className="w-4 h-4 ml-auto" />}
            </Link>
          );
        })}
      </nav>

      {/* User section */}
      <div className="px-3 py-4 border-t border-navy-500 space-y-1">
        <Link
          to="/settings"
          aria-current={isNavActive(location.pathname, "/settings") ? "page" : undefined}
          className={clsx(
            "relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
            isNavActive(location.pathname, "/settings")
              ? "bg-white/15 text-white shadow-sm before:absolute before:inset-y-1 before:left-0 before:w-1 before:rounded-r-full before:bg-gold-500"
              : "text-navy-200 hover:bg-white/5 hover:text-white"
          )}
        >
          <Settings className="w-5 h-5" />
          <span>Settings</span>
          {isNavActive(location.pathname, "/settings") && (
            <ChevronRight className="w-4 h-4 ml-auto" />
          )}
        </Link>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-navy-200 hover:bg-white/5 hover:text-red-300 transition-colors"
        >
          <LogOut className="w-5 h-5" />
          <span>Logout</span>
        </button>
        {user && (
          <div className="flex items-center gap-3 px-3 py-3 mt-2 rounded-lg bg-white/5">
            <div className="w-8 h-8 rounded-full bg-gold-500 flex items-center justify-center text-white text-xs font-bold">
              {user.full_name.charAt(0).toUpperCase()}
            </div>
            <div className="overflow-hidden">
              <p className="text-white text-xs font-medium truncate">{user.full_name}</p>
              <p className="text-navy-300 text-xs truncate capitalize">
                {user.role.charAt(0).toUpperCase() + user.role.slice(1).toLowerCase()}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50 dark:bg-navy-900 text-gray-900 dark:text-gray-100 transition-colors">
      {/* Skip-link — invisible until focused. Lets keyboard users bypass the
          sidebar nav and jump directly to the main content region. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-3 focus:py-2 focus:bg-navy-700 focus:text-white focus:rounded-lg focus:shadow-lg"
      >
        Skip to main content
      </a>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar — desktop */}
      <aside
        className="hidden lg:flex lg:w-64 lg:flex-col lg:flex-shrink-0"
        aria-label="Primary navigation"
      >
        <SidebarContent />
      </aside>

      {/* Sidebar — mobile */}
      <aside
        className={clsx(
          "fixed inset-y-0 left-0 z-30 w-64 flex flex-col transform transition-transform lg:hidden",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
        aria-label="Mobile navigation"
        aria-hidden={!sidebarOpen}
      >
        <SidebarContent />
      </aside>

      {/* Main content */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {/* Topbar */}
        <header
          className="flex items-center justify-between h-16 px-4 bg-white dark:bg-navy-800 border-b border-gray-200 dark:border-navy-700 flex-shrink-0"
          role="banner"
        >
          <button
            className="lg:hidden p-2 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-navy-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-500 dark:focus-visible:ring-gold-400"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? "Close menu" : "Open menu"}
            aria-expanded={sidebarOpen}
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <div className="flex items-center gap-3 ml-auto">
            {/* Cmd+K palette trigger — the actual handler is the global
                keydown listener inside <CommandPalette/>. Clicking this just
                forwards a synthetic event so mouse users get the same UX. */}
            <button
              type="button"
              onClick={() => {
                const evt = new KeyboardEvent("keydown", {
                  key: "k",
                  metaKey: true,
                  ctrlKey: true,
                  bubbles: true,
                });
                window.dispatchEvent(evt);
              }}
              className="hidden md:inline-flex items-center gap-2 px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 dark:border-navy-600 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-navy-700 hover:text-gray-700 dark:hover:text-gray-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-500 dark:focus-visible:ring-gold-400"
              title="Open command palette (⌘K)"
              aria-label="Open command palette"
              aria-keyshortcuts="Meta+K Control+K"
            >
              <Search className="w-3.5 h-3.5" aria-hidden="true" />
              <span className="hidden lg:inline">Search…</span>
              <kbd className="font-mono bg-gray-100 dark:bg-navy-700 dark:text-gray-300 rounded px-1 py-0.5 text-[10px]" aria-hidden="true">⌘ K</kbd>
            </button>
            {/* Theme toggle — sun in dark mode, moon in light mode. Cycles
                light → dark → light. System is the unattended default until
                the user touches this. */}
            <button
              type="button"
              onClick={toggleTheme}
              className="p-2 rounded-lg text-gray-500 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-navy-700 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-500 dark:focus-visible:ring-gold-400"
              title={isDark ? "Switch to light mode" : "Switch to dark mode"}
              aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
              aria-pressed={isDark}
            >
              {isDark ? <Sun className="w-5 h-5" aria-hidden="true" /> : <Moon className="w-5 h-5" aria-hidden="true" />}
            </button>
            <Link
              to="/settings"
              className="relative p-2 rounded-lg text-gray-500 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-navy-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-500 dark:focus-visible:ring-gold-400"
              aria-label={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : "Notifications"}
            >
              <Bell className="w-5 h-5" aria-hidden="true" />
              {unreadCount > 0 && (
                <span
                  className="absolute top-1 right-1 flex items-center justify-center w-4 h-4 text-[10px] font-bold text-white bg-red-500 rounded-full"
                  aria-hidden="true"
                >
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </Link>
            {user && (
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
                  {user.full_name}
                </span>
                <span className="hidden sm:inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold tracking-wide bg-navy-50 text-navy-700 dark:bg-navy-700 dark:text-gold-300">
                  {user.role
                    ? user.role.charAt(0).toUpperCase() + user.role.slice(1).toLowerCase()
                    : ""}
                </span>
              </div>
            )}
          </div>
        </header>

        {/* Page content */}
        <main
          className="flex-1 overflow-y-auto p-6"
          id="main-content"
          tabIndex={-1}
        >
          {children}
        </main>
      </div>

      {/* Global Cmd+K command palette — listens for ⌘K / Ctrl+K anywhere. */}
      <CommandPalette />
    </div>
  );
}
