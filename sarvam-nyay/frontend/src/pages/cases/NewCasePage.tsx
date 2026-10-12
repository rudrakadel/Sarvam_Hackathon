/**
 * VeriDictum AI — New Case Page (UC-13)
 */

import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import toast from "react-hot-toast";
import { casesApi } from "@/services/api";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";

const CASE_TYPES = ["CRIMINAL", "CIVIL", "DEPOSITION", "ARBITRATION", "HEARING", "OTHER"] as const;

const schema = z.object({
  case_number: z.string().min(1, "Case number required"),
  title: z.string().min(3, "Title required"),
  court: z.string().optional(),
  jurisdiction: z.string().optional(),
  case_type: z.enum(CASE_TYPES, { errorMap: () => ({ message: "Please select a case type" }) }),
  description: z.string().optional(),
});
type FormData = z.infer<typeof schema>;

export function NewCasePage() {
  const navigate = useNavigate();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const mutation = useMutation({
    mutationFn: (data: FormData) => casesApi.create(data),
    onSuccess: (res) => {
      toast.success("Case created successfully.");
      navigate(`/cases/${res.data.id}`);
    },
    onError: () => toast.error("Failed to create case. Please try again."),
  });

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">New Case</h1>
        <p className="text-gray-500 text-sm mt-1">Create a new legal case to organise your evidence.</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
        <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-5">
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Case Number"
              placeholder="2026-CR-001234"
              error={errors.case_number?.message}
              required
              {...register("case_number")}
            />
            <div>
              <label className="text-sm font-medium text-gray-700 block mb-1">Case Type *</label>
              <select
                {...register("case_type")}
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-navy-500"
              >
                <option value="" disabled>Select case type…</option>
                {CASE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.charAt(0) + t.slice(1).toLowerCase()}
                  </option>
                ))}
              </select>
              {errors.case_type && (
                <p className="text-xs text-red-600 mt-1">{errors.case_type.message}</p>
              )}
            </div>
          </div>

          <Input
            label="Case Title"
            placeholder="State v. Johnson — Murder in the First Degree"
            error={errors.title?.message}
            required
            {...register("title")}
          />

          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Court"
              placeholder="Superior Court of California"
              {...register("court")}
            />
            <Input
              label="Jurisdiction"
              placeholder="Los Angeles County, CA"
              {...register("jurisdiction")}
            />
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 block mb-1">Description</label>
            <textarea
              {...register("description")}
              rows={3}
              placeholder="Brief case description..."
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-navy-500"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <Button type="submit" loading={mutation.isPending}>
              Create Case
            </Button>
            <Button type="button" variant="outline" onClick={() => navigate("/cases")}>
              Cancel
            </Button>
          </div>

          {mutation.isError && (
            <p className="text-sm text-red-600">Failed to create case. Please try again.</p>
          )}
        </form>
      </div>
    </div>
  );
}
