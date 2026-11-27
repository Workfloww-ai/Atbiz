"use client";

import React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/src/context/AuthContext";
import {
  Building2,
  Lock,
  ArrowRight,
  ShieldCheck,
  LogOut,
} from "lucide-react";

export default function WelcomePage() {
  const router = useRouter();
  const {
    user,
    profile,
    loading: authLoading,
    logout,
    isAdmin,
    canAccessModule,
  } = useAuth();

  const hasAccess =
    isAdmin ||
    canAccessModule("resume_desk") ||
    canAccessModule("pipeline") ||
    ((profile?.assigned_modules?.length ?? 0) > 0);

  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-800 flex flex-col justify-between font-sans selection:bg-slate-900 selection:text-white">
      {/* Top Header */}
      <header className="w-full bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          {/* Brand Logo */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-slate-900 flex items-center justify-center text-white shadow-xs">
              <Building2 className="w-5 h-5 text-white" />
            </div>
            <div>
              <span className="font-bold text-base text-slate-900 tracking-tight">
                AT BiZ
              </span>
              <span className="text-[10px] uppercase font-semibold ml-2 px-1.5 py-0.2 bg-slate-100 text-slate-700 border border-slate-200 rounded">
                Enterprise
              </span>
            </div>
          </div>

          {/* Right Action */}
          <div>
            {authLoading ? (
              <div className="text-xs text-slate-400">Loading...</div>
            ) : user ? (
              <div className="flex items-center gap-3">
                <span className="text-xs font-semibold text-slate-900 hidden sm:inline">
                  {profile?.full_name || user.email?.split("@")[0]}
                </span>
                <Link
                  href={hasAccess ? "/resume-desk" : "/login"}
                  className="px-3.5 py-1.5 text-xs font-semibold bg-slate-900 hover:bg-black text-white rounded transition shadow-xs flex items-center gap-1.5"
                >
                  <span>Enter Portal</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </Link>
                <button
                  type="button"
                  onClick={() => logout()}
                  className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded transition cursor-pointer"
                  title="Sign Out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="px-4 py-1.5 text-xs font-semibold bg-slate-900 hover:bg-black text-white rounded transition shadow-xs flex items-center gap-1.5"
              >
                <Lock className="w-3.5 h-3.5" />
                <span>Sign In</span>
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Main Welcome Hero */}
      <main className="flex-1 flex items-center justify-center px-4 py-16">
        <div className="max-w-xl w-full text-center">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-slate-100 border border-slate-200 text-slate-700 text-xs font-medium mb-6 shadow-2xs">
            <ShieldCheck className="w-3.5 h-3.5 text-slate-800" />
            <span>Authorized Personnel Only</span>
          </div>

          {/* Heading */}
          <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Welcome to AT BiZ
          </h1>

          {/* Subtitle */}
          <p className="mt-3 text-sm sm:text-base text-slate-600 max-w-md mx-auto leading-relaxed">
            Enterprise Workforce Solutions & Operational Management Portal.
          </p>
          <p className="mt-1 text-xs text-slate-400 max-w-sm mx-auto">
            Please sign in to access your organization workspace and services.
          </p>

          {/* Action Button */}
          <div className="mt-8 flex justify-center">
            {authLoading ? (
              <div className="text-xs text-slate-400">Verifying session...</div>
            ) : user ? (
              <Link
                href={hasAccess ? "/resume-desk" : "/login"}
                className="px-6 py-3 bg-slate-900 hover:bg-black text-white font-semibold text-xs rounded-lg transition shadow-md flex items-center justify-center gap-2"
              >
                <span>Enter Workspace</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
            ) : (
              <Link
                href="/login"
                className="px-6 py-3 bg-slate-900 hover:bg-black text-white font-semibold text-xs rounded-lg transition shadow-md flex items-center justify-center gap-2"
              >
                <Lock className="w-4 h-4" />
                <span>Sign In to Portal</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
            )}
          </div>
        </div>
      </main>

      {/* Clean Minimal Footer */}
      <footer className="border-t border-slate-200 bg-white py-5">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-slate-600" />
            <span className="font-medium text-slate-700">AT BiZ Workforce Solutions Ltd.</span>
          </div>
          <div>
            <span>Enterprise Security & Role-Based Access Control</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
