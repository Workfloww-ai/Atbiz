"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { supabase } from "@/src/lib/supabase";
import { User, Session } from "@supabase/supabase-js";

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  phone?: string;
  tenant_id?: string;
  tenant_name?: string;
  account_tier: "developer" | "tenant_super_admin" | "tenant_admin" | "tenant_user";
  role_name?: string;
  must_change_password: boolean;
  assigned_client_ids: string[];
  assigned_site_ids: string[];
  assigned_modules: string[];
}

interface AuthContextType {
  user: User | null;
  session: Session | null;
  profile: UserProfile | null;
  loading: boolean;
  isDeveloper: boolean;
  isSuperAdmin: boolean;
  isAdmin: boolean;
  canAccessClient: (clientId: string) => boolean;
  canAccessModule: (moduleId: string) => boolean;
  login: (email: string, password: string) => Promise<{ error?: string; mustChangePassword?: boolean }>;
  logout: () => Promise<void>;
  changePassword: (newPassword: string) => Promise<{ error?: string }>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchUserProfile = async (token: string, userId: string, userEmail: string): Promise<UserProfile | null> => {
    try {
      // Call backend /api/users/me with Bearer token
      const res = await fetch("/api/users/me", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (res.ok) {
        const data = await res.json();
        return data.user as UserProfile;
      }
    } catch (e) {
      console.warn("Failed to fetch user profile from API, falling back to database query:", e);
    }

    // Direct Supabase fallback if API is unreachable
    try {
      const { data: prof } = await supabase
        .from("profiles")
        .select("*")
        .eq("id", userId)
        .single();

      if (prof) {
        // Query assigned clients & modules
        const [cRes, mRes] = await Promise.all([
          supabase.from("user_client_assignments").select("client_id").eq("user_id", userId).eq("status", "active"),
          supabase.from("user_module_assignments").select("module_id").eq("user_id", userId),
        ]);

        return {
          id: userId,
          email: userEmail,
          full_name: prof.full_name || userEmail.split("@")[0],
          phone: prof.phone,
          tenant_id: prof.tenant_id,
          account_tier: prof.account_tier || "tenant_user",
          must_change_password: prof.must_change_password || false,
          assigned_client_ids: (cRes.data || []).map((r: any) => r.client_id),
          assigned_site_ids: [],
          assigned_modules: (mRes.data || []).map((r: any) => r.module_id),
        };
      }
    } catch (err) {
      console.error("Error reading profile directly from Supabase:", err);
    }

    // Default fallback profile
    return {
      id: userId,
      email: userEmail,
      full_name: userEmail.split("@")[0],
      account_tier: "tenant_user",
      must_change_password: false,
      assigned_client_ids: [],
      assigned_site_ids: [],
      assigned_modules: ["resume_desk", "pipeline"],
    };
  };

  const refreshProfile = async () => {
    if (!session || !user) return;
    const p = await fetchUserProfile(session.access_token, user.id, user.email || "");
    if (p) setProfile(p);
  };

  useEffect(() => {
    // 1. Check existing session
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      setSession(session);
      setUser(session?.user ?? null);
      if (session?.user) {
        const p = await fetchUserProfile(session.access_token, session.user.id, session.user.email || "");
        setProfile(p);
      }
      setLoading(false);
    });

    // 2. Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (_event, session) => {
      setSession(session);
      setUser(session?.user ?? null);
      if (session?.user) {
        const p = await fetchUserProfile(session.access_token, session.user.id, session.user.email || "");
        setProfile(p);
      } else {
        setProfile(null);
      }
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error) {
        return { error: error.message };
      }

      if (data.session && data.user) {
        setSession(data.session);
        setUser(data.user);
        const p = await fetchUserProfile(data.session.access_token, data.user.id, data.user.email || "");
        setProfile(p);
        return { mustChangePassword: p?.must_change_password ?? false };
      }

      return {};
    } catch (err: any) {
      return { error: err.message || "An unexpected error occurred during sign in." };
    }
  };

  const logout = async () => {
    await supabase.auth.signOut();
    setSession(null);
    setUser(null);
    setProfile(null);
  };

  const changePassword = async (newPassword: string) => {
    if (!session) return { error: "No active session." };
    try {
      // 1. Update in backend to clear must_change_password
      const res = await fetch("/api/users/change-password", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ new_password: newPassword }),
      });

      if (!res.ok) {
        const data = await res.json();
        return { error: data.detail || "Failed to update password." };
      }

      // 2. Also sync with client-side Supabase Auth
      await supabase.auth.updateUser({ password: newPassword });

      // 3. Update local state
      if (profile) {
        setProfile({ ...profile, must_change_password: false });
      }

      return {};
    } catch (err: any) {
      return { error: err.message || "Failed to change password." };
    }
  };

  const isDeveloper = profile?.account_tier === "developer";
  const isSuperAdmin = isDeveloper || profile?.account_tier === "tenant_super_admin";
  const isAdmin = isSuperAdmin || profile?.account_tier === "tenant_admin";

  const canAccessClient = (clientId: string) => {
    if (isAdmin) return true;
    return profile?.assigned_client_ids.includes(clientId) ?? false;
  };

  const canAccessModule = (moduleId: string) => {
    if (isAdmin) return true;
    // Normalize module key
    const cleanId = moduleId.toLowerCase().replace(/\s+/g, "_");
    return profile?.assigned_modules.includes(cleanId) ?? false;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        profile,
        loading,
        isDeveloper,
        isSuperAdmin,
        isAdmin,
        canAccessClient,
        canAccessModule,
        login,
        logout,
        changePassword,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
