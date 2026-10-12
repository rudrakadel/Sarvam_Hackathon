/**
 * VeriDictum AI — Settings Page (UC-10, UC-12)
 * User profile, password change, MFA management, active sessions.
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient, useQuery } from "@tanstack/react-query";
import { User, Lock, Shield, Monitor, Eye, EyeOff, CheckCircle, Copy } from "lucide-react";
import toast from "react-hot-toast";
import { authApi } from "@/services/api";
import { useAuthStore } from "@/store/authStore";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { parseUserAgent } from "@/utils/format";
import type { User as UserType } from "@/types";

// ─── Profile Tab ─────────────────────────────────────────────────────────────

const profileSchema = z.object({
  full_name: z.string().min(2, "Name required"),
  phone: z.string().optional(),
});
type ProfileData = z.infer<typeof profileSchema>;

function ProfileTab({ user }: { user: UserType }) {
  const { setUser } = useAuthStore();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ProfileData>({
    resolver: zodResolver(profileSchema),
    defaultValues: { full_name: user.full_name, phone: user.phone ?? "" },
  });

  const mutation = useMutation({
    mutationFn: (data: ProfileData) => authApi.updateProfile(user.id, data),
    onSuccess: (res) => {
      setUser(res.data as UserType);
      toast.success("Profile saved successfully.");
    },
    onError: () => toast.error("Failed to save profile. Please try again."),
  });

  return (
    <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Full Name"
          error={errors.full_name?.message}
          required
          {...register("full_name")}
        />
        <Input
          label="Phone (optional)"
          placeholder="+1 555 123 4567"
          {...register("phone")}
        />
      </div>
      <div>
        <label className="text-sm font-medium text-gray-700 block mb-1">Email address</label>
        <p className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2">
          {user.email}
        </p>
        <p className="text-xs text-gray-400 mt-1">Email changes require support.</p>
      </div>
      <div>
        <label className="text-sm font-medium text-gray-700 block mb-1">Role</label>
        <p className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 capitalize">
          {user.role.charAt(0).toUpperCase() + user.role.slice(1).toLowerCase()}
        </p>
      </div>
      {mutation.isSuccess && (
        <p className="text-sm text-green-600 flex items-center gap-1.5">
          <CheckCircle className="w-4 h-4" /> Profile saved.
        </p>
      )}
      {mutation.isError && (
        <p className="text-sm text-red-600">Failed to save profile. Please try again.</p>
      )}
      <Button type="submit" loading={mutation.isPending}>
        Save Changes
      </Button>
    </form>
  );
}

// ─── Password Tab ─────────────────────────────────────────────────────────────

const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Required"),
    new_password: z
      .string()
      .min(12, "At least 12 characters")
      .regex(/[A-Z]/, "Must contain uppercase")
      .regex(/[a-z]/, "Must contain lowercase")
      .regex(/[0-9]/, "Must contain a number")
      .regex(/[^A-Za-z0-9]/, "Must contain a special character"),
    confirm: z.string(),
  })
  .refine((d) => d.new_password === d.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  });
type PasswordData = z.infer<typeof passwordSchema>;

function PasswordTab() {
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PasswordData>({ resolver: zodResolver(passwordSchema) });

  const mutation = useMutation({
    mutationFn: (data: PasswordData) =>
      authApi.changePassword(data.current_password, data.new_password),
    onSuccess: () => {
      reset();
      toast.success("Password updated successfully.");
    },
    onError: () => toast.error("Incorrect current password or server error."),
  });

  return (
    <form onSubmit={handleSubmit((d) => mutation.mutate(d))} className="space-y-5 max-w-md">
      <div className="relative">
        <Input
          label="Current password"
          type={showCurrent ? "text" : "password"}
          error={errors.current_password?.message}
          {...register("current_password")}
        />
        <button
          type="button"
          onClick={() => setShowCurrent((v) => !v)}
          className="absolute right-3 top-8 text-gray-400"
          tabIndex={-1}
        >
          {showCurrent ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
      <div className="relative">
        <Input
          label="New password"
          type={showNew ? "text" : "password"}
          error={errors.new_password?.message}
          hint="Min 12 chars, uppercase, lowercase, number & symbol"
          {...register("new_password")}
        />
        <button
          type="button"
          onClick={() => setShowNew((v) => !v)}
          className="absolute right-3 top-8 text-gray-400"
          tabIndex={-1}
        >
          {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
      <Input
        label="Confirm new password"
        type="password"
        error={errors.confirm?.message}
        {...register("confirm")}
      />
      {mutation.isSuccess && (
        <p className="text-sm text-green-600 flex items-center gap-1.5">
          <CheckCircle className="w-4 h-4" /> Password updated successfully.
        </p>
      )}
      {mutation.isError && (
        <p className="text-sm text-red-600">Incorrect current password or server error.</p>
      )}
      <Button type="submit" loading={mutation.isPending}>
        <Lock className="w-4 h-4" /> Update Password
      </Button>
    </form>
  );
}

// ─── MFA Tab ──────────────────────────────────────────────────────────────────

function MFATab({ user }: { user: UserType }) {
  const [step, setStep] = useState<"idle" | "setup" | "done">("idle");
  const [qrCode, setQrCode] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);
  const [backupCodes, setBackupCodes] = useState<string[]>([]);
  const [otp, setOtp] = useState("");
  const [copied, setCopied] = useState(false);

  const setupMutation = useMutation({
    mutationFn: () => authApi.setupMFA(),
    onSuccess: (res) => {
      setQrCode(res.data.qr_code_base64);
      setSecret(res.data.secret);
      setStep("setup");
    },
  });

  const confirmMutation = useMutation({
    mutationFn: () => authApi.confirmMFA(otp),
    onSuccess: (res) => {
      setBackupCodes(res.data.backup_codes ?? []);
      setStep("done");
    },
  });

  // Disabling MFA requires a fresh TOTP code (defence against an attacker
  // who hijacks a session and tries to drop the second factor). The flow is:
  // click "Disable MFA" → inline input asking for the 6-digit code → submit.
  const [disableCode, setDisableCode] = useState("");
  const [showDisableForm, setShowDisableForm] = useState(false);
  const disableMutation = useMutation({
    mutationFn: (code: string) => authApi.disableMFA(code),
    onSuccess: () => {
      setShowDisableForm(false);
      setDisableCode("");
    },
  });

  const copySecret = () => {
    if (secret) {
      navigator.clipboard.writeText(secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (user.mfa_enabled && step === "idle") {
    return (
      <div className="space-y-5 max-w-md">
        <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-lg">
          <Shield className="w-5 h-5 text-green-600 flex-shrink-0" />
          <div>
            <p className="text-sm font-medium text-green-800">MFA is enabled</p>
            <p className="text-xs text-green-700">
              Your account is protected with an authenticator app.
            </p>
          </div>
        </div>
        {disableMutation.isSuccess ? (
          <p className="text-sm text-amber-600">MFA disabled. Please refresh the page.</p>
        ) : showDisableForm ? (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (disableCode.trim().length === 6) {
                disableMutation.mutate(disableCode.trim());
              }
            }}
          >
            <Input
              label="Authenticator code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="000000"
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, ""))}
              hint="Enter the 6-digit code from your authenticator to confirm."
              required
            />
            {disableMutation.isError && (
              <p className="text-xs text-red-600 dark:text-red-400">
                Code rejected. Try again with the latest code from your authenticator.
              </p>
            )}
            <div className="flex gap-2">
              <Button
                type="submit"
                variant="danger"
                loading={disableMutation.isPending}
                disabled={disableCode.length !== 6}
              >
                Confirm disable
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setShowDisableForm(false);
                  setDisableCode("");
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <Button
            variant="danger"
            onClick={() => setShowDisableForm(true)}
          >
            Disable MFA
          </Button>
        )}
      </div>
    );
  }

  if (step === "done") {
    return (
      <div className="space-y-5 max-w-md">
        <div className="flex items-center gap-3 p-4 bg-green-50 border border-green-200 rounded-lg">
          <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
          <p className="text-sm font-medium text-green-800">MFA enabled successfully!</p>
        </div>
        {backupCodes.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-semibold text-gray-700">
              Save your backup codes
            </p>
            <p className="text-xs text-gray-500">
              Each code can only be used once. Store them in a secure location.
            </p>
            <div className="grid grid-cols-2 gap-1.5 font-mono text-xs bg-gray-50 border border-gray-200 rounded-lg p-3">
              {backupCodes.map((c) => (
                <span key={c} className="py-0.5 text-gray-700">{c}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (step === "setup" && qrCode) {
    return (
      <div className="space-y-5 max-w-md">
        <div>
          <p className="text-sm font-semibold text-gray-800 mb-1">
            1. Scan this QR code with your authenticator app
          </p>
          <img
            src={`data:image/png;base64,${qrCode}`}
            alt="MFA QR code"
            className="w-48 h-48 border border-gray-200 rounded-lg"
          />
        </div>
        {secret && (
          <div>
            <p className="text-xs text-gray-500 mb-1">Or enter the secret manually:</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs bg-gray-100 rounded px-2 py-1.5 font-mono break-all">
                {secret}
              </code>
              <button
                onClick={copySecret}
                className="p-1.5 text-gray-400 hover:text-gray-600"
                title="Copy secret"
              >
                {copied ? <CheckCircle className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </div>
        )}
        <div>
          <p className="text-sm font-semibold text-gray-800 mb-2">
            2. Enter the 6-digit code from your app
          </p>
          <div className="flex gap-3">
            <input
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
              placeholder="000000"
              maxLength={6}
              className="w-36 text-center text-lg font-mono tracking-widest border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-navy-500"
            />
            <Button
              loading={confirmMutation.isPending}
              disabled={otp.length !== 6}
              onClick={() => confirmMutation.mutate()}
            >
              Verify & Enable
            </Button>
          </div>
          {confirmMutation.isError && (
            <p className="text-sm text-red-600 mt-2">Invalid code. Please try again.</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-md">
      <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
        <p className="text-sm font-medium text-amber-800">MFA is not enabled</p>
        <p className="text-xs text-amber-700 mt-1">
          Enable multi-factor authentication to add an extra layer of security to your account.
        </p>
      </div>
      <Button loading={setupMutation.isPending} onClick={() => setupMutation.mutate()}>
        <Shield className="w-4 h-4" /> Enable MFA
      </Button>
    </div>
  );
}

// ─── Sessions Tab ─────────────────────────────────────────────────────────────

function SessionsTab() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => authApi.listSessions(),
  });

  const revokeMutation = useMutation({
    mutationFn: (tokenId: string) => authApi.revokeSession(tokenId),
    onSuccess: () => {
      toast.success("Session revoked.");
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: () => toast.error("Failed to revoke session."),
  });

  const revokeAllMutation = useMutation({
    mutationFn: async () => {
      const sessions = (data?.data as any[]) ?? [];
      // Revoke all sessions except the first (current)
      const others = sessions.slice(1);
      await Promise.all(others.map((s: any) => authApi.revokeSession(s.id)));
    },
    onSuccess: () => {
      toast.success("All other sessions revoked.");
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: () => toast.error("Failed to revoke sessions."),
  });

  const sessions = (data?.data as any[]) ?? [];

  return (
    <div className="space-y-4 max-w-2xl">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          These are all your active login sessions. Revoke any you don't recognise.
        </p>
        {sessions.length > 1 && (
          <Button
            size="sm"
            variant="outline"
            loading={revokeAllMutation.isPending}
            onClick={() => revokeAllMutation.mutate()}
          >
            Revoke all other sessions
          </Button>
        )}
      </div>
      {isLoading ? (
        <div className="animate-pulse space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-14 bg-gray-100 rounded-lg" />
          ))}
        </div>
      ) : sessions.length === 0 ? (
        <p className="text-sm text-gray-400">No active sessions found.</p>
      ) : (
        <div className="divide-y divide-gray-100 border border-gray-100 rounded-xl overflow-hidden">
          {sessions.map((session: any, idx: number) => {
            const deviceLabel = parseUserAgent(session.device_info ?? session.user_agent);
            const isCurrentSession = idx === 0; // Most recently created = current
            return (
              <div key={session.id} className="flex items-center justify-between px-4 py-3 bg-white hover:bg-gray-50">
                <div className="flex items-center gap-3">
                  <Monitor className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="text-sm text-gray-800 font-medium">
                        {deviceLabel}
                      </p>
                      {isCurrentSession && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 font-medium">
                          Current session
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 mt-0.5">
                      {session.created_at
                        ? `Started ${new Date(session.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })} · `
                        : ""}
                      Expires {new Date(session.expires_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                    </p>
                  </div>
                </div>
                {!isCurrentSession && (
                  <Button
                    size="sm"
                    variant="ghost"
                    loading={revokeMutation.isPending}
                    onClick={() => revokeMutation.mutate(session.id)}
                  >
                    Revoke
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const TABS = [
  { id: "profile", label: "Profile", icon: User },
  { id: "password", label: "Password", icon: Lock },
  { id: "mfa", label: "Two-Factor Auth", icon: Shield },
  { id: "sessions", label: "Sessions", icon: Monitor },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function SettingsPage() {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<TabId>("profile");

  if (!user) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Account Settings</h1>
          <p className="text-gray-500 text-sm mt-1">
            Manage your profile, security, and active sessions.
          </p>
        </div>
        <div className="flex gap-6">
          {/* Sidebar skeleton */}
          <div className="w-48 flex-shrink-0 bg-gray-50 rounded-xl border border-gray-100 p-2 space-y-1">
            {TABS.map(({ id, label }) => (
              <div key={id} className="h-9 bg-gray-100 animate-pulse rounded-lg" aria-label={label} />
            ))}
          </div>
          {/* Content skeleton */}
          <div className="flex-1 bg-white rounded-xl border border-gray-100 shadow-sm p-6 space-y-4">
            <p className="text-sm text-gray-500">Loading your account settings…</p>
            <div className="h-6 w-40 bg-gray-100 animate-pulse rounded" />
            <div className="h-10 bg-gray-100 animate-pulse rounded-lg" />
            <div className="h-10 bg-gray-100 animate-pulse rounded-lg" />
            <div className="h-10 bg-gray-100 animate-pulse rounded-lg" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Account Settings</h1>
        <p className="text-gray-500 text-sm mt-1">
          Manage your profile, security, and active sessions.
        </p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar nav — distinct bg to differentiate from main app nav */}
        <nav className="w-48 flex-shrink-0 bg-gray-50 rounded-xl border border-gray-100 p-2 space-y-1 self-start">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === id
                  ? "bg-white text-navy-700 shadow-sm border border-gray-100"
                  : "text-gray-600 hover:bg-white hover:text-gray-900"
              }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </nav>

        {/* Content panel */}
        <div className="flex-1 bg-white rounded-xl border border-gray-100 shadow-sm p-6">
          {activeTab === "profile" && <ProfileTab user={user} />}
          {activeTab === "password" && <PasswordTab />}
          {activeTab === "mfa" && <MFATab user={user} />}
          {activeTab === "sessions" && <SessionsTab />}
        </div>
      </div>
    </div>
  );
}
