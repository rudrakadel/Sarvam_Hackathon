/**
 * VeriDictum AI — Register Page (UC-01)
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Shield, CheckCircle } from "lucide-react";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { authApi } from "@/services/api";

const schema = z
  .object({
    full_name: z.string().min(2, "Full name required"),
    email: z.string().email("Valid email required"),
    organisation_name: z.string().min(2, "Law firm or organisation name required"),
    password: z
      .string()
      .min(12, "Minimum 12 characters")
      .regex(/[A-Z]/, "Needs uppercase letter")
      .regex(/[0-9]/, "Needs number")
      .regex(/[^A-Za-z0-9]/, "Needs special character"),
    confirm_password: z.string(),
  })
  .refine((d) => d.password === d.confirm_password, {
    message: "Passwords don't match",
    path: ["confirm_password"],
  });

type FormData = z.infer<typeof schema>;

export function RegisterPage() {
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    setError(null);
    try {
      await authApi.register({
        full_name: data.full_name,
        email: data.email,
        password: data.password,
        organisation_name: data.organisation_name,
      });
      setSuccess(true);
    } catch (err: unknown) {
      const e = err as { response?: { data: { detail: string } } };
      setError(e.response?.data?.detail || "Registration failed.");
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-navy-600 to-navy-800 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl p-8 w-full max-w-md text-center">
          <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-900 mb-2">Check Your Email</h2>
          <p className="text-gray-600 text-sm mb-6">
            We've sent a verification link to your email address. Click it to activate your account.
          </p>
          <Link
            to="/login"
            className="inline-flex items-center justify-center px-6 py-3 bg-navy-600 text-white rounded-lg font-medium hover:bg-navy-700 transition-colors"
          >
            Back to Login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-navy-600 to-navy-800 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-gold-500 mb-4 shadow-lg">
            <Shield className="w-9 h-9 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Sarvam Nyaya</h1>
          <p className="text-navy-200 text-sm mt-1">Start your 30-day free trial</p>
        </div>

        <div className="bg-white rounded-2xl shadow-2xl p-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">Create Account</h2>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Input
              label="Full Name"
              placeholder="Jane Smith"
              error={errors.full_name?.message}
              required
              {...register("full_name")}
            />
            <Input
              label="Email Address"
              type="email"
              placeholder="jane@smithlaw.com"
              error={errors.email?.message}
              required
              {...register("email")}
            />
            <Input
              label="Law Firm or Organization"
              placeholder="Smith & Associates LLP"
              error={errors.organisation_name?.message}
              required
              {...register("organisation_name")}
            />
            <Input
              label="Password"
              type="password"
              placeholder="••••••••••••"
              hint="Min 12 chars, uppercase, number, special char"
              error={errors.password?.message}
              required
              {...register("password")}
            />
            <Input
              label="Confirm Password"
              type="password"
              placeholder="••••••••••••"
              error={errors.confirm_password?.message}
              required
              {...register("confirm_password")}
            />

            <Button type="submit" fullWidth loading={isSubmitting} size="lg" className="mt-2">
              Create Account
            </Button>
          </form>

          <p className="text-center text-sm text-gray-600 mt-6">
            Already have an account?{" "}
            <Link to="/login" className="text-navy-600 font-medium hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
