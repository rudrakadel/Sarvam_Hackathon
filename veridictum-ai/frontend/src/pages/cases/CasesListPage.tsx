/**
 * VeriDictum AI — Cases List Page
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, Briefcase } from "lucide-react";
import { casesApi } from "@/services/api";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { formatLabel } from "@/utils/format";
import type { Case } from "@/types";
import { format } from "date-fns";

export function CasesListPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["cases", page],
    queryFn: () => casesApi.list({ page, page_size: 20 }),
  });

  const cases: Case[] = data?.data?.items || [];
  const total = data?.data?.total || 0;
  const totalPages = data?.data?.total_pages || 1;

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Cases</h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm">{total} cases in your organisation</p>
        </div>
        <Link to="/cases/new">
          <Button>
            <Plus className="w-4 h-4" />
            New Case
          </Button>
        </Link>
      </div>

      {/* Search */}
      <div className="max-w-sm">
        <Input
          placeholder="Search by case number or title..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Cases Table */}
      <div className="bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-navy-600 dark:border-gold-400 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : cases.length === 0 ? (
          <div className="text-center py-20">
            <Briefcase className="w-16 h-16 text-gray-200 dark:text-navy-600 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">No cases yet</h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm mb-6">
              Create your first case to start analysing transcripts and documents.
            </p>
            <Link to="/cases/new">
              <Button>
                <Plus className="w-4 h-4" />
                Create First Case
              </Button>
            </Link>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100 dark:border-navy-700 bg-gray-50 dark:bg-navy-900/40">
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Case</th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Type</th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                    <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Created</th>
                    <th className="px-6 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50 dark:divide-navy-700">
                  {cases.map((c) => (
                    <tr
                      key={c.id}
                      className="hover:bg-gray-50 dark:hover:bg-navy-700/40 transition-colors cursor-pointer"
                      onClick={() => navigate(`/cases/${c.id}`)}
                    >
                      <td className="px-6 py-4">
                        <div>
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">{c.title}</p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">{c.case_number}</p>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300">{formatLabel(c.case_type)}</td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium ${
                            c.status === "OPEN" ? "bg-green-50 text-green-700 ring-1 ring-inset ring-green-200 dark:bg-green-500/15 dark:text-green-400 dark:ring-green-500/30" :
                            c.status === "ARCHIVED" ? "bg-gray-100 text-gray-600 dark:bg-navy-700 dark:text-gray-400" :
                            "bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200 dark:bg-blue-500/15 dark:text-blue-400 dark:ring-blue-500/30"
                          }`}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            c.status === "OPEN" ? "bg-green-500" :
                            c.status === "ARCHIVED" ? "bg-gray-400" :
                            "bg-blue-500"
                          }`} />
                          {formatLabel(c.status)}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                        {format(new Date(c.created_at), "MMM d, yyyy")}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <span className="text-sm text-navy-600 dark:text-gold-400 font-medium">
                          Open →
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100 dark:border-navy-700">
                <p className="text-sm text-gray-500 dark:text-gray-400">Page {page} of {totalPages}</p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage(p => p - 1)}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage(p => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
