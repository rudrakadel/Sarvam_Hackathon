/**
 * CommandPalette — Cmd+K / Ctrl+K instant navigation.
 *
 * Powered by `cmdk`. Provides:
 *   - Fuzzy search across all cases in the org.
 *   - Quick jump-to-page actions (Dashboard / Cases / Reports / Settings).
 *   - Recent items pinned to the top.
 *
 * The palette listens globally for `(meta|ctrl)+k`. Open / close are managed
 * via local state; consumers don't have to render anything except this
 * component once near the root.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import {
  Search,
  Briefcase,
  LayoutDashboard,
  BarChart3,
  Settings as SettingsIcon,
  Plus,
  MessageSquare,
  CornerDownLeft,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { casesApi } from "@/services/api";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { formatLabel } from "@/utils/format";
import type { Case } from "@/types";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const reduce = useReducedMotion();

  // Global keyboard listener — Cmd+K (mac) / Ctrl+K (win/linux)
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
        return;
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Fetch cases for fuzzy search — only when the palette is open so we don't
  // pay the network cost for users who never trigger it.
  const { data: casesData, isLoading } = useQuery({
    queryKey: ["cases", "palette"],
    queryFn: () => casesApi.list({ page: 1, page_size: 50 }),
    enabled: open,
    staleTime: 60_000,
  });

  const cases: Case[] = casesData?.data?.items ?? [];

  const go = (path: string): void => {
    setOpen(false);
    setSearch("");
    navigate(path);
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4"
          initial={reduce ? { opacity: 0 } : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={() => setOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Command palette"
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-navy-900/50 backdrop-blur-sm" />

          {/* Panel */}
          <motion.div
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            onClick={(e) => e.stopPropagation()}
            className="relative w-full max-w-xl rounded-2xl bg-white dark:bg-navy-800 shadow-2xl border border-gray-200 dark:border-navy-700 overflow-hidden"
          >
            <Command
              label="Command palette"
              loop
              filter={(value, query) => {
                if (!query) return 1;
                const v = value.toLowerCase();
                const q = query.toLowerCase().trim();
                if (v.includes(q)) return 1;
                // soft token match
                const toks = q.split(/\s+/).filter(Boolean);
                return toks.every((t) => v.includes(t)) ? 0.7 : 0;
              }}
            >
              {/* Search input */}
              <div className="flex items-center gap-3 px-4 border-b border-gray-100 dark:border-navy-700">
                <Search className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" aria-hidden="true" />
                <Command.Input
                  autoFocus
                  value={search}
                  onValueChange={setSearch}
                  placeholder="Search cases or jump to a page…"
                  className="flex-1 py-4 bg-transparent text-sm text-gray-800 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none"
                />
                <kbd className="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-gray-200 dark:border-navy-600 text-[10px] font-mono text-gray-500 dark:text-gray-400">
                  esc
                </kbd>
              </div>

              <Command.List className="max-h-[60vh] overflow-y-auto py-2">
                <Command.Empty className="px-4 py-6 text-sm text-gray-400 dark:text-gray-500 text-center">
                  No matches. Press <kbd className="font-mono text-[11px] bg-gray-100 dark:bg-navy-700 rounded px-1 py-0.5">esc</kbd> to close.
                </Command.Empty>

                {/* ── Jump to ───────────────────────────────────────── */}
                <Command.Group heading="Jump to">
                  <PaletteAction
                    icon={LayoutDashboard}
                    label="Dashboard"
                    hint="Overview metrics"
                    onSelect={() => go("/dashboard")}
                  />
                  <PaletteAction
                    icon={Briefcase}
                    label="Cases"
                    hint="All cases in your organisation"
                    onSelect={() => go("/cases")}
                  />
                  <PaletteAction
                    icon={Plus}
                    label="New case"
                    hint="Create a new case"
                    onSelect={() => go("/cases/new")}
                  />
                  <PaletteAction
                    icon={BarChart3}
                    label="Reports"
                    hint="Contradiction intelligence reports"
                    onSelect={() => go("/reports")}
                  />
                  <PaletteAction
                    icon={SettingsIcon}
                    label="Settings"
                    hint="Profile, MFA, sessions"
                    onSelect={() => go("/settings")}
                  />
                </Command.Group>

                {/* ── Cases ─────────────────────────────────────────── */}
                <Command.Group heading={isLoading ? "Loading cases…" : "Cases"}>
                  {cases.map((c) => (
                    <PaletteAction
                      key={c.id}
                      icon={Briefcase}
                      label={c.title}
                      hint={`${c.case_number} · ${formatLabel(c.case_type)}`}
                      onSelect={() => go(`/cases/${c.id}`)}
                    />
                  ))}
                </Command.Group>

                {/* ── Ask AI on the most recent case ──────────────── */}
                {cases[0] && (
                  <Command.Group heading="AI">
                    <PaletteAction
                      icon={MessageSquare}
                      label={`Ask Vera about ${cases[0].title}`}
                      hint="Open the AI assistant"
                      onSelect={() => go(`/cases/${cases[0].id}/query`)}
                    />
                  </Command.Group>
                )}
              </Command.List>

              {/* Footer */}
              <div className="flex items-center justify-between px-4 py-2 border-t border-gray-100 dark:border-navy-700 text-[11px] text-gray-500 dark:text-gray-400">
                <span className="flex items-center gap-2">
                  <CornerDownLeft className="w-3 h-3" />
                  <span>to select</span>
                </span>
                <span className="hidden sm:flex items-center gap-1">
                  <kbd className="font-mono bg-gray-100 dark:bg-navy-700 dark:text-gray-300 rounded px-1 py-0.5 text-[10px]">⌘</kbd>
                  <kbd className="font-mono bg-gray-100 dark:bg-navy-700 dark:text-gray-300 rounded px-1 py-0.5 text-[10px]">K</kbd>
                  to toggle
                </span>
              </div>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

interface PaletteActionProps {
  icon: React.ElementType;
  label: string;
  hint?: string;
  onSelect: () => void;
}

function PaletteAction({ icon: Icon, label, hint, onSelect }: PaletteActionProps) {
  return (
    <Command.Item
      value={`${label} ${hint ?? ""}`}
      onSelect={onSelect}
      className="flex items-center gap-3 px-3 py-2.5 mx-2 rounded-lg cursor-pointer text-sm text-gray-700 dark:text-gray-200 aria-selected:bg-navy-50 dark:aria-selected:bg-navy-700 aria-selected:text-navy-700 dark:aria-selected:text-gold-300 transition-colors"
    >
      <Icon className="w-4 h-4 text-gray-400 dark:text-gray-500 flex-shrink-0" aria-hidden="true" />
      <span className="flex-1 truncate">{label}</span>
      {hint && <span className="text-[11px] text-gray-400 dark:text-gray-500 truncate hidden sm:inline">{hint}</span>}
    </Command.Item>
  );
}
