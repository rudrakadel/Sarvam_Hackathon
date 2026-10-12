/**
 * VeriDictum AI — Login Page (UC-02)
 */

import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Shield, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { authApi, apiClient } from "@/services/api";
import { useAuthStore } from "@/store/authStore";
import type { TokenResponse, User } from "@/types";

const schema = z.object({
  email: z.string().email("Valid email required"),
  password: z.string().min(1, "Password required"),
  totp_code: z.string().optional(),
});

type FormData = z.infer<typeof schema>;

export function LoginPage() {
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuthStore();
  const [showPassword, setShowPassword] = useState(false);
  const [mfaRequired, setMfaRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormData) => {
    setError(null);
    try {
      const res = await authApi.login(data);
      const tokens = res.data as TokenResponse;
      setTokens(tokens.access_token, tokens.refresh_token);
      try {
        const profileRes = await apiClient.get("/users/me", {
          headers: { Authorization: `Bearer ${tokens.access_token}` },
        });
        setUser(profileRes.data as User);
      } catch {
        // non-fatal: settings page will show limited UI
      }
      navigate("/dashboard");
    } catch (err: unknown) {
      const e = err as { response?: { status: number; data: { detail: string } } };
      if (e.response?.data?.detail === "MFA_REQUIRED") {
        setMfaRequired(true);
      } else {
        setError(e.response?.data?.detail || "Login failed. Please try again.");
      }
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-navy-600 to-navy-800 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-gold-500 mb-4 shadow-lg">
            <Shield className="w-9 h-9 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Sarvam Nyaya</h1>
          <p className="text-navy-200 text-sm mt-1">Courtroom Intelligence Platform</p>
        </div>

        {/* Card */}
        <div className="bg-white dark:bg-navy-800 dark:border dark:border-navy-700 rounded-2xl shadow-2xl p-8">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-6">Sign In</h2>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 text-red-700 dark:text-red-300 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <Input
              label="Email Address"
              type="email"
              placeholder="attorney@firm.com"
              error={errors.email?.message}
              required
              {...register("email")}
            />

            <div className="relative">
              <Input
                label="Password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••••••"
                error={errors.password?.message}
                required
                {...register("password")}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-8 text-gray-400 hover:text-gray-600"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>

            {mfaRequired && (
              <Input
                label="Authenticator Code"
                type="text"
                placeholder="000000"
                maxLength={6}
                hint="Enter the 6-digit code from your authenticator app"
                error={errors.totp_code?.message}
                required
                {...register("totp_code")}
              />
            )}

            <div className="flex justify-end">
              <Link to="/forgot-password" className="text-sm text-navy-600 hover:text-navy-700 hover:underline">
                Forgot password?
              </Link>
            </div>

            <Button type="submit" fullWidth loading={isSubmitting} size="lg">
              Sign In
            </Button>
          </form>

          <p className="text-center text-sm text-gray-600 dark:text-gray-400 mt-6">
            Don't have an account?{" "}
            <Link to="/register" className="text-navy-600 dark:text-gold-400 font-medium hover:underline">
              Sign up
            </Link>
          </p>
        </div>

        <p className="text-center text-navy-300 text-xs mt-6">
          Encrypted at rest and in transit · Privileged work product · Authorized access only
        </p>
      </div>
    </div>
  );
}
