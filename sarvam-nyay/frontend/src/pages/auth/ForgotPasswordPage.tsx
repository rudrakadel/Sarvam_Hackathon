/**
 * VeriDictum AI — Forgot Password Page
 * Sends a password-reset link to the user's email.
 */

import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation } from "@tanstack/react-query";
import { Mail, ArrowLeft, CheckCircle, Shield } from "lucide-react";
import { authApi } from "@/services/api";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";

const schema = z.object({
  email: z.string().email("Valid email required"),
});
type FormData = z.infer<typeof schema>;

export function ForgotPasswordPage() {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const mutation = useMutation({
    mutationFn: (data: FormData) => authApi.forgotPassword(data.email),
  });

  if (mutation.isSuccess) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-navy-900 via-navy-800 to-navy-700 flex items-center justify-center px-4">
        <div className="w-full max-w-md text-center space-y-4">
          <CheckCircle className="w-16 h-16 text-green-400 mx-auto" />
          <h2 className="text-2xl font-bold text-white">Check your inbox</h2>
          <p className="text-navy-200 text-sm">
            If an account exists with that email, we've sent a password reset link.
            The link expires in 1 hour.
          </p>
          <Link
            to="/login"
            className="inline-flex items-center gap-2 text-sm text-gold-400 hover:text-gold-300 font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-navy-900 via-navy-800 to-navy-700 flex items-center justify-center px-4">
      <div className="w-full max-w-md space-y-8">
        {/* Brand — matches login page treatment */}
        <div className="text-center">
          <div className="inline-flex items-center gap-3 mb-6">
            <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-gold-500 shadow-lg">
              <Shield className="w-7 h-7 text-white" />
            </div>
            <div className="text-left">
              <p className="text-white font-bold text-xl leading-tight">Sarvam Nyaya</p>
              <p className="text-navy-200 text-xs">Legal Intelligence</p>
            </div>
          </div>
          {/* High-contrast text on dark background */}
          <h2 className="text-2xl font-bold text-white">Reset your password</h2>
          <p className="text-navy-200 text-sm mt-2">
            Enter your email and we'll send you a reset link.
          </p>
        </div>

        <div className="bg-white rounded-2xl shadow-xl border border-white/10 p-8 space-y-5">
          <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-4">
            <Input
              label="Email address"
              type="email"
              placeholder="you@lawfirm.com"
              error={errors.email?.message}
              autoComplete="email"
              autoFocus
              {...register("email")}
            />

            {mutation.isError && (
              <p className="text-sm text-red-600">
                Something went wrong. Please try again.
              </p>
            )}

            <Button
              type="submit"
              className="w-full justify-center"
              loading={mutation.isPending}
            >
              <Mail className="w-4 h-4" />
              Send reset link
            </Button>
          </form>

          <div className="text-center">
            <Link
              to="/login"
              className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700"
            >
              <ArrowLeft className="w-3 h-3" />
              Back to login
            </Link>
          </div>
        </div>

        {/* Trust signal */}
        <p className="text-center text-xs text-navy-300">
          Encrypted at rest and in transit · Attorney work product protected
        </p>
      </div>
    </div>
  );
}
