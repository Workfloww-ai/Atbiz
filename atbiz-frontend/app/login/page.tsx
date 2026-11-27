"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/src/context/AuthContext";
import {
  Lock,
  Mail,
  Eye,
  EyeOff,
  Building2,
  KeyRound,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  ShieldCheck,
} from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { user, profile, loading, login, logout, changePassword } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Forced First-Time Password Change Mode
  const [mustReset, setMustReset] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [resetSuccess, setResetSuccess] = useState(false);

  // Module Access Restricted State (User has 0 assigned modules)
  const [hasNoModuleAccess, setHasNoModuleAccess] = useState(false);

  const checkUserHasModuleAccess = (p: any): boolean => {
    if (!p) return false;
    if (
      p.account_tier === "developer" ||
      p.account_tier === "tenant_super_admin" ||
      p.account_tier === "tenant_admin"
    ) {
      return true;
    }
    const modules = p.assigned_modules || [];
    return modules.length > 0;
  };

  // If already logged in and no password change needed, redirect or show restricted state
  useEffect(() => {
    if (!loading && user && profile) {
      if (profile.must_change_password) {
        setMustReset(true);
      } else {
        if (checkUserHasModuleAccess(profile)) {
          router.push("/resume-desk");
        } else {
          setHasNoModuleAccess(true);
        }
      }
    }
  }, [loading, user, profile, router]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setHasNoModuleAccess(false);
    setIsSubmitting(true);

    try {
      const res = await login(email, password);
      if (res.error) {
        setErrorMessage(res.error);
        setIsSubmitting(false);
        return;
      }

      if (res.mustChangePassword) {
        setMustReset(true);
      } else {
        const hasAccess = checkUserHasModuleAccess(res.profile);
        if (hasAccess) {
          router.push("/resume-desk");
        } else {
          setHasNoModuleAccess(true);
        }
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to sign in. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (newPassword.length < 6) {
      setErrorMessage("New password must be at least 6 characters.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await changePassword(newPassword);
      if (res.error) {
        setErrorMessage(res.error);
        setIsSubmitting(false);
        return;
      }

      setResetSuccess(true);
      setTimeout(() => {
        if (checkUserHasModuleAccess(profile)) {
          router.push("/resume-desk");
        } else {
          setMustReset(false);
          setHasNoModuleAccess(true);
        }
      }, 1200);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to update password.");
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-800 flex flex-col justify-center items-center p-4 relative">
      {/* Top Header Brand Bar */}
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl shadow-xl shadow-slate-200/60 p-8 relative z-10">
        {/* Back to Welcome Page Button */}
        <div className="mb-4">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-900 transition-colors py-1.5 px-2.5 -ml-2 rounded-lg hover:bg-slate-100/80 cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Welcome Page</span>
          </Link>
        </div>

        {/* Brand Header */}
        <div className="flex flex-col items-center mb-7 text-center">
          <div className="w-12 h-12 rounded-xl bg-slate-900 flex items-center justify-center text-white shadow-xs mb-3.5">
            <Building2 className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">AT BiZ Platform</h1>
          <p className="text-xs text-slate-500 mt-1 font-medium">
            Enterprise Workforce & Operational Management
          </p>
        </div>

        {/* Error notification (matches dashboard rose alert) */}
        {errorMessage && (
          <div className="mb-5 p-3 rounded-lg bg-[#fce7e7] border border-[#fca5a5] text-[#991b1b] text-xs flex items-start gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-[#991b1b]" />
            <span className="font-medium">{errorMessage}</span>
          </div>
        )}

        {/* Access Restricted Mode (No modules assigned) */}
        {hasNoModuleAccess ? (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-950">
              <div className="flex items-center gap-2 font-bold text-xs text-amber-950">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                <span>Workspace Permission Required</span>
              </div>
              <p className="text-xs text-amber-900 mt-2 leading-relaxed">
                Your account ({user?.email || profile?.email || email}) has been verified, but your organization administrator has not assigned any workspace modules (e.g. Hiring Pipeline, Resume Desk, Attendance) to your account yet.
              </p>
              <p className="text-[11px] text-amber-800 mt-2">
                Please contact your workspace administrator or HR Operations manager to assign you module permissions in <strong>Team Management</strong>.
              </p>
            </div>

            <div className="flex flex-col gap-2 pt-2">
              <button
                type="button"
                onClick={() => router.push("/")}
                className="w-full bg-slate-900 hover:bg-black text-white font-semibold py-2.5 px-4 rounded-lg text-xs transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs"
              >
                <span>Back to Welcome Page</span>
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={async () => {
                  await logout();
                  setHasNoModuleAccess(false);
                  setEmail("");
                  setPassword("");
                }}
                className="w-full bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 font-medium py-2 px-4 rounded-lg text-xs transition cursor-pointer"
              >
                Sign In with Different Account
              </button>
            </div>
          </div>
        ) : mustReset ? (
          <div>
            <div className="mb-5 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-900">
              <div className="flex items-center gap-2 font-semibold text-xs text-amber-950">
                <KeyRound className="w-4 h-4 text-amber-600" />
                First-Time Sign In Required
              </div>
              <p className="text-[11px] text-amber-800 mt-1 leading-relaxed">
                For security, please replace your temporary password with a permanent one before entering the platform.
              </p>
            </div>

            {resetSuccess ? (
              <div className="p-6 text-center bg-emerald-50 border border-emerald-200 rounded-xl">
                <CheckCircle2 className="w-10 h-10 text-emerald-600 mx-auto mb-2" />
                <h3 className="text-sm font-bold text-emerald-950">Password Updated!</h3>
                <p className="text-xs text-emerald-700 mt-1">Redirecting to your dashboard...</p>
              </div>
            ) : (
              <form onSubmit={handlePasswordChange} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    New Permanent Password
                  </label>
                  <div className="relative">
                    <input
                      type={showNewPassword ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="At least 6 characters"
                      required
                      className="w-full bg-white border border-slate-300 rounded-lg px-3.5 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent transition"
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPassword(!showNewPassword)}
                      className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                    >
                      {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                    Confirm New Password
                  </label>
                  <input
                    type={showNewPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat new password"
                    required
                    className="w-full bg-white border border-slate-300 rounded-lg px-3.5 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent transition"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full mt-2 bg-slate-900 hover:bg-black text-white font-semibold py-2.5 px-4 rounded-lg text-xs transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs disabled:opacity-50"
                >
                  {isSubmitting ? "Updating..." : "Save Password & Continue"}
                  <ArrowRight className="w-4 h-4" />
                </button>
              </form>
            )}
          </div>
        ) : (
          /* 2. Standard Login Mode */
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Work Email Address
              </label>
              <div className="relative">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com"
                  required
                  autoComplete="email"
                  className="w-full bg-white border border-slate-300 rounded-lg pl-10 pr-3.5 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent transition shadow-2xs"
                />
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-2.5" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  autoComplete="current-password"
                  className="w-full bg-white border border-slate-300 rounded-lg pl-10 pr-10 py-2.5 text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-transparent transition shadow-2xs"
                />
                <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-2.5" />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full mt-3 bg-slate-900 hover:bg-black text-white font-semibold py-2.5 px-4 rounded-lg text-xs transition-all flex items-center justify-center gap-2 cursor-pointer shadow-xs disabled:opacity-50"
            >
              {isSubmitting ? "Signing in..." : "Sign in to AT BiZ"}
              <ArrowRight className="w-4 h-4" />
            </button>
          </form>
        )}

        <div className="mt-8 pt-5 border-t border-slate-100 flex items-center justify-center gap-1.5 text-center">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
          <p className="text-[11px] text-slate-500 font-medium">
            Secure multi-tenant workforce workspace
          </p>
        </div>
      </div>
    </div>
  );
}
