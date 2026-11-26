"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  Users,
  UserPlus,
  Building2,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  KeyRound,
  Layers,
  RefreshCw,
  Briefcase,
  Settings2,
  Edit3,
  ShieldCheck,
} from "lucide-react";

interface TeamMember {
  id: string;
  email: string;
  full_name: string;
  phone?: string;
  account_tier: string;
  role_name?: string;
  tenant_name?: string;
  status: string;
  must_change_password: boolean;
  created_at: string;
  assigned_clients?: { id: string; name: string }[];
  assigned_modules?: string[];
}

interface TeamManagementModalProps {
  isOpen: boolean;
  onClose: () => void;
  token?: string;
  tenantId?: string;
  tenantName?: string;
  isDeveloper?: boolean;
  clients: { id: string; name: string }[];
  onPermissionsUpdated?: () => void;
}

const AVAILABLE_MODULES = [
  { id: "resume_desk", name: "Resume Desk", desc: "Resume intake, search & digital filters" },
  { id: "pipeline", name: "Pipeline", desc: "Recruitment stages & Kanban board" },
  { id: "attendance", name: "Attendance", desc: "Shift logs, biometrics & site muster" },
  { id: "onboarding", name: "Onboarding", desc: "Offer letters & document verification" },
  { id: "employees", name: "Employees", desc: "Active workforce & site allocations" },
  { id: "mis", name: "MIS & Reports", desc: "Analytics & operational reporting" },
];

export default function TeamManagementModal({
  isOpen,
  onClose,
  token,
  tenantId,
  tenantName,
  isDeveloper,
  clients,
  onPermissionsUpdated,
}: TeamManagementModalProps) {
  const [activeTab, setActiveTab] = useState<"members" | "add">("members");
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);

  // Edit Permissions State
  const [editingMember, setEditingMember] = useState<TeamMember | null>(null);
  const [editAccountTier, setEditAccountTier] = useState<string>("tenant_user");
  const [editRoleName, setEditRoleName] = useState<string>("Team Member");
  const [editSelectedClients, setEditSelectedClients] = useState<string[]>([]);
  const [editSelectedModules, setEditSelectedModules] = useState<string[]>([]);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editSuccess, setEditSuccess] = useState<string | null>(null);

  const handleStartEdit = (m: TeamMember) => {
    setEditingMember(m);
    setEditAccountTier(m.account_tier || "tenant_user");
    setEditRoleName(m.role_name || "Team Member");
    setEditSelectedClients((m.assigned_clients || []).map((c) => c.id));
    setEditSelectedModules(m.assigned_modules || []);
    setEditError(null);
    setEditSuccess(null);
  };

  const toggleEditModule = (modId: string) => {
    setEditSelectedModules((prev) =>
      prev.includes(modId) ? prev.filter((id) => id !== modId) : [...prev, modId]
    );
  };

  const toggleEditClient = (cid: string) => {
    setEditSelectedClients((prev) =>
      prev.includes(cid) ? prev.filter((id) => id !== cid) : [...prev, cid]
    );
  };

  const handleSavePermissions = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingMember) return;
    setEditSubmitting(true);
    setEditError(null);
    setEditSuccess(null);

    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch(`/api/users/${editingMember.id}/permissions`, {
        method: "PATCH",
        headers,
        body: JSON.stringify({
          account_tier: editAccountTier,
          role_name: editRoleName.trim() || "Team Member",
          client_ids: editSelectedClients,
          modules: editSelectedModules,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        setEditError(data.detail || "Failed to update permissions.");
        setEditSubmitting(false);
        return;
      }

      setEditSuccess("Permissions updated successfully!");
      fetchMembers();
      if (onPermissionsUpdated) onPermissionsUpdated();
      setTimeout(() => {
        setEditingMember(null);
        setEditSuccess(null);
      }, 1000);
    } catch (err: any) {
      setEditError(err.message || "An unexpected error occurred.");
    } finally {
      setEditSubmitting(false);
    }
  };

  // Available Tenants (For Developer tier)
  const [tenants, setTenants] = useState<{ id: string; name: string }[]>([]);
  const [selectedTenantId, setSelectedTenantId] = useState<string>(
    tenantId || "a0000000-0000-0000-0000-000000000001"
  );

  // Add User Form State
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [accountTier, setAccountTier] = useState<string>("tenant_user");
  const [roleName, setRoleName] = useState("Recruiter");
  const [selectedClients, setSelectedClients] = useState<string[]>([]);
  const [selectedModules, setSelectedModules] = useState<string[]>(["resume_desk", "pipeline"]);

  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Success state after inviting
  const [createdResult, setCreatedResult] = useState<{
    email: string;
    temporaryPassword: string;
    modules: string[];
  } | null>(null);
  const [copied, setCopied] = useState(false);

  // Fetch team members
  const fetchMembers = async () => {
    setLoadingMembers(true);
    try {
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch("/api/users", { headers });
      if (res.ok) {
        const data = await res.json();
        setMembers(data.users || []);
      }
    } catch (e) {
      console.error("Failed to fetch team members:", e);
    } finally {
      setLoadingMembers(false);
    }
  };

  // Fetch available tenants (especially for Developer)
  const fetchTenants = async () => {
    try {
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch("/api/users/tenants", { headers });
      if (res.ok) {
        const data = await res.json();
        const tList = data.tenants || [];
        setTenants(tList);
        if (tList.length > 0 && !selectedTenantId) {
          setSelectedTenantId(tList[0].id);
        }
      }
    } catch (e) {
      console.warn("Failed to fetch tenants:", e);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchMembers();
      fetchTenants();
      if (clients.length > 0 && selectedClients.length === 0) {
        setSelectedClients(clients.map((c) => c.id));
      }
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const toggleClient = (clientId: string) => {
    setSelectedClients((prev) =>
      prev.includes(clientId) ? prev.filter((id) => id !== clientId) : [...prev, clientId]
    );
  };

  const toggleSelectAllClients = () => {
    if (selectedClients.length === clients.length) {
      setSelectedClients([]);
    } else {
      setSelectedClients(clients.map((c) => c.id));
    }
  };

  const toggleModule = (moduleId: string) => {
    setSelectedModules((prev) =>
      prev.includes(moduleId) ? prev.filter((id) => id !== moduleId) : [...prev, moduleId]
    );
  };

  const handleCopyPassword = () => {
    if (!createdResult) return;
    navigator.clipboard.writeText(createdResult.temporaryPassword);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleAddUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (
      accountTier !== "tenant_admin" &&
      accountTier !== "tenant_super_admin" &&
      accountTier !== "developer" &&
      selectedClients.length === 0
    ) {
      setErrorMessage("Please assign at least one client to this team member.");
      return;
    }

    if (selectedModules.length === 0 && accountTier !== "developer") {
      setErrorMessage("Please select at least one module for this user.");
      return;
    }

    setSubmitting(true);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const res = await fetch("/api/users/invite", {
        method: "POST",
        headers,
        body: JSON.stringify({
          full_name: fullName,
          email,
          phone: phone || null,
          account_tier: accountTier,
          role_name: roleName.trim() || "Team Member",
          client_ids: selectedClients,
          modules: selectedModules,
          target_tenant_id:
            accountTier === "developer"
              ? null
              : selectedTenantId || tenantId || "a0000000-0000-0000-0000-000000000001",
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        setErrorMessage(data.detail || "Failed to provision user.");
        setSubmitting(false);
        return;
      }

      setCreatedResult({
        email: data.email,
        temporaryPassword: data.temporary_password,
        modules: data.modules,
      });

      setFullName("");
      setEmail("");
      setPhone("");
      fetchMembers();
    } catch (err: any) {
      setErrorMessage(err.message || "An unexpected error occurred.");
    } finally {
      setSubmitting(false);
    }
  };

  const formatTierBadge = (tier: string) => {
    switch (tier) {
      case "developer":
        return (
          <span className="bg-slate-900 text-white px-2 py-0.5 rounded text-[10px] font-medium tracking-tight">
            Developer
          </span>
        );
      case "tenant_super_admin":
        return (
          <span className="bg-slate-100 text-slate-800 border border-slate-200 px-2 py-0.5 rounded text-[10px] font-semibold">
            Super Admin
          </span>
        );
      case "tenant_admin":
        return (
          <span className="bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.5 rounded text-[10px] font-medium">
            Admin (HR Ops)
          </span>
        );
      default:
        return (
          <span className="text-slate-600 text-[11px] font-normal">
            Team Member
          </span>
        );
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-2xs">
      <div className="bg-white rounded-lg shadow-xl border border-slate-200 w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between bg-white">
          <div>
            <h2 className="text-sm font-semibold text-slate-900 tracking-tight">
              Team & Permissions
            </h2>
            <p className="text-[11px] text-slate-500 mt-0.5">
              {isDeveloper ? "Developer Mode (Cross-Tenant Admin)" : tenantName || "AT BiZ Workforce Solutions"} • Manage roles, client scope & modules
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Sub-Header Tabs */}
        <div className="flex border-b border-slate-200 px-5 bg-white gap-6">
          <button
            onClick={() => {
              setActiveTab("members");
              setCreatedResult(null);
            }}
            className={`py-2.5 text-xs flex items-center gap-2 border-b-2 transition cursor-pointer ${
              activeTab === "members"
                ? "border-slate-900 text-slate-900 font-semibold"
                : "border-transparent text-slate-500 hover:text-slate-800 font-medium"
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>Members</span>
            <span className="text-[10px] text-slate-400 bg-slate-100 px-1.5 py-0.2 rounded font-normal">
              {members.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab("add")}
            className={`py-2.5 text-xs flex items-center gap-2 border-b-2 transition cursor-pointer ${
              activeTab === "add"
                ? "border-slate-900 text-slate-900 font-semibold"
                : "border-transparent text-slate-500 hover:text-slate-800 font-medium"
            }`}
          >
            <UserPlus className="w-3.5 h-3.5" />
            <span>Add Member</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto flex-1">
          {/* TAB 1: MEMBERS ROSTER */}
          {activeTab === "members" && (
            <div>
              <div className="flex justify-between items-center mb-3">
                <span className="text-xs text-slate-500">
                  Accounts provisioned under this workspace
                </span>
                <button
                  onClick={fetchMembers}
                  className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded transition cursor-pointer"
                  title="Refresh Roster"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${loadingMembers ? "animate-spin text-slate-800" : ""}`} />
                </button>
              </div>

              {loadingMembers ? (
                <div className="py-12 text-center text-xs text-slate-400 font-normal">
                  Loading members...
                </div>
              ) : members.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400 font-normal">
                  No additional team members. Click &quot;Add Member&quot; to invite someone.
                </div>
              ) : (
                <div className="border border-slate-200 rounded-md overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-[#f8fafc] border-b border-slate-200 text-slate-500 text-[11px] font-medium">
                      <tr>
                        <th className="px-3.5 py-2">Name & Email</th>
                        <th className="px-3.5 py-2">Role & Title</th>
                        {isDeveloper && <th className="px-3.5 py-2">Tenant</th>}
                        <th className="px-3.5 py-2">Clients</th>
                        <th className="px-3.5 py-2">Modules</th>
                        <th className="px-3.5 py-2">Status</th>
                        <th className="px-3.5 py-2 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {members.map((m) => (
                        <tr key={m.id} className="hover:bg-slate-50/60 transition-colors">
                          <td className="px-3.5 py-2.5">
                            <div className="font-semibold text-slate-900">{m.full_name}</div>
                            <div className="text-[11px] text-slate-400">{m.email}</div>
                          </td>
                          <td className="px-3.5 py-2.5">
                            <div className="font-medium text-slate-800 text-xs">
                              {m.role_name || (m.account_tier === "developer" ? "System Developer" : "Team Member")}
                            </div>
                            <div className="mt-0.5">{formatTierBadge(m.account_tier)}</div>
                          </td>
                          {isDeveloper && (
                            <td className="px-3.5 py-2.5">
                              <span className="text-[11px] text-slate-600 font-medium">
                                {m.tenant_name || (m.account_tier === "developer" ? "Global (All Tenants)" : "Standard")}
                              </span>
                            </td>
                          )}
                          <td className="px-3.5 py-2.5">
                            {m.account_tier === "tenant_super_admin" || m.account_tier === "developer" ? (
                              <span className="text-[11px] text-slate-500 font-normal">
                                All Clients
                              </span>
                            ) : m.assigned_clients && m.assigned_clients.length > 0 ? (
                              <div className="flex flex-wrap gap-1 max-w-[180px]">
                                {m.assigned_clients.map((c) => (
                                  <span
                                    key={c.id}
                                    className="bg-slate-100 text-slate-700 border border-slate-200/60 px-1.5 py-0.5 rounded text-[10px]"
                                  >
                                    {c.name}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="text-[11px] text-slate-400">None</span>
                            )}
                          </td>
                          <td className="px-3.5 py-2.5">
                            {m.assigned_modules && m.assigned_modules.length > 0 ? (
                              <div className="flex flex-wrap gap-1 max-w-[160px]">
                                {m.assigned_modules.map((mod) => (
                                  <span
                                    key={mod}
                                    className="bg-slate-100 text-slate-700 border border-slate-200/60 px-1.5 py-0.5 rounded text-[10px]"
                                  >
                                    {mod.replace("_", " ")}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="text-[11px] text-slate-500 font-normal">All Modules</span>
                            )}
                          </td>
                          <td className="px-3.5 py-2.5">
                            {m.must_change_password ? (
                              <span className="inline-flex items-center gap-1.5 text-[11px] text-amber-700 font-medium">
                                <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                                Pending 1st Login
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 text-[11px] text-emerald-700 font-medium">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                                Active
                              </span>
                            )}
                          </td>
                          <td className="px-3.5 py-2.5 text-right whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() => handleStartEdit(m)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 border border-slate-200 rounded transition cursor-pointer"
                              title="Edit user role, clients and module permissions"
                            >
                              <Edit3 className="w-3 h-3 text-slate-500" />
                              <span>Edit Permissions</span>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Edit Permissions Modal Overlay */}
              {editingMember && (
                <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-2xs">
                  <div className="bg-white rounded-lg shadow-2xl border border-slate-200 w-full max-w-xl overflow-hidden flex flex-col max-h-[85vh]">
                    <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
                      <div>
                        <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                          <ShieldCheck className="w-4 h-4 text-slate-800" />
                          <span>Edit Permissions: {editingMember.full_name}</span>
                        </h3>
                        <p className="text-[11px] text-slate-500">{editingMember.email}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setEditingMember(null)}
                        className="p-1 text-slate-400 hover:text-slate-600 rounded transition cursor-pointer"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>

                    <form onSubmit={handleSavePermissions} className="p-5 overflow-y-auto space-y-4 flex-1">
                      {editError && (
                        <div className="p-2.5 bg-rose-50 border border-rose-200 text-rose-700 rounded text-xs flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
                          <span>{editError}</span>
                        </div>
                      )}
                      {editSuccess && (
                        <div className="p-2.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded text-xs flex items-center gap-2">
                          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                          <span>{editSuccess}</span>
                        </div>
                      )}

                      {/* Tier & Role */}
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">Access Level (Role Tier)</label>
                          <select
                            value={editAccountTier}
                            onChange={(e) => setEditAccountTier(e.target.value)}
                            className="w-full text-xs border border-slate-300 rounded px-2.5 py-1.5 text-slate-900 bg-white focus:outline-none focus:border-slate-900"
                          >
                            <option value="tenant_user">Team Member (Scoped Access)</option>
                            <option value="tenant_admin">Admin (HR Operations)</option>
                            {isDeveloper && (
                              <>
                                <option value="tenant_super_admin">Tenant Super Admin</option>
                                <option value="developer">Developer</option>
                              </>
                            )}
                          </select>
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">Role Title / Designation</label>
                          <input
                            type="text"
                            value={editRoleName}
                            onChange={(e) => setEditRoleName(e.target.value)}
                            className="w-full text-xs border border-slate-300 rounded px-2.5 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900"
                          />
                        </div>
                      </div>

                      {/* Modules Access */}
                      <div>
                        <label className="block text-xs font-bold text-slate-800 mb-1.5">
                          Assigned Modules (Permissions)
                        </label>
                        <div className="grid grid-cols-2 gap-2">
                          {AVAILABLE_MODULES.map((mod) => {
                            const isChecked = editSelectedModules.includes(mod.id);
                            return (
                              <div
                                key={mod.id}
                                onClick={() => toggleEditModule(mod.id)}
                                className={`p-2.5 border rounded cursor-pointer transition-all flex items-start gap-2 ${
                                  isChecked
                                    ? "border-slate-900 bg-slate-50 text-slate-900 shadow-2xs"
                                    : "border-slate-200 bg-white hover:border-slate-300 text-slate-600"
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  checked={isChecked}
                                  onChange={() => {}}
                                  className="mt-0.5 rounded border-slate-300 text-slate-900 focus:ring-0 cursor-pointer"
                                />
                                <div>
                                  <div className="font-semibold text-xs text-slate-900">{mod.name}</div>
                                  <div className="text-[10px] text-slate-400">{mod.desc}</div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      {/* Clients Access */}
                      {editAccountTier !== "developer" && (
                        <div>
                          <div className="flex items-center justify-between mb-1.5">
                            <label className="text-xs font-bold text-slate-800">Assigned Clients</label>
                            <button
                              type="button"
                              onClick={() => {
                                if (editSelectedClients.length === clients.length) {
                                  setEditSelectedClients([]);
                                } else {
                                  setEditSelectedClients(clients.map((c) => c.id));
                                }
                              }}
                              className="text-[11px] font-semibold text-slate-600 hover:text-slate-900 cursor-pointer"
                            >
                              {editSelectedClients.length === clients.length ? "Deselect All" : "Select All"}
                            </button>
                          </div>
                          <div className="grid grid-cols-2 gap-1.5 max-h-36 overflow-y-auto border border-slate-200 rounded p-2 bg-slate-50/50">
                            {clients.map((c) => {
                              const isSelected = editSelectedClients.includes(c.id);
                              return (
                                <label
                                  key={c.id}
                                  className={`flex items-center gap-2 px-2 py-1 rounded text-xs cursor-pointer ${
                                    isSelected ? "bg-white font-medium text-slate-900 shadow-2xs border border-slate-200" : "text-slate-600 hover:bg-slate-100"
                                  }`}
                                >
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => toggleEditClient(c.id)}
                                    className="rounded border-slate-300 text-slate-900 focus:ring-0"
                                  />
                                  <span className="truncate">{c.name}</span>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      <div className="pt-3 border-t border-slate-200 flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setEditingMember(null)}
                          className="px-3 py-1.5 text-xs font-medium border border-slate-300 rounded text-slate-700 hover:bg-slate-50 transition cursor-pointer"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          disabled={editSubmitting}
                          className="px-4 py-1.5 text-xs font-semibold bg-slate-900 hover:bg-black text-white rounded transition cursor-pointer disabled:opacity-50"
                        >
                          {editSubmitting ? "Saving..." : "Save Permissions"}
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: ADD MEMBER FORM */}
          {activeTab === "add" && (
            <div>
              {createdResult ? (
                <div className="p-5 border border-slate-200 bg-[#f8fafc] rounded-lg">
                  <div className="flex items-center gap-2.5 mb-2.5">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                    <div>
                      <h3 className="text-xs font-bold text-slate-900">Member Provisioned</h3>
                      <p className="text-[11px] text-slate-500">
                        Welcome email dispatched to <strong>{createdResult.email}</strong>.
                      </p>
                    </div>
                  </div>

                  <div className="bg-white border border-slate-200 rounded p-3 my-3">
                    <div className="text-[11px] text-slate-500 mb-1">Temporary Password:</div>
                    <div className="flex items-center justify-between">
                      <code className="text-xs font-bold font-mono text-slate-900 bg-slate-50 border border-slate-200 px-2 py-1 rounded">
                        {createdResult.temporaryPassword}
                      </code>
                      <button
                        onClick={handleCopyPassword}
                        className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-slate-900 hover:bg-black text-white rounded transition cursor-pointer"
                      >
                        {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                        {copied ? "Copied" : "Copy"}
                      </button>
                    </div>
                    <p className="text-[10px] text-slate-400 mt-2 flex items-center gap-1">
                      <KeyRound className="w-3 h-3 text-amber-600" />
                      User must change this password on their initial sign in.
                    </p>
                  </div>

                  <div className="flex justify-end gap-2 pt-1">
                    <button
                      onClick={() => setCreatedResult(null)}
                      className="px-3.5 py-1.5 text-xs font-semibold bg-slate-900 text-white rounded hover:bg-black transition cursor-pointer"
                    >
                      Add Another
                    </button>
                    <button
                      onClick={() => {
                        setCreatedResult(null);
                        setActiveTab("members");
                      }}
                      className="px-3.5 py-1.5 text-xs font-medium border border-slate-200 text-slate-700 rounded hover:bg-white transition cursor-pointer"
                    >
                      View All Members
                    </button>
                  </div>
                </div>
              ) : (
                <form onSubmit={handleAddUser} className="space-y-4">
                  {errorMessage && (
                    <div className="p-2.5 bg-[#fce7e7] border border-[#fca5a5] text-[#991b1b] rounded text-xs flex items-center gap-2">
                      <AlertCircle className="w-4 h-4 shrink-0 text-[#991b1b]" />
                      <span className="font-medium">{errorMessage}</span>
                    </div>
                  )}

                  {/* Row 1: Full Name & Email */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Full Name <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        placeholder="e.g. Ramesh Kumar"
                        required
                        className="w-full text-xs border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Work Email <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="ramesh@company.com"
                        required
                        className="w-full text-xs border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900"
                      />
                    </div>
                  </div>

                  {/* Row 2: Phone & Role Title / Designation */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Phone (Optional)
                      </label>
                      <input
                        type="tel"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        placeholder="+91 98765 43210"
                        className="w-full text-xs border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Role Title / Designation <span className="text-rose-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={roleName}
                        onChange={(e) => setRoleName(e.target.value)}
                        placeholder="e.g. Recruitment Lead, Operations Manager"
                        required
                        className="w-full text-xs border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900"
                      />
                    </div>
                  </div>

                  {/* Row 3: Role Tier & Organization/Tenant */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Access Level (Role Tier) <span className="text-rose-500">*</span>
                      </label>
                      <select
                        value={accountTier}
                        onChange={(e) => {
                          const tier = e.target.value;
                          setAccountTier(tier);
                          if (tier === "developer") {
                            setRoleName("System Developer");
                          } else if (tier === "tenant_super_admin") {
                            setRoleName("Super Admin / Director");
                          } else if (tier === "tenant_admin") {
                            setRoleName("HR Operations Manager");
                          } else {
                            setRoleName("Recruitment Specialist");
                          }
                        }}
                        className="w-full text-xs border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900 bg-white"
                      >
                        <option value="tenant_user">Team Member (Restricted to assigned clients)</option>
                        <option value="tenant_admin">Admin / HR Ops (Organization-wide management)</option>
                        {isDeveloper && (
                          <>
                            <option value="tenant_super_admin">Tenant Super Admin (Organization Owner)</option>
                            <option value="developer">Developer (Global Platform Access)</option>
                          </>
                        )}
                      </select>
                    </div>

                    {/* Developer: Tenant Selector */}
                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">
                        Target Organization / Tenant <span className="text-rose-500">*</span>
                      </label>
                      {accountTier === "developer" ? (
                        <div className="w-full text-xs border border-slate-200 bg-slate-50 text-slate-500 rounded px-3 py-1.5 font-medium">
                          Global (All Tenants)
                        </div>
                      ) : isDeveloper ? (
                        <select
                          value={selectedTenantId}
                          onChange={(e) => setSelectedTenantId(e.target.value)}
                          className="w-full text-xs border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900 bg-white"
                        >
                          {tenants.map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <div className="w-full text-xs border border-slate-200 bg-slate-50 text-slate-700 rounded px-3 py-1.5 font-medium truncate">
                          {tenantName || "AT BiZ Workforce Solutions Ltd."}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Client Scoping (Only if not Developer tier) */}
                  {accountTier !== "developer" && (
                    <div className="pt-2 border-t border-slate-200">
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-1.5">
                          <Building2 className="w-3.5 h-3.5 text-slate-600" />
                          <label className="text-xs font-bold text-slate-800">
                            Assigned Clients{" "}
                            {accountTier === "tenant_user" && (
                              <span className="text-rose-500">*</span>
                            )}
                          </label>
                        </div>
                        <button
                          type="button"
                          onClick={toggleSelectAllClients}
                          className="text-[11px] font-semibold text-slate-600 hover:text-slate-900 cursor-pointer"
                        >
                          {selectedClients.length === clients.length ? "Deselect All" : "Select All"}
                        </button>
                      </div>
                      <p className="text-[11px] text-slate-400 mb-2">
                        {accountTier === "tenant_admin" || accountTier === "tenant_super_admin"
                          ? "Admins automatically have access to all clients; you can also specify primary clients."
                          : "User will strictly see resumes and data for selected clients."}
                      </p>

                      <div className="grid grid-cols-2 gap-1.5 bg-slate-50 p-2.5 rounded border border-slate-200 max-h-28 overflow-y-auto">
                        {clients.map((c) => (
                          <label
                            key={c.id}
                            className="flex items-center gap-2 text-xs text-slate-800 p-1 hover:bg-white rounded transition cursor-pointer"
                          >
                            <input
                              type="checkbox"
                              checked={selectedClients.includes(c.id)}
                              onChange={() => toggleClient(c.id)}
                              className="rounded accent-slate-900 text-slate-900 focus:ring-slate-900"
                            />
                            <span className="truncate text-slate-700">{c.name}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Module Access (Only if not Developer tier) */}
                  {accountTier !== "developer" && (
                    <div className="pt-2 border-t border-slate-200">
                      <div className="flex items-center gap-1.5 mb-1.5">
                        <Layers className="w-3.5 h-3.5 text-slate-600" />
                        <label className="text-xs font-bold text-slate-800">
                          Module Access <span className="text-rose-500">*</span>
                        </label>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        {AVAILABLE_MODULES.map((m) => (
                          <label
                            key={m.id}
                            className={`flex items-start gap-2 p-2 rounded border text-xs cursor-pointer transition ${
                              selectedModules.includes(m.id)
                                ? "border-slate-900 bg-slate-50/75 text-slate-900 font-semibold"
                                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50/50"
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={selectedModules.includes(m.id)}
                              onChange={() => toggleModule(m.id)}
                              className="mt-0.5 rounded accent-slate-900 text-slate-900 focus:ring-slate-900"
                            />
                            <div>
                              <div className="font-semibold text-slate-900">{m.name}</div>
                              <div className="text-[10px] text-slate-500 font-normal">{m.desc}</div>
                            </div>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Footer Action Buttons */}
                  <div className="flex justify-end gap-2 pt-3 border-t border-slate-200">
                    <button
                      type="button"
                      onClick={() => setActiveTab("members")}
                      className="px-3.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded transition cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={submitting}
                      className="px-4 py-1.5 text-xs font-semibold bg-slate-900 hover:bg-black text-white rounded transition shadow-2xs cursor-pointer disabled:opacity-50"
                    >
                      {submitting ? "Inviting..." : "Send Invite"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
