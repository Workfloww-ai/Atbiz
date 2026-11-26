"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/src/context/AuthContext";
import TeamManagementModal from "@/src/components/TeamManagementModal";
import {
  Search,
  RefreshCw,
  Folder,
  Building2,
  ChevronDown,
  ChevronRight,
  Phone,
  Mail,
  MapPin,
  GraduationCap,
  FileText,
  AlertCircle,
  CheckCircle2,
  Download,
  Mic,
  ExternalLink,
  X,
  SlidersHorizontal,
  ChevronLeft,
  Calendar,
  Clock,
  Send,
  Plus,
  Kanban,
  LayoutGrid,
  GripVertical,
  Users,
  LogOut,
  ShieldCheck,
  KeyRound,
  Eye,
  EyeOff,
  Square,
} from "lucide-react";

interface RoleItem {
  name: string;
  count: number;
}

interface SiteItem {
  id: string;
  state: string;
  name: string;
  count: number;
  roles?: RoleItem[];
}

interface ClientItem {
  id: string;
  code: string;
  name: string;
  count: number;
  sites: SiteItem[];
}

interface CandidateNote {
  id: number;
  text: string;
  author: string;
  created_at: string;
}

interface Candidate {
  id: string;
  first_name: string;
  last_name: string | null;
  email: string | null;
  phone: string;
  dob: string | null;
  location: string | null;
  last_qualification: string | null;
  experience_years?: number | null;
  drive_folder_path: string | null;
  drive_file_id?: string | null;
  resume_url?: string | null;
  extracted_attributes: Record<string, any> | null;
  created_at: string;
  application_id?: string | null;
  stage?: string;
  app_status?: string;
  display_status?: string;
  flags?: string[];
  is_renamed?: boolean;
  notes?: CandidateNote[];
  comments_count?: number;
  ai_call_badge?: string;
  locations_present?: {
    client_id?: string;
    site_id?: string;
    client_name?: string;
    site_name?: string;
    role_name?: string;
    path?: string;
    file_id?: string;
  }[];
  is_multi_location?: boolean;
  contextual_role?: string;
  contextual_path?: string;
  contextual_site?: string;
  other_locations?: any[];
}

interface SyncStatus {
  is_scheduler_active: boolean;
  sync_interval_hours: number;
  last_synced_at: string | null;
  next_scheduled_sync: string | null;
  seconds_until_next_sync: number | null;
  total_candidates: number;
  total_scanned?: number;
  total_duplicates?: number;
  candidates_with_duplicates?: number;
  last_synced_resumes_count?: number;
}

const API_BASE = "";

const STATUS_OPTIONS = [
  { label: "New", color: "bg-slate-500", text: "text-slate-700" },
  { label: "Ready for AI Call", color: "bg-blue-500", text: "text-blue-700" },
  { label: "AI Call Initiated", color: "bg-amber-500", text: "text-amber-700" },
  { label: "Offer Sent", color: "bg-teal-500", text: "text-teal-700" },
  { label: "Accepted", color: "bg-indigo-600", text: "text-indigo-700" },
  { label: "Rejected", color: "bg-rose-500", text: "text-rose-700" },
];

const MODULE_OPTIONS = [
  { name: "Resume Desk", active: true },
  { name: "Pipeline", active: true },
  { name: "Rejected", active: false },
  { name: "Onboarding", active: false },
  { name: "Headcount", active: false },
  { name: "Employees", active: false },
  { name: "Exits", active: false },
  { name: "Attendance", active: false },
  { name: "MIS", active: false },
];

export default function ResumeDeskDashboard() {
  const router = useRouter();
  const {
    user,
    session,
    profile,
    loading: authLoading,
    logout,
    changePassword,
    isDeveloper,
    isSuperAdmin,
    isAdmin,
    canAccessClient,
    canAccessModule,
    refreshProfile,
  } = useAuth();

  // Route protection
  useEffect(() => {
    if (!authLoading) {
      if (!user) {
        router.push("/login");
      } else if (profile?.must_change_password) {
        router.push("/login");
      }
    }
  }, [authLoading, user, profile, router]);

  // Team Management & User Profile state
  const [teamModalOpen, setTeamModalOpen] = useState(false);
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);

  // Change Password state
  const [changePasswordModalOpen, setChangePasswordModalOpen] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [pwdError, setPwdError] = useState<string | null>(null);
  const [pwdSuccess, setPwdSuccess] = useState(false);
  const [pwdSubmitting, setPwdSubmitting] = useState(false);

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwdError(null);

    if (newPassword.length < 6) {
      setPwdError("New password must be at least 6 characters.");
      return;
    }

    if (newPassword !== confirmPassword) {
      setPwdError("Passwords do not match.");
      return;
    }

    setPwdSubmitting(true);
    try {
      const res = await changePassword(newPassword);
      if (res.error) {
        setPwdError(res.error);
        setPwdSubmitting(false);
        return;
      }

      setPwdSuccess(true);
      setTimeout(() => {
        setPwdSuccess(false);
        setNewPassword("");
        setConfirmPassword("");
        setChangePasswordModalOpen(false);
      }, 1400);
    } catch (err: any) {
      setPwdError(err.message || "Failed to update password.");
    } finally {
      setPwdSubmitting(false);
    }
  };

  // Navigation & View state
  const [activeTab, setActiveTab] = useState("Resume Desk");
  const [moduleDropdownOpen, setModuleDropdownOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Filters state
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [expandedClients, setExpandedClients] = useState<Record<string, boolean>>({});
  const [expandedSites, setExpandedSites] = useState<Record<string, boolean>>({});
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");

  // Pagination & Sorting state
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(10);
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  // Sort handler
  const handleSort = (column: string) => {
    if (sortBy === column) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortOrder("asc");
    }
    setPage(1);
  };

  // Selection state
  const [selectedCandidates, setSelectedCandidates] = useState<Record<string, boolean>>({});

  // Data state
  const [clientTree, setClientTree] = useState<ClientItem[]>([]);

  // Filter client tree based on user permissions
  const filteredClientTree = useMemo(() => {
    if (isAdmin) return clientTree;
    return clientTree.filter((client) => canAccessClient(client.id));
  }, [clientTree, isAdmin, canAccessClient]);

  // Clients list for Team Management
  const allClientsList = useMemo(() => {
    return clientTree.map((c) => ({ id: c.id, name: c.name }));
  }, [clientTree]);
  const [totalCount, setTotalCount] = useState(0);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [candidatesCount, setCandidatesCount] = useState(0);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);

  // Modals & Drawers
  const [activeCandidate, setActiveCandidate] = useState<Candidate | null>(null);
  const [notesModalCandidate, setNotesModalCandidate] = useState<Candidate | null>(null);
  const [newNoteText, setNewNoteText] = useState("");
  const [isSubmittingNote, setIsSubmittingNote] = useState(false);

  // Live Speech Recognition / Voice Dictation State (Web Speech API)
  const [isRecordingNote, setIsRecordingNote] = useState(false);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const recognitionRef = React.useRef<any>(null);

  // Pipeline Drag & Drop State
  const [draggedCandidateId, setDraggedCandidateId] = useState<string | null>(null);
  const [dragOverCol, setDragOverCol] = useState<string | null>(null);

  // 1. Fetch Hierarchy Tree & Sync Status
  const fetchMetaAndStatus = async () => {
    try {
      const [treeRes, statusRes] = await Promise.all([
        fetch(`${API_BASE}/api/candidates/meta/tree`),
        fetch(`${API_BASE}/api/ingest/status`),
      ]);
      if (treeRes.ok) {
        const treeData = await treeRes.json();
        setClientTree(treeData.tree || []);
        setTotalCount(treeData.total_count || 0);

        // Auto-expand all clients and sites initially
        const expClients: Record<string, boolean> = {};
        const expSites: Record<string, boolean> = {};
        (treeData.tree || []).forEach((c: ClientItem) => {
          expClients[c.id] = true;
          (c.sites || []).forEach((s: SiteItem) => {
            expSites[s.id] = true;
          });
        });
        setExpandedClients(expClients);
        setExpandedSites(expSites);
      }
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setSyncStatus(statusData);
      }
    } catch (err) {
      console.error("Error fetching metadata:", err);
    }
  };

  // 2. Fetch Candidates with active filters
  const fetchCandidates = async () => {
    setLoading(true);
    try {
      const isPipeline = activeTab === "Pipeline";
      const params = new URLSearchParams({
        page: isPipeline ? "1" : String(page),
        limit: isPipeline ? "250" : String(limit),
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      if (selectedClientId) params.append("client_id", selectedClientId);
      if (selectedSiteId) params.append("site_id", selectedSiteId);
      if (selectedRole) params.append("role", selectedRole);
      if (statusFilter && statusFilter !== "All") params.append("status", statusFilter);
      if (searchQuery.trim()) params.append("search", searchQuery.trim());

      const res = await fetch(`${API_BASE}/api/candidates?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setCandidates(data.data || []);
        setCandidatesCount(data.count || 0);
      }
    } catch (err) {
      console.error("Error fetching candidates:", err);
    } finally {
      setLoading(false);
    }
  };

  // 3. Update Status Handler
  const handleUpdateStatus = async (candidateId: string, newStatus: string) => {
    // Optimistic UI update
    setCandidates((prev) =>
      prev.map((c) => (c.id === candidateId ? { ...c, display_status: newStatus } : c))
    );
    if (activeCandidate && activeCandidate.id === candidateId) {
      setActiveCandidate((prev) => (prev ? { ...prev, display_status: newStatus } : null));
    }

    try {
      const res = await fetch(`${API_BASE}/api/candidates/${candidateId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) {
        console.error("Failed to update status on server");
        fetchCandidates();
      }
    } catch (err) {
      console.error("Error updating status:", err);
      fetchCandidates();
    }
  };

  // 4. Add Note Handler
  const handleAddNote = async (candidateId: string) => {
    if (!newNoteText.trim()) return;
    setIsSubmittingNote(true);
    try {
      const res = await fetch(`${API_BASE}/api/candidates/${candidateId}/notes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: newNoteText.trim(), author: "Recruiter" }),
      });
      if (res.ok) {
        const data = await res.json();
        setNewNoteText("");
        // Update local candidates
        setCandidates((prev) =>
          prev.map((c) =>
            c.id === candidateId
              ? { ...c, notes: data.notes, comments_count: data.comments_count }
              : c
          )
        );
        if (notesModalCandidate && notesModalCandidate.id === candidateId) {
          setNotesModalCandidate((prev) =>
            prev ? { ...prev, notes: data.notes, comments_count: data.comments_count } : null
          );
        }
        if (activeCandidate && activeCandidate.id === candidateId) {
          setActiveCandidate((prev) =>
            prev ? { ...prev, notes: data.notes, comments_count: data.comments_count } : null
          );
        }
      }
    } catch (err) {
      console.error("Error adding note:", err);
    } finally {
      setIsSubmittingNote(false);
    }
  };

  // Voice recording & Live Transcription methods (Web Speech API)
  const startVoiceRecording = () => {
    if (typeof window === "undefined") return;
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSpeechError(
        "Speech recognition is not supported in this browser. Please use Google Chrome or Microsoft Edge."
      );
      return;
    }

    setSpeechError(null);

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = "en-IN"; // English (India) with support for Indian accents
      recognition.continuous = true;
      recognition.interimResults = true;

      recognition.onstart = () => {
        setIsRecordingNote(true);
      };

      recognition.onresult = (event: any) => {
        let transcript = "";
        for (let i = 0; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        setNewNoteText(transcript);
      };

      recognition.onerror = (event: any) => {
        console.warn("Speech recognition notice:", event.error);
        if (event.error === "not-allowed") {
          setSpeechError("Microphone access was denied. Please allow microphone permissions in your browser.");
        } else if (event.error === "network") {
          setSpeechError("Network error during voice recognition. Check your connection.");
        } else if (event.error !== "no-speech") {
          setSpeechError(`Voice error: ${event.error}`);
        }
        setIsRecordingNote(false);
      };

      recognition.onend = () => {
        setIsRecordingNote(false);
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err: any) {
      console.error("Failed to start voice recognition:", err);
      setSpeechError(err.message || "Could not activate microphone.");
      setIsRecordingNote(false);
    }
  };

  const stopVoiceRecording = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch (e) {
        // Ignore
      }
      recognitionRef.current = null;
    }
    setIsRecordingNote(false);
  };

  const toggleVoiceRecording = () => {
    if (isRecordingNote) {
      stopVoiceRecording();
    } else {
      startVoiceRecording();
    }
  };

  // Stop recording when notes modal closes
  useEffect(() => {
    if (!notesModalCandidate && isRecordingNote) {
      stopVoiceRecording();
    }
    setSpeechError(null);
  }, [notesModalCandidate]);

  // 5. Trigger manual Google Drive sync
  const handleTriggerSync = async (force: boolean = false) => {
    setSyncing(true);
    setSyncNotice(null);
    try {
      const url = force ? `${API_BASE}/api/ingest/sync?force=true` : `${API_BASE}/api/ingest/sync`;
      const res = await fetch(url, { method: "POST" });
      if (res.status === 409) {
        setSyncNotice("Sync already active in background. Processing Google Drive resumes now...");
        // Poll for completion
        let checks = 0;
        const interval = setInterval(async () => {
          checks++;
          try {
            const statusRes = await fetch(`${API_BASE}/api/ingest/status`);
            if (statusRes.ok) {
              const data = await statusRes.json();
              setSyncStatus(data);
              if (!data.is_syncing || checks >= 8) {
                clearInterval(interval);
                setSyncing(false);
                setSyncNotice(null);
                fetchCandidates();
              }
            }
          } catch {
            if (checks >= 8) {
              clearInterval(interval);
              setSyncing(false);
              setSyncNotice(null);
            }
          }
        }, 3000);
        return;
      }
      if (res.ok) {
        setSyncNotice("Sync started! Scanning Drive folders for new resumes...");
        setTimeout(async () => {
          await fetchMetaAndStatus();
          await fetchCandidates();
          setSyncing(false);
          setSyncNotice(null);
        }, 4000);
      } else {
        const err = await res.json().catch(() => ({}));
        setSyncNotice(err.detail || "Sync could not be started.");
        setSyncing(false);
        setTimeout(() => setSyncNotice(null), 5000);
      }
    } catch (err) {
      console.error("Error triggering sync:", err);
      setSyncing(false);
    }
  };

  useEffect(() => {
    if (!authLoading && user && (isAdmin || canAccessModule("resume_desk"))) {
      fetchMetaAndStatus();
    }
  }, [authLoading, user, isAdmin]);

  useEffect(() => {
    if (!authLoading && user && (isAdmin || canAccessModule("resume_desk"))) {
      fetchCandidates();
    }
  }, [authLoading, user, isAdmin, selectedClientId, selectedSiteId, selectedRole, statusFilter, searchQuery, page, limit, sortBy, sortOrder, activeTab]);

  // Helper to determine the job role for which a candidate has applied
  const getCandidateJobRole = (c: Candidate): string => {
    if (c.contextual_role) return c.contextual_role;
    if (selectedClientId && c.locations_present && c.locations_present.length > 0) {
      const matchedRoles = Array.from(
        new Set(
          c.locations_present
            .filter((l) => l.client_id === selectedClientId)
            .map((l) => l.role_name?.trim())
            .filter(Boolean)
        )
      ) as string[];
      if (matchedRoles.length > 0) return matchedRoles.join(", ");
    }
    if (c.locations_present && c.locations_present.length > 0) {
      const roles = Array.from(
        new Set(c.locations_present.map((l) => l.role_name?.trim()).filter(Boolean))
      ) as string[];
      if (roles.length > 0) return roles.join(", ");
    }
    const pathParts = (c.drive_folder_path || "").replace(/^\/+/, "").split("/").filter(Boolean);
    if (pathParts.length >= 3 && pathParts[2]) {
      return pathParts[2].trim();
    }
    const attrs = c.extracted_attributes || {};
    const fallback = attrs.role || attrs.job_role || attrs.applied_role || attrs.position || selectedRole || "";
    return String(fallback).trim();
  };

  // Helper to determine the client company
  const getCandidateClient = (c: Candidate): string => {
    if (selectedClientId && c.locations_present && c.locations_present.length > 0) {
      const matched = c.locations_present.find((l) => l.client_id === selectedClientId);
      if (matched?.client_name) return matched.client_name;
    }
    if (c.locations_present && c.locations_present.length > 0) {
      const clients = Array.from(
        new Set(c.locations_present.map((l) => l.client_name?.trim()).filter(Boolean))
      ) as string[];
      if (clients.length > 0) return clients.join(", ");
    }
    const pathParts = (c.drive_folder_path || "").replace(/^\/+/, "").split("/").filter(Boolean);
    if (pathParts.length >= 1 && pathParts[0]) {
      return pathParts[0].trim();
    }
    return "";
  };

  // Helper to determine the site / location they were in or applied for
  const getCandidateAppliedLocation = (c: Candidate): string => {
    if (c.contextual_site) return c.contextual_site;
    if (selectedClientId && c.locations_present && c.locations_present.length > 0) {
      const matchedSites = Array.from(
        new Set(
          c.locations_present
            .filter((l) => l.client_id === selectedClientId)
            .map((l) => l.site_name?.trim())
            .filter(Boolean)
        )
      ) as string[];
      if (matchedSites.length > 0) return matchedSites.join(", ");
    }
    if (c.locations_present && c.locations_present.length > 0) {
      const sites = Array.from(
        new Set(c.locations_present.map((l) => l.site_name?.trim()).filter(Boolean))
      ) as string[];
      if (sites.length > 0) return sites.join(", ");
    }
    const pathParts = (c.drive_folder_path || "").replace(/^\/+/, "").split("/").filter(Boolean);
    if (pathParts.length >= 2 && pathParts[1]) {
      return pathParts[1].trim();
    }
    return c.location || "";
  };

  // Export current list to CSV
  const handleExportCSV = () => {
    const selectedCandidateList = candidates.filter((c) => selectedCandidates[c.id]);
    const exportCandidates = selectedCandidateList.length > 0 ? selectedCandidateList : candidates;
    if (!exportCandidates.length) return;

    const headers = [
      "Name",
      "Job Role",
      "Applied Location",
      "Client",
      "Candidate Location",
      "Phone",
      "Email",
      "Qualification",
      "Status",
      "Flags",
      "Folder Path",
      "Created At",
    ];

    const escapeCsv = (val: any) => `"${String(val ?? "").replace(/"/g, '""')}"`;

    const rows = exportCandidates.map((c) => {
      const role = getCandidateJobRole(c);
      const appliedLocation = getCandidateAppliedLocation(c);
      const client = getCandidateClient(c);
      const fullName = `${c.first_name || ""} ${c.last_name || ""}`.trim();
      return [
        escapeCsv(fullName),
        escapeCsv(role),
        escapeCsv(appliedLocation),
        escapeCsv(client),
        escapeCsv(c.location),
        escapeCsv(c.phone),
        escapeCsv(c.email),
        escapeCsv(c.last_qualification),
        escapeCsv(c.display_status || "New"),
        escapeCsv((c.flags || []).join(", ")),
        escapeCsv(c.drive_folder_path),
        escapeCsv(c.created_at),
      ];
    });

    // \uFEFF Byte Order Mark ensures Microsoft Excel displays UTF-8 characters correctly
    const csvContent = "\uFEFF" + [headers.join(","), ...rows.map((r) => r.join(","))].join("\r\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", `candidates_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  // Format date helper matching screenshot: "18 Nov 2026, 1:23 pm"
  const formatTime = (isoString?: string | null) => {
    if (!isoString) return "18 Nov 2026, 1:23 pm";
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "numeric",
        minute: "numeric",
        hour12: true,
      });
    } catch {
      return isoString;
    }
  };

  // Toggle client accordion
  const toggleClientExpand = (clientId: string) => {
    setExpandedClients((prev) => ({
      ...prev,
      [clientId]: !prev[clientId],
    }));
  };

  // Select all checkboxes handler
  const handleSelectAll = (checked: boolean) => {
    const updated: Record<string, boolean> = {};
    if (checked) {
      candidates.forEach((c) => {
        updated[c.id] = true;
      });
    }
    setSelectedCandidates(updated);
  };

  const selectedCount = Object.values(selectedCandidates).filter(Boolean).length;
  const totalPages = Math.ceil(candidatesCount / limit) || 1;

  // Selected scope name
  const currentScopeName = useMemo(() => {
    if (selectedSiteId) {
      for (const client of clientTree) {
        const found = client.sites.find((s) => s.id === selectedSiteId);
        if (found) return `${client.name} — ${found.name}`;
      }
    }
    if (selectedClientId) {
      const found = clientTree.find((c) => c.id === selectedClientId);
      if (found) return found.name;
    }
    return "All companies";
  }, [selectedClientId, selectedSiteId, clientTree]);

  // 1. Loading screen while authenticating
  if (authLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#f8fafc]">
        <div className="flex flex-col items-center gap-3 text-center">
          <RefreshCw className="w-6 h-6 animate-spin text-slate-800" />
          <p className="text-xs font-semibold text-slate-700">Authenticating access to Resume Desk...</p>
        </div>
      </div>
    );
  }

  // 2. Unauthenticated check
  if (!user) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#f8fafc]">
        <div className="flex flex-col items-center gap-3 text-center">
          <RefreshCw className="w-5 h-5 animate-spin text-slate-400" />
          <p className="text-xs text-slate-500">Redirecting to login...</p>
        </div>
      </div>
    );
  }

  // 3. Module permission check (Must have resume_desk or be admin/dev)
  const hasResumeDeskAccess = isAdmin || canAccessModule("resume_desk");
  if (!hasResumeDeskAccess) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-[#f8fafc] p-4">
        <div className="max-w-md w-full bg-white border border-slate-200 rounded-2xl p-8 text-center shadow-xl">
          <div className="w-12 h-12 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center mx-auto mb-4 text-amber-600">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <h2 className="text-base font-bold text-slate-900">Access Restricted</h2>
          <p className="text-xs text-slate-600 mt-2 leading-relaxed">
            You are signed in as <strong>{user.email}</strong>, but your account does not have permission to access the <strong>Resume Desk</strong> module.
          </p>
          <p className="text-[11px] text-slate-400 mt-2">
            Please ask your workspace administrator or HR Operations manager to assign you the Resume Desk module in Team & Permissions.
          </p>
          <div className="mt-6 flex flex-col gap-2">
            <button
              onClick={() => router.push("/")}
              className="w-full bg-slate-900 hover:bg-black text-white font-semibold py-2 px-4 rounded-lg text-xs transition cursor-pointer"
            >
              Back to Welcome Page
            </button>
            <button
              onClick={() => logout()}
              className="w-full border border-slate-200 hover:bg-slate-50 text-slate-700 font-medium py-2 px-4 rounded-lg text-xs transition cursor-pointer"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-full bg-[#f8fafc] text-slate-800 font-sans overflow-hidden">
      {/* =========================================================================
          LEFT SIDEBAR: RESUME DESK HIERARCHY (Exact as Mockup)
      ========================================================================== */}
      <aside
        className={`${sidebarOpen ? "w-[280px]" : "w-0 -translate-x-full"
          } transition-all duration-300 ease-in-out border-r border-slate-200 bg-white flex flex-col flex-shrink-0 z-20 overflow-hidden shadow-xs`}
      >
        {/* Sidebar Header */}
        <div className="p-4 border-b border-slate-100 flex items-start justify-between">
          <div>
            <h1 className="font-bold text-base text-slate-900 tracking-tight">Resume Desk</h1>
            <p className="text-[11px] text-slate-400 mt-1 leading-snug">
              Tick a client for all its sites, or pick individual sites
            </p>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors"
            title="Collapse Sidebar"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        </div>

        {/* Tree Content */}
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5 text-xs select-none">
          {/* All Companies Row (Pink highlight when active, as in mockup) */}
          <div
            onClick={() => {
              setSelectedClientId(null);
              setSelectedSiteId(null);
              setPage(1);
            }}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-md cursor-pointer transition-colors ${selectedClientId === null && selectedSiteId === null
                ? "bg-[#fce7e7] text-[#991b1b] font-semibold"
                : "text-slate-700 hover:bg-slate-50 font-normal"
              }`}
          >
            <span>All companies</span>
            <span
              className={`text-xs ${selectedClientId === null && selectedSiteId === null
                  ? "text-[#991b1b] font-semibold"
                  : "text-slate-400 font-normal"
                }`}
            >
              {totalCount}
            </span>
          </div>

          {/* Client Rows */}
          {filteredClientTree.map((client) => {
            const isClientSelected = selectedClientId === client.id && selectedSiteId === null;
            const isExpanded = !!expandedClients[client.id];

            return (
              <div key={client.id} className="pt-0.5">
                {/* Client Row */}
                <div
                  className={`flex items-center justify-between px-2 py-1.5 rounded-md cursor-pointer transition-colors ${isClientSelected ? "bg-slate-100 font-semibold" : "hover:bg-slate-50 text-slate-700"
                    }`}
                >
                  <div className="flex items-center gap-1.5 flex-1 min-w-0">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleClientExpand(client.id);
                      }}
                      className="p-0.5 hover:bg-slate-200 rounded text-slate-400"
                    >
                      {isExpanded ? (
                        <ChevronDown className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5" />
                      )}
                    </button>

                    <input
                      type="checkbox"
                      checked={selectedClientId === client.id}
                      onChange={() => {
                        if (selectedClientId === client.id) {
                          setSelectedClientId(null);
                          setSelectedSiteId(null);
                        } else {
                          setSelectedClientId(client.id);
                          setSelectedSiteId(null);
                        }
                        setPage(1);
                      }}
                      className="rounded border-slate-300 text-rose-500 focus:ring-rose-400 w-3.5 h-3.5 cursor-pointer"
                    />

                    <span
                      onClick={() => toggleClientExpand(client.id)}
                      className="truncate text-xs select-none"
                    >
                      {client.name}
                    </span>
                  </div>

                  <span className="text-[11px] text-slate-400 font-mono ml-2">{client.count}</span>
                </div>

                {/* Nested Sites */}
                {isExpanded && (
                  <div className="ml-5 pl-2 border-l border-slate-200 space-y-0.5 mt-0.5">
                    {client.sites.map((site) => {
                      const isSiteSelected = selectedSiteId === site.id;

                      return (
                        <div key={site.id} className="pt-0.5">
                          <div
                            onClick={() => {
                              setSelectedClientId(client.id);
                              if (isSiteSelected) {
                                setSelectedSiteId(null);
                                setSelectedRole(null);
                              } else {
                                setSelectedSiteId(site.id);
                                setSelectedRole(null);
                              }
                              setPage(1);
                            }}
                            className={`flex items-center justify-between px-2 py-1 rounded cursor-pointer text-xs transition-colors ${isSiteSelected && !selectedRole
                                ? "bg-[#fce7e7] text-[#991b1b] font-medium"
                                : "text-slate-600 hover:bg-slate-100"
                              }`}
                          >
                            <div className="flex items-center gap-2 truncate">
                              <input
                                type="checkbox"
                                checked={isSiteSelected}
                                onChange={() => { }}
                                className="rounded border-slate-300 text-rose-500 focus:ring-rose-400 w-3.5 h-3.5"
                              />
                              <span className="truncate text-[11px]">{site.name}</span>
                            </div>
                            <span className="text-[11px] text-slate-400 font-mono ml-2">
                              {site.count}
                            </span>
                          </div>

                          {/* Nested Positions / Roles under Site */}
                          {site.roles && site.roles.length > 0 && (
                            <div className="ml-4 pl-2 border-l border-slate-200 space-y-0.5 mt-0.5">
                              {site.roles.map((role) => {
                                const isRoleSelected =
                                  selectedSiteId === site.id && selectedRole === role.name;

                                return (
                                  <div
                                    key={role.name}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setSelectedClientId(client.id);
                                      setSelectedSiteId(site.id);
                                      setSelectedRole(isRoleSelected ? null : role.name);
                                      setPage(1);
                                    }}
                                    className={`flex items-center justify-between px-2 py-0.5 rounded cursor-pointer text-[11px] transition-colors ${isRoleSelected
                                        ? "bg-[#fee2e2] text-[#991b1b] font-semibold"
                                        : "text-slate-500 hover:bg-slate-100"
                                      }`}
                                  >
                                    <div className="flex items-center gap-1.5 truncate">
                                      <input
                                        type="checkbox"
                                        checked={isRoleSelected}
                                        onChange={() => { }}
                                        className="rounded border-slate-300 text-rose-500 focus:ring-rose-400 w-3 h-3"
                                      />
                                      <span className="truncate">{role.name}</span>
                                    </div>
                                    <span className="text-[10px] text-slate-400 font-mono ml-2">
                                      {role.count}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Sidebar Footer: "• Collapse Sidebar" */}
        <div className="p-3 border-t border-slate-100 bg-white">
          <button
            onClick={() => setSidebarOpen(false)}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 transition-colors"
          >
            <span className="text-slate-400 font-bold">•</span>
            <span>Collapse Sidebar</span>
          </button>
        </div>
      </aside>

      {/* =========================================================================
          MAIN APPLICATION AREA
      ========================================================================== */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-white">
        {/* TOP NAVBAR & TABS (Exact as Mockup) */}
        <header className="border-b border-slate-200 bg-white">
          {/* Row 1: Left Scope/Status & Right Navigation Tabs */}
          <div className="px-6 py-2.5 flex items-center justify-between border-b border-slate-100 text-xs">
            {/* Left: Last updated & Sync stats (All companies dropdown removed per request) */}
            <div className="flex items-center gap-3">
              {!sidebarOpen && (
                <button
                  onClick={() => setSidebarOpen(true)}
                  className="px-2.5 py-1 text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 rounded font-medium flex items-center gap-1.5 transition-colors"
                >
                  <SlidersHorizontal className="w-3.5 h-3.5" />
                  <span>Resume Desk</span>
                </button>
              )}

              {/* Live Status Indicator & Resumes Synced + Duplicates Count */}
              <div className="flex items-center gap-2.5 text-xs text-slate-600 flex-wrap">
                <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block"></span>
                <span>
                  Last updated {formatTime(syncStatus?.last_synced_at)}
                </span>
                <span className="text-slate-300 font-normal">•</span>

                {/* Badge 1: Total Resumes Synced */}
                <span className="inline-flex items-center gap-1.5 text-slate-800 font-medium bg-slate-100 px-2.5 py-0.5 rounded-full text-[11px] border border-slate-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-500"></span>
                  <span className="font-semibold text-slate-900">{syncStatus?.total_scanned ?? syncStatus?.last_synced_resumes_count ?? 40}</span>
                  <span>resumes synced</span>
                  <span className="text-slate-400 font-normal">({syncStatus?.total_candidates ?? 30} unique)</span>
                </span>

                {/* Badge 2: Duplicates Count */}
                <span
                  className="inline-flex items-center gap-1 text-amber-900 font-medium bg-amber-50 px-2.5 py-0.5 rounded-full text-[11px] border border-amber-200 shadow-2xs"
                  title={`${syncStatus?.total_duplicates ?? 10} duplicate resumes blocked across ${syncStatus?.candidates_with_duplicates ?? 8} candidates`}
                >
                  <span className="text-amber-500 font-bold">⚠️</span>
                  <span className="font-semibold text-amber-950">{syncStatus?.total_duplicates ?? 10}</span>
                  <span>duplicates</span>
                </span>

                {/* Manual Sync Button */}
                <button
                  onClick={(e) => handleTriggerSync(e.shiftKey)}
                  disabled={syncing}
                  className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors disabled:opacity-50 ml-0.5 cursor-pointer"
                  title="Sync Google Drive Now (Shift+Click to force-unlock if stuck)"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin text-rose-500" : ""}`} />
                </button>

                {syncNotice && (
                  <span className="inline-flex items-center gap-1 text-[11px] font-medium text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full animate-pulse">
                    <span>{syncNotice}</span>
                  </span>
                )}
              </div>
            </div>

            {/* Right: Actions, Module Switcher & User Profile */}
            <div className="flex items-center gap-2">
              {/* Manage Team Button (For Admins / Super Admins / Developers) */}
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => setTeamModalOpen(true)}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium bg-white text-slate-700 hover:text-slate-900 hover:bg-slate-50 rounded-md border border-slate-200 shadow-2xs transition cursor-pointer"
                >
                  <Users className="w-3.5 h-3.5 text-slate-500" />
                  <span>Team</span>
                </button>
              )}

              {/* Module Switcher Dropdown */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setModuleDropdownOpen((prev) => !prev)}
                  className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-black text-white rounded-md shadow-xs hover:bg-slate-800 transition-all cursor-pointer"
                >
                  <span>{activeTab}</span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 transition-transform duration-200 ${moduleDropdownOpen ? "rotate-180" : ""
                      }`}
                  />
                </button>

                {moduleDropdownOpen && (
                  <>
                    {/* Backdrop for click outside */}
                    <div
                      className="fixed inset-0 z-30"
                      onClick={() => setModuleDropdownOpen(false)}
                    />
                    <div className="absolute right-0 mt-1.5 w-48 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-40 text-xs">
                      <div className="px-3 py-1.5 text-[10px] font-semibold text-slate-400 uppercase tracking-wider border-b border-slate-100">
                        Modules
                      </div>
                      {MODULE_OPTIONS.map((mod) => {
                        const isSelected = activeTab === mod.name;
                        const isAllowed = canAccessModule(mod.name);
                        const canClick = mod.active && isAllowed;

                        return (
                          <button
                            key={mod.name}
                            type="button"
                            disabled={!canClick}
                            onClick={() => {
                              if (canClick) {
                                setActiveTab(mod.name);
                              }
                              setModuleDropdownOpen(false);
                            }}
                            className={`w-full text-left px-3 py-2 flex items-center justify-between transition-colors ${isSelected
                                ? "bg-slate-100 text-slate-900 font-semibold"
                                : canClick
                                  ? "text-slate-700 hover:bg-slate-50 font-medium cursor-pointer"
                                  : "text-slate-400 hover:bg-slate-50 cursor-not-allowed opacity-60"
                              }`}
                          >
                            <span>{mod.name}</span>
                            {isSelected ? (
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                            ) : !isAllowed ? (
                              <span className="text-[10px] text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded font-normal">
                                Restricted
                              </span>
                            ) : !mod.active ? (
                              <span className="text-[10px] text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded font-normal">
                                Soon
                              </span>
                            ) : null}
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>

              {/* User Avatar & Menu */}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setUserDropdownOpen((prev) => !prev)}
                  className="flex items-center gap-2 px-2 py-1 rounded-md border border-slate-200 hover:bg-slate-50 transition cursor-pointer"
                >
                  <div className="w-5 h-5 rounded-full bg-slate-900 text-white flex items-center justify-center font-medium text-[10px]">
                    {profile?.full_name?.charAt(0).toUpperCase() || user?.email?.charAt(0).toUpperCase() || "U"}
                  </div>
                  <span className="font-medium text-slate-700 text-xs hidden sm:inline max-w-[120px] truncate">
                    {profile?.full_name || user?.email?.split("@")[0] || "User"}
                  </span>
                  <ChevronDown className="w-3 h-3 text-slate-400" />
                </button>

                {userDropdownOpen && (
                  <>
                    <div className="fixed inset-0 z-30" onClick={() => setUserDropdownOpen(false)} />
                    <div className="absolute right-0 mt-1.5 w-56 bg-white border border-slate-200 rounded-md shadow-lg py-1.5 z-40 text-xs">
                      <div className="px-3 py-2 border-b border-slate-100">
                        <div className="font-semibold text-slate-900 truncate">
                          {profile?.full_name || "User"}
                        </div>
                        <div className="text-[11px] text-slate-400 truncate">{user?.email}</div>
                        <div className="mt-1 flex items-center gap-1">
                          <span className="text-[10px] font-medium px-1.5 py-0.2 rounded bg-slate-100 text-slate-700 border border-slate-200">
                            {profile?.account_tier === "developer"
                              ? "Developer"
                              : profile?.account_tier === "tenant_super_admin"
                              ? "Super Admin"
                              : profile?.account_tier === "tenant_admin"
                              ? "Admin (HR Ops)"
                              : "Team Member"}
                          </span>
                        </div>
                        {profile?.tenant_name && (
                          <div className="mt-1 text-[10px] text-slate-400 truncate">
                            {profile.tenant_name}
                          </div>
                        )}
                      </div>

                      <div className="pt-1">
                        <button
                          type="button"
                          onClick={() => {
                            setUserDropdownOpen(false);
                            setPwdError(null);
                            setPwdSuccess(false);
                            setNewPassword("");
                            setConfirmPassword("");
                            setChangePasswordModalOpen(true);
                          }}
                          className="w-full text-left px-3 py-1.5 text-slate-700 hover:text-slate-900 hover:bg-slate-50 flex items-center gap-2 font-medium transition cursor-pointer"
                        >
                          <KeyRound className="w-3.5 h-3.5 text-slate-400" />
                          <span>Change Password</span>
                        </button>

                        <button
                          type="button"
                          onClick={async () => {
                            setUserDropdownOpen(false);
                            await logout();
                            router.push("/login");
                          }}
                          className="w-full text-left px-3 py-1.5 text-slate-600 hover:text-rose-600 hover:bg-slate-50 flex items-center gap-2 font-medium transition cursor-pointer border-t border-slate-100 mt-0.5"
                        >
                          <LogOut className="w-3.5 h-3.5" />
                          <span>Sign Out</span>
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Row 2: Search Bar & Action Buttons */}
          <div className="px-6 py-2.5 bg-white flex items-center justify-between gap-4">
            {/* Search Input */}
            <div className="relative flex-1 max-w-sm">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search name, phone, city"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-9 pr-8 py-1.5 text-xs bg-white border border-slate-200 rounded text-slate-800 placeholder-slate-400 focus:outline-none focus:border-slate-400"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Action Buttons: Offer template, Send offer letters, Export to Excel */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="px-3 py-1.5 text-xs font-medium border border-slate-200 text-slate-700 bg-white hover:bg-slate-50 rounded shadow-2xs transition-colors"
              >
                Offer template
              </button>

              <button
                type="button"
                className="px-3.5 py-1.5 text-xs font-medium bg-[#fca5a5] hover:bg-[#f87171] text-white rounded shadow-2xs transition-colors"
              >
                Send offer letters
              </button>

              <button
                onClick={handleExportCSV}
                className="px-3 py-1.5 text-xs font-medium border border-slate-200 text-slate-700 bg-white hover:bg-slate-50 rounded shadow-2xs transition-colors flex items-center gap-1.5"
              >
                <span>Export to Excel</span>
              </button>
            </div>
          </div>
        </header>

        {/* CANDIDATES MAIN AREA (TABLE OR PIPELINE VIEW) */}
        <main className="flex-1 overflow-auto px-6 py-3 bg-white">
          {activeTab === "Pipeline" ? (
            /* PIPELINE KANBAN BOARD */
            <div className="flex flex-col h-full">
              {/* Pipeline Header Bar */}
              <div className="mb-3 flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                    <Kanban className="w-4 h-4 text-blue-600" />
                    <span>Hiring Pipeline</span>
                  </span>
                  <span className="text-slate-400">•</span>
                  <span className="text-slate-500 font-medium">
                    {candidates.length} candidates in view
                  </span>
                  {(selectedClientId || selectedSiteId || selectedRole || searchQuery) && (
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedClientId(null);
                        setSelectedSiteId(null);
                        setSelectedRole(null);
                        setSearchQuery("");
                      }}
                      className="text-[11px] text-blue-600 hover:text-blue-800 font-medium ml-2 underline cursor-pointer"
                    >
                      Clear active filters
                    </button>
                  )}
                </div>

                <div className="text-[11px] text-slate-400 flex items-center gap-1">
                  <span>💡 Drag & drop candidate cards across columns to update their stage</span>
                </div>
              </div>

              {/* Kanban Columns (Horizontal Scroll) */}
              <div className="flex-1 overflow-x-auto pb-4">
                <div className="flex gap-3.5 min-w-max h-[calc(100vh-210px)]">
                  {STATUS_OPTIONS.map((col) => {
                    const colCandidates = candidates.filter(
                      (c) => (c.display_status || "New") === col.label
                    );
                    const isDragTarget = dragOverCol === col.label;

                    return (
                      <div
                        key={col.label}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.dataTransfer.dropEffect = "move";
                          if (dragOverCol !== col.label) {
                            setDragOverCol(col.label);
                          }
                        }}
                        onDragLeave={(e) => {
                          if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                            setDragOverCol(null);
                          }
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          setDragOverCol(null);
                          const candidateId = e.dataTransfer.getData("text/plain") || draggedCandidateId;
                          if (candidateId) {
                            handleUpdateStatus(candidateId, col.label);
                          }
                          setDraggedCandidateId(null);
                        }}
                        className={`w-[300px] flex flex-col rounded-xl border transition-all duration-150 ${
                          isDragTarget
                            ? "bg-blue-50/70 border-blue-400 ring-2 ring-blue-300 ring-dashed shadow-md"
                            : "bg-slate-50/80 border-slate-200"
                        }`}
                      >
                        {/* Column Header */}
                        <div className="p-3 border-b border-slate-200/80 flex items-center justify-between bg-white rounded-t-xl">
                          <div className="flex items-center gap-2">
                            <span className={`w-2.5 h-2.5 rounded-full ${col.color}`} />
                            <span className="font-semibold text-xs text-slate-800">{col.label}</span>
                          </div>
                          <span className="text-[11px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
                            {colCandidates.length}
                          </span>
                        </div>

                        {/* Column Cards Container (Vertical Scroll) */}
                        <div className="flex-1 overflow-y-auto p-2.5 space-y-2.5">
                          {colCandidates.length === 0 ? (
                            <div
                              className={`h-28 border-2 border-dashed rounded-lg flex flex-col items-center justify-center text-xs transition-colors ${
                                isDragTarget
                                  ? "border-blue-300 bg-blue-50/40 text-blue-500 font-medium"
                                  : "border-slate-200 text-slate-400"
                              }`}
                            >
                              <span>Drop candidate here</span>
                            </div>
                          ) : (
                            colCandidates.map((c) => {
                              const isBeingDragged = draggedCandidateId === c.id;

                              // Determine display role and site
                              const rawParts = (c.drive_folder_path || "").split("/").filter(Boolean);
                              const displayRole = getCandidateJobRole(c) || "Applicant";
                              const displaySite = c.contextual_site || (rawParts.length >= 2 ? rawParts[1] : "");

                              return (
                                <div
                                  key={c.id}
                                  draggable
                                  onDragStart={(e) => {
                                    e.dataTransfer.setData("text/plain", c.id);
                                    e.dataTransfer.effectAllowed = "move";
                                    setDraggedCandidateId(c.id);
                                  }}
                                  onDragEnd={() => {
                                    setDraggedCandidateId(null);
                                    setDragOverCol(null);
                                  }}
                                  className={`bg-white rounded-lg p-3 border shadow-2xs hover:shadow-md transition-all cursor-grab active:cursor-grabbing select-none group ${
                                    isBeingDragged
                                      ? "opacity-40 border-dashed border-blue-400 scale-[0.98]"
                                      : "border-slate-200 hover:border-slate-300"
                                  }`}
                                >
                                  {/* Top Row: Name + Drag Handle */}
                                  <div className="flex items-start justify-between gap-1 mb-1.5">
                                    <button
                                      type="button"
                                      onClick={() => setActiveCandidate(c)}
                                      className="font-semibold text-xs text-slate-900 hover:text-blue-600 transition-colors text-left line-clamp-1 cursor-pointer"
                                    >
                                      {c.first_name} {c.last_name || ""}
                                    </button>
                                    <GripVertical className="w-3.5 h-3.5 text-slate-300 group-hover:text-slate-500 flex-shrink-0 transition-colors" />
                                  </div>

                                  {/* Position & Site Badges */}
                                  <div className="flex flex-wrap items-center gap-1.5 mb-2">
                                    {displayRole && (
                                      <span className="text-[10px] font-medium bg-slate-100 text-slate-700 px-2 py-0.5 rounded border border-slate-200 line-clamp-1">
                                        {displayRole}
                                      </span>
                                    )}
                                    {displaySite && (
                                      <span className="text-[10px] font-medium bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded border border-indigo-100 flex items-center gap-0.5">
                                        <MapPin className="w-2.5 h-2.5" />
                                        <span>{displaySite}</span>
                                      </span>
                                    )}
                                  </div>

                                  {/* Candidate Meta Info */}
                                  <div className="space-y-1 text-[11px] text-slate-500 mb-2.5">
                                    {c.phone && (
                                      <div className="flex items-center gap-1.5">
                                        <Phone className="w-3 h-3 text-slate-400" />
                                        <span>{c.phone}</span>
                                      </div>
                                    )}
                                    {c.email && (
                                      <div className="flex items-center gap-1.5 truncate">
                                        <Mail className="w-3 h-3 text-slate-400" />
                                        <span className="truncate">{c.email}</span>
                                      </div>
                                    )}
                                    {((c.experience_years !== null && c.experience_years !== undefined) || c.last_qualification) && (
                                      <div className="flex items-center gap-2 pt-0.5 text-[10px] text-slate-600">
                                        {c.experience_years !== null && c.experience_years !== undefined && (
                                          <span>💼 {c.experience_years} yrs exp</span>
                                        )}
                                        {c.last_qualification && (
                                          <span>🎓 {c.last_qualification}</span>
                                        )}
                                      </div>
                                    )}
                                  </div>

                                  {/* Card Footer: View Resume, Notes & Quick Move */}
                                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between gap-1 text-[11px]">
                                    <div className="flex items-center gap-2">
                                      {c.drive_file_id && (
                                        <a
                                          href={`https://drive.google.com/file/d/${c.drive_file_id}/view`}
                                          target="_blank"
                                          rel="noreferrer"
                                          onClick={(e) => e.stopPropagation()}
                                          className="text-blue-600 hover:text-blue-800 flex items-center gap-1 font-medium hover:underline text-[10px]"
                                          title="View resume in Google Drive"
                                        >
                                          <FileText className="w-3 h-3" />
                                          <span>Resume</span>
                                          <ExternalLink className="w-2.5 h-2.5" />
                                        </a>
                                      )}

                                      <button
                                        type="button"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setNotesModalCandidate(c);
                                        }}
                                        className="text-slate-500 hover:text-slate-800 flex items-center gap-1 text-[10px] cursor-pointer"
                                        title="Notes / comments"
                                      >
                                        <Mic className="w-3 h-3" />
                                        <span>{c.comments_count || c.notes?.length || 0}</span>
                                      </button>
                                    </div>

                                    {/* Move To Quick Selector */}
                                    <select
                                      value={c.display_status || "New"}
                                      onChange={(e) => {
                                        e.stopPropagation();
                                        handleUpdateStatus(c.id, e.target.value);
                                      }}
                                      onClick={(e) => e.stopPropagation()}
                                      className="text-[10px] font-medium border border-slate-200 rounded px-1.5 py-0.5 bg-slate-50 text-slate-700 hover:bg-white focus:outline-none focus:border-slate-400 cursor-pointer"
                                      title="Quick change status"
                                    >
                                      {STATUS_OPTIONS.map((st) => (
                                        <option key={st.label} value={st.label}>
                                          → {st.label}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            /* RESUME DESK TABLE VIEW */
            <>
              {/* Status Filter Dropdown Bar */}
              <div className="mb-2 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <div className="relative inline-block text-left">
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setPage(1);
                  }}
                  className="text-xs font-medium text-slate-700 bg-white border border-transparent hover:border-slate-200 rounded px-2 py-1 cursor-pointer focus:outline-none"
                >
                  <option value="All">Status: All ▾</option>
                  <option value="New">Status: New</option>
                  <option value="Ready for AI Call">Status: Ready for AI Call</option>
                  <option value="AI Call Initiated">Status: AI Call Initiated</option>
                  <option value="Offer Sent">Status: Offer Sent</option>
                  <option value="Accepted">Status: Accepted</option>
                  <option value="Rejected">Status: Rejected</option>
                </select>
              </div>

              {selectedCount > 0 && (
                <span className="text-[11px] bg-rose-50 text-rose-700 font-medium px-2 py-0.5 rounded-full border border-rose-100">
                  {selectedCount} selected
                </span>
              )}
            </div>

            {/* Active sync or background status */}
            <div className="text-[11px] text-slate-400">
              6-hr auto refresh active • Sub-50ms query cache
            </div>
          </div>

          {/* Table Container */}
          <div className="border border-slate-200 rounded overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-[#f8fafc] border-b border-slate-200 text-slate-600 font-medium">
                  <tr>
                    <th className="p-2.5 w-8 text-center">
                      <input
                        type="checkbox"
                        checked={candidates.length > 0 && selectedCount === candidates.length}
                        onChange={(e) => handleSelectAll(e.target.checked)}
                        className="rounded border-slate-300 text-rose-500 focus:ring-rose-400 w-3.5 h-3.5 cursor-pointer"
                      />
                    </th>

                    {/* Name Header (Sortable) */}
                    <th
                      onClick={() => handleSort("name")}
                      className="py-2.5 px-3 font-medium cursor-pointer hover:bg-slate-100/80 transition-colors select-none group"
                      title="Click to sort by Name"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={sortBy === "name" ? "text-slate-900 font-semibold" : ""}>Name</span>
                        <span className="text-[10px]">
                          {sortBy === "name" ? (
                            sortOrder === "asc" ? <span className="text-rose-600 font-bold">▲</span> : <span className="text-rose-600 font-bold">▼</span>
                          ) : (
                            <span className="text-slate-300 group-hover:text-slate-500">⇅</span>
                          )}
                        </span>
                      </div>
                    </th>

                    {/* Phone Header (Sortable) */}
                    <th
                      onClick={() => handleSort("phone")}
                      className="py-2.5 px-3 font-medium cursor-pointer hover:bg-slate-100/80 transition-colors select-none group"
                      title="Click to sort by Phone"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={sortBy === "phone" ? "text-slate-900 font-semibold" : ""}>Phone</span>
                        <span className="text-[10px]">
                          {sortBy === "phone" ? (
                            sortOrder === "asc" ? <span className="text-rose-600 font-bold">▲</span> : <span className="text-rose-600 font-bold">▼</span>
                          ) : (
                            <span className="text-slate-300 group-hover:text-slate-500">⇅</span>
                          )}
                        </span>
                      </div>
                    </th>

                    {/* Location Header (Sortable) */}
                    <th
                      onClick={() => handleSort("location")}
                      className="py-2.5 px-3 font-medium cursor-pointer hover:bg-slate-100/80 transition-colors select-none group"
                      title="Click to sort by Location"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={sortBy === "location" ? "text-slate-900 font-semibold" : ""}>Location</span>
                        <span className="text-[10px]">
                          {sortBy === "location" ? (
                            sortOrder === "asc" ? <span className="text-rose-600 font-bold">▲</span> : <span className="text-rose-600 font-bold">▼</span>
                          ) : (
                            <span className="text-slate-300 group-hover:text-slate-500">⇅</span>
                          )}
                        </span>
                      </div>
                    </th>

                    {/* Email Header (Sortable) */}
                    <th
                      onClick={() => handleSort("email")}
                      className="py-2.5 px-3 font-medium cursor-pointer hover:bg-slate-100/80 transition-colors select-none group"
                      title="Click to sort by Email"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={sortBy === "email" ? "text-slate-900 font-semibold" : ""}>Email</span>
                        <span className="text-[10px]">
                          {sortBy === "email" ? (
                            sortOrder === "asc" ? <span className="text-rose-600 font-bold">▲</span> : <span className="text-rose-600 font-bold">▼</span>
                          ) : (
                            <span className="text-slate-300 group-hover:text-slate-500">⇅</span>
                          )}
                        </span>
                      </div>
                    </th>

                    {/* Status Header (Sortable) */}
                    <th
                      onClick={() => handleSort("status")}
                      className="py-2.5 px-3 font-medium cursor-pointer hover:bg-slate-100/80 transition-colors select-none group"
                      title="Click to sort by Status"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className={sortBy === "status" ? "text-slate-900 font-semibold" : ""}>Status</span>
                        <span className="text-[10px]">
                          {sortBy === "status" ? (
                            sortOrder === "asc" ? <span className="text-rose-600 font-bold">▲</span> : <span className="text-rose-600 font-bold">▼</span>
                          ) : (
                            <span className="text-slate-300 group-hover:text-slate-500">⇅</span>
                          )}
                        </span>
                      </div>
                    </th>

                    {/* Comments Header (Sortable) */}
                    <th
                      onClick={() => handleSort("comments")}
                      className="py-2.5 px-3 font-medium text-center cursor-pointer hover:bg-slate-100/80 transition-colors select-none group"
                      title="Click to sort by Comments count"
                    >
                      <div className="flex items-center justify-center gap-1.5">
                        <span className={sortBy === "comments" ? "text-slate-900 font-semibold" : ""}>Comments</span>
                        <span className="text-[10px]">
                          {sortBy === "comments" ? (
                            sortOrder === "asc" ? <span className="text-rose-600 font-bold">▲</span> : <span className="text-rose-600 font-bold">▼</span>
                          ) : (
                            <span className="text-slate-300 group-hover:text-slate-500">⇅</span>
                          )}
                        </span>
                      </div>
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {loading ? (
                    <tr>
                      <td colSpan={7} className="py-12 text-center text-slate-400">
                        <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-rose-400" />
                        Loading resumes...
                      </td>
                    </tr>
                  ) : candidates.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-12 text-center text-slate-400">
                        No resumes found matching the selected filters.
                      </td>
                    </tr>
                  ) : (
                    candidates.map((c) => {
                      const isSelected = !!selectedCandidates[c.id];
                      const attrs = c.extracted_attributes || {};
                      const isRenamed = Boolean(
                        (c.is_renamed || attrs.is_renamed) &&
                        attrs.previous_path &&
                        attrs.previous_path.trim().replace(/^\/+/, "") !== (c.drive_folder_path || "").trim().replace(/^\/+/, "")
                      );
                      const pathSegments = (c.drive_folder_path || "").replace(/^\/+/, "").split("/");
                      const roleName = getCandidateJobRole(c) || null;
                      const displayPath = c.contextual_path || c.drive_folder_path;
                      const hasDuplicate =
                        (c.flags || []).includes("duplicate_resume_uploaded") ||
                        (attrs.duplicate_files && attrs.duplicate_files.length > 0);
                      const displayStatus = c.display_status || "New";

                      // Status indicator dot color
                      const statusConfig = STATUS_OPTIONS.find((s) => s.label === displayStatus) || {
                        color: "bg-slate-400",
                        text: "text-slate-700",
                      };

                      return (
                        <tr
                          key={c.id}
                          className={`hover:bg-slate-50/70 transition-colors ${isSelected ? "bg-rose-50/30" : ""
                            }`}
                        >
                          {/* Checkbox */}
                          <td className="p-2.5 text-center">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={(e) => {
                                setSelectedCandidates((prev) => ({
                                  ...prev,
                                  [c.id]: e.target.checked,
                                }));
                              }}
                              className="rounded border-slate-300 text-rose-500 focus:ring-rose-400 w-3.5 h-3.5 cursor-pointer"
                            />
                          </td>

                          {/* Candidate Name (Reddish/Coral Link as in Mockup) */}
                          <td className="py-2 px-3">
                            <div className="flex flex-col">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <button
                                  onClick={() => setActiveCandidate(c)}
                                  className="font-medium text-[#dc2626] hover:underline text-left"
                                >
                                  {c.first_name} {c.last_name || ""}
                                </button>

                                {roleName && (
                                  <span className="px-1.5 py-0.2 text-[10px] font-medium bg-slate-100 text-slate-700 border border-slate-200 rounded">
                                    {roleName}
                                  </span>
                                )}

                                {/* Multi-location presence badge */}
                                {c.is_multi_location && (
                                  <span
                                    title={`Present in: ${(c.locations_present || [])
                                      .map((l) => `${l.client_name || ""} ${l.site_name || ""} (${l.role_name || ""})`)
                                      .join(" • ")}`}
                                    className="px-1.5 py-0.2 text-[10px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-200 rounded flex items-center gap-1 shadow-2xs"
                                  >
                                    <MapPin className="w-2.5 h-2.5 text-indigo-500" />
                                    <span>
                                      {selectedSiteId && c.other_locations && c.other_locations.length > 0
                                        ? `Also in ${c.other_locations.map((l) => l.site_name).join(", ")}`
                                        : `${c.locations_present?.length} locations: ${(c.locations_present || [])
                                          .map((l) => l.site_name)
                                          .join(", ")}`}
                                    </span>
                                  </span>
                                )}

                                {/* Duplicate & Rename Flags */}
                                {isRenamed && (
                                  <span
                                    title={`Renamed in Google Drive: ${attrs.previous_path || ""}`}
                                    className="px-1.5 py-0.2 text-[10px] font-semibold bg-purple-50 text-purple-700 border border-purple-200 rounded"
                                  >
                                    Renamed in Drive
                                  </span>
                                )}

                                {/* {hasDuplicate && (
                                  <span
                                    title={`Duplicate resume uploaded in: ${(attrs.duplicate_files || []).join(", ")}`}
                                    className="px-1.5 py-0.2 text-[10px] font-semibold bg-amber-100 text-amber-900 border border-amber-300 rounded flex items-center gap-1 shadow-2xs"
                                  >
                                    <AlertCircle className="w-2.5 h-2.5 text-amber-700" />
                                    <span>Duplicate in Drive</span>
                                  </span>
                                )} */}
                              </div>

                              {displayPath && (
                                <div className="flex items-center gap-2 mt-0.5">
                                  <span className="text-[10px] text-slate-400 truncate max-w-xs">
                                    {displayPath}
                                  </span>
                                  {c.drive_file_id && (
                                    <a
                                      href={`https://drive.google.com/file/d/${c.drive_file_id}/view`}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      onClick={(e) => e.stopPropagation()}
                                      className="inline-flex items-center gap-0.5 text-[10px] text-rose-600 hover:text-rose-800 hover:underline font-medium shrink-0"
                                      title="Open resume in Google Drive"
                                    >
                                      <ExternalLink className="w-2.5 h-2.5" />
                                      <span>Open</span>
                                    </a>
                                  )}
                                </div>
                              )}
                            </div>
                          </td>

                          {/* Phone & AI Call Badge */}
                          <td className="py-2 px-3 whitespace-nowrap">
                            <div className="flex items-center gap-2">
                              <span className="font-mono text-slate-800">{c.phone}</span>
                              <button
                                type="button"
                                className="px-2 py-0.5 text-[10px] font-medium bg-white hover:bg-slate-50 text-slate-700 rounded border border-slate-200 flex items-center gap-1"
                              >
                                <span>AI Call</span>
                                {c.ai_call_badge && c.ai_call_badge.includes("/") && (
                                  <span className="text-amber-600 font-semibold">
                                    {c.ai_call_badge}
                                  </span>
                                )}
                              </button>
                            </div>
                          </td>

                          {/* Location */}
                          <td className="py-2 px-3 whitespace-nowrap text-slate-600">
                            {c.location || "—"}
                          </td>

                          {/* Email */}
                          <td className="py-2 px-3 text-slate-600 truncate max-w-[200px]">
                            {c.email || "—"}
                          </td>

                          {/* Status Dropdown with Dot (Interactive) */}
                          <td className="py-2 px-3 whitespace-nowrap">
                            <div className="flex items-center gap-1.5">
                              <span className={`w-2 h-2 rounded-full ${statusConfig.color}`}></span>
                              <select
                                value={displayStatus}
                                onChange={(e) => handleUpdateStatus(c.id, e.target.value)}
                                className="text-xs text-slate-700 bg-transparent border-none hover:bg-slate-100 rounded px-1 py-0.5 cursor-pointer focus:outline-none"
                              >
                                {STATUS_OPTIONS.map((opt) => (
                                  <option key={opt.label} value={opt.label}>
                                    {opt.label}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </td>

                          {/* Comments: Microphone outline with note count */}
                          <td className="py-2 px-3 text-center whitespace-nowrap">
                            <button
                              onClick={() => setNotesModalCandidate(c)}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-rose-200 text-[#dc2626] hover:bg-rose-50 transition-colors text-[11px]"
                              title="Click to view or add notes"
                            >
                              <Mic className="w-3.5 h-3.5" />
                              <span>
                                {c.comments_count || 0}{" "}
                                {(c.comments_count || 0) === 1 ? "note" : "notes"}
                              </span>
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination & Rows Per Page Footer */}
            <div className="p-3 border-t border-slate-200 bg-white flex flex-wrap items-center justify-between gap-3 text-xs text-slate-600 select-none">
              {/* Left: Summary + Rows Per Page Selector */}
              <div className="flex items-center gap-4">
                <span className="font-medium text-slate-700">
                  {candidatesCount > 0
                    ? `${(page - 1) * limit + 1}-${Math.min(page * limit, candidatesCount)} of ${candidatesCount} resumes`
                    : "0 of 0 resumes"}
                </span>

                <div className="flex items-center gap-2 text-slate-500 border-l border-slate-200 pl-4">
                  <span>Rows per page:</span>
                  <select
                    value={limit}
                    onChange={(e) => {
                      setLimit(Number(e.target.value));
                      setPage(1);
                    }}
                    className="border border-slate-200 rounded px-2 py-0.5 text-xs text-slate-700 bg-white font-medium focus:outline-none focus:border-slate-400 cursor-pointer"
                  >
                    <option value={10}>10</option>
                    <option value={20}>20</option>
                    <option value={30}>30</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </select>
                </div>
              </div>

              {/* Right: Page Buttons */}
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-2.5 py-1 text-xs border border-slate-200 rounded hover:bg-slate-50 text-slate-700 disabled:opacity-40 disabled:cursor-not-allowed font-medium transition-colors"
                >
                  Previous
                </button>

                {/* Page Number Buttons */}
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => {
                  const isCurrent = page === p;
                  if (
                    totalPages <= 7 ||
                    p === 1 ||
                    p === totalPages ||
                    (p >= page - 1 && p <= page + 1)
                  ) {
                    return (
                      <button
                        key={p}
                        type="button"
                        onClick={() => setPage(p)}
                        className={`min-w-7 h-7 px-2 flex items-center justify-center rounded text-xs transition-colors ${isCurrent
                            ? "bg-slate-900 text-white font-semibold shadow-xs"
                            : "border border-slate-200 text-slate-700 hover:bg-slate-50 font-medium"
                          }`}
                      >
                        {p}
                      </button>
                    );
                  } else if (p === page - 2 || p === page + 2) {
                    return (
                      <span key={p} className="px-1 text-slate-400 text-xs">
                        ...
                      </span>
                    );
                  }
                  return null;
                })}

                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-2.5 py-1 text-xs border border-slate-200 rounded hover:bg-slate-50 text-slate-700 disabled:opacity-40 disabled:cursor-not-allowed font-medium transition-colors"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
            </>
          )}
        </main>
      </div>

      {/* =========================================================================
          CANDIDATE PROFILE SLIDE-OVER DRAWER
      ========================================================================== */}
      {activeCandidate && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/20 backdrop-blur-2xs transition-opacity">
          <div className="w-full max-w-lg bg-white h-full shadow-2xl flex flex-col z-50 border-l border-slate-200">
            {/* Header */}
            <div className="p-5 border-b border-slate-100 flex items-start justify-between bg-slate-50">
              <div>
                <span className="text-[10px] font-bold text-rose-600 uppercase tracking-wider">
                  Resume Details
                </span>
                <h2 className="text-lg font-bold text-slate-900 mt-0.5">
                  {activeCandidate.first_name} {activeCandidate.last_name || ""}
                </h2>
                {activeCandidate.drive_folder_path && (
                  <p className="text-xs text-slate-500 font-mono mt-1 flex items-center gap-1">
                    <Folder className="w-3 h-3 text-slate-400" />
                    <span>{activeCandidate.drive_folder_path}</span>
                  </p>
                )}

                {/* Open Resume Button in Header */}
                {activeCandidate.drive_file_id && (
                  <a
                    href={`https://drive.google.com/file/d/${activeCandidate.drive_file_id}/view`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 mt-2.5 bg-rose-50 hover:bg-rose-100 text-[#dc2626] font-semibold text-xs rounded border border-rose-200 transition-colors shadow-2xs"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Open Resume</span>
                  </a>
                )}
              </div>
              <button
                onClick={() => setActiveCandidate(null)}
                className="p-1.5 hover:bg-slate-200 rounded text-slate-400 hover:text-slate-700 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5 text-xs">
              {/* Status & Quick Change */}
              <div className="p-3 bg-slate-50 border border-slate-200 rounded flex items-center justify-between">
                <span className="text-slate-600 font-medium">Recruitment Status:</span>
                <select
                  value={activeCandidate.display_status || "New"}
                  onChange={(e) => handleUpdateStatus(activeCandidate.id, e.target.value)}
                  className="text-xs font-semibold bg-white border border-slate-300 rounded px-2 py-1 cursor-pointer"
                >
                  {STATUS_OPTIONS.map((opt) => (
                    <option key={opt.label} value={opt.label}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Attributes Grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 bg-white border border-slate-200 rounded">
                  <span className="text-slate-400 block text-[11px] mb-0.5">Phone</span>
                  <span className="font-mono font-semibold text-slate-800 text-sm">
                    {activeCandidate.phone}
                  </span>
                </div>
                <div className="p-3 bg-white border border-slate-200 rounded">
                  <span className="text-slate-400 block text-[11px] mb-0.5">Email</span>
                  <span className="font-medium text-slate-800 text-xs truncate block">
                    {activeCandidate.email || "Not Provided"}
                  </span>
                </div>
                <div className="p-3 bg-white border border-slate-200 rounded">
                  <span className="text-slate-400 block text-[11px] mb-0.5">Location</span>
                  <span className="font-medium text-slate-800 text-xs">
                    {activeCandidate.location || "Unspecified"}
                  </span>
                </div>
                <div className="p-3 bg-white border border-slate-200 rounded">
                  <span className="text-slate-400 block text-[11px] mb-0.5">Qualification</span>
                  <span className="font-medium text-slate-800 text-xs">
                    {activeCandidate.last_qualification || "Not Detected"}
                  </span>
                </div>
              </div>

              {/* Flags Alert Card */}
              {activeCandidate.extracted_attributes?.is_renamed && (
                <div className="p-3 bg-purple-50 border border-purple-200 rounded">
                  <div className="flex items-center gap-1.5 text-purple-900 font-semibold text-xs mb-1">
                    <AlertCircle className="w-4 h-4 text-purple-600" />
                    <span>Renamed in Google Drive</span>
                  </div>
                  <p className="text-[11px] text-purple-700">
                    Previous path:{" "}
                    <code className="bg-purple-100 px-1 py-0.5 rounded">
                      {activeCandidate.extracted_attributes?.previous_path}
                    </code>
                  </p>
                </div>
              )}

              {/* Duplicate in Drive Alert Card */}
              {((activeCandidate.flags || []).includes("duplicate_resume_uploaded") ||
                ((activeCandidate.extracted_attributes?.duplicate_files || []).length > 0)) && (
                  <div className="p-3 bg-amber-50 border border-amber-300 rounded shadow-2xs">
                    <div className="flex items-center gap-1.5 text-amber-900 font-semibold text-xs mb-1">
                      <AlertCircle className="w-4 h-4 text-amber-600" />
                      <span>Duplicate Resume Uploaded in Google Drive</span>
                    </div>
                    <p className="text-[11px] text-amber-800 mb-1.5">
                      This candidate was already present in the dashboard. Duplicate resume uploads were blocked from creating another entry:
                    </p>
                    <div className="space-y-1">
                      {(activeCandidate.extracted_attributes?.duplicate_files || []).map(
                        (p: string, i: number) => (
                          <div
                            key={i}
                            className="bg-amber-100/80 text-amber-900 px-2 py-1 rounded text-[11px] font-mono break-all border border-amber-200"
                          >
                            {p}
                          </div>
                        )
                      )}
                    </div>
                  </div>
                )}

              {/* All Locations & Circles Present */}
              {activeCandidate.locations_present && activeCandidate.locations_present.length > 0 && (
                <div className="p-3 bg-slate-50 border border-slate-200 rounded">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-slate-800 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                      <MapPin className="w-3.5 h-3.5 text-rose-500" />
                      <span>Locations & Circles Present ({activeCandidate.locations_present.length})</span>
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      Single candidate in database
                    </span>
                  </div>
                  <div className="space-y-2">
                    {activeCandidate.locations_present.map((loc, idx) => (
                      <div
                        key={idx}
                        className="p-2 bg-white border border-slate-200 rounded flex items-center justify-between gap-2"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-semibold text-slate-800 text-xs">
                              {loc.client_name} — {loc.site_name}
                            </span>
                            {loc.role_name && (
                              <span className="px-1.5 py-0.2 bg-slate-100 text-slate-700 rounded text-[10px] font-medium border border-slate-200">
                                {loc.role_name}
                              </span>
                            )}
                          </div>
                          {loc.path && (
                            <p className="text-[10px] text-slate-400 font-mono truncate mt-0.5">
                              {loc.path}
                            </p>
                          )}
                        </div>
                        {loc.file_id && (
                          <a
                            href={`https://drive.google.com/file/d/${loc.file_id}/view`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 px-2 py-1 text-[10px] font-semibold text-rose-600 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded shrink-0 transition-colors"
                          >
                            <ExternalLink className="w-2.5 h-2.5" />
                            <span>Resume</span>
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Notes / Comments summary */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-700 uppercase tracking-wider text-[11px]">
                    Candidate Notes ({activeCandidate.notes?.length || 0})
                  </span>
                  <button
                    onClick={() => {
                      setNotesModalCandidate(activeCandidate);
                    }}
                    className="text-rose-600 hover:underline text-[11px] font-medium"
                  >
                    + Add Note
                  </button>
                </div>
                <div className="space-y-1.5">
                  {(activeCandidate.notes || []).length === 0 ? (
                    <p className="text-slate-400 italic">No notes recorded yet.</p>
                  ) : (
                    (activeCandidate.notes || []).map((n) => (
                      <div key={n.id} className="p-2.5 bg-slate-50 border border-slate-200 rounded">
                        <p className="text-slate-800">{n.text}</p>
                        <span className="text-[10px] text-slate-400 mt-1 block">
                          {n.author} • {formatTime(n.created_at)}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Raw Parsed Content */}
              <div>
                <span className="font-semibold text-slate-700 uppercase tracking-wider text-[11px] block mb-2">
                  Extracted Resume Text
                </span>
                <div className="p-3 bg-slate-900 text-slate-100 rounded font-mono text-[11px] max-h-64 overflow-y-auto leading-relaxed">
                  <pre className="whitespace-pre-wrap">
                    {activeCandidate.extracted_attributes?.raw_preview ||
                      "Full extracted resume content stored in database."}
                  </pre>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="p-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
              <span className="text-[11px] text-slate-400 font-mono">
                ID: {activeCandidate.id.slice(0, 8)}...
              </span>
              <div className="flex items-center gap-2">
                {activeCandidate.drive_file_id && (
                  <a
                    href={`https://drive.google.com/file/d/${activeCandidate.drive_file_id}/view`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-1.5 bg-[#fca5a5] hover:bg-[#f87171] text-white rounded text-xs font-semibold flex items-center gap-1.5 transition-colors"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Open Resume</span>
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => setActiveCandidate(null)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-900 text-white rounded text-xs font-medium"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          NOTES & AUDIO VOICE TRANSCRIPTION MODAL
      ========================================================================== */}
      {notesModalCandidate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-2xs p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md border border-slate-200 overflow-hidden">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Mic className="w-4 h-4 text-rose-500" />
                <h3 className="font-semibold text-sm text-slate-900">
                  Notes & Voice for {notesModalCandidate.first_name} {notesModalCandidate.last_name || ""}
                </h3>
              </div>
              <button
                onClick={() => {
                  stopVoiceRecording();
                  setNotesModalCandidate(null);
                }}
                className="p-1 text-slate-400 hover:text-slate-600 rounded cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Speech error notice */}
            {speechError && (
              <div className="px-4 py-2 bg-rose-50 border-b border-rose-200 text-rose-700 text-[11px] flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5 text-rose-600 shrink-0" />
                  <span>{speechError}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setSpeechError(null)}
                  className="text-rose-500 hover:text-rose-800 text-[10px] font-bold"
                >
                  ✕
                </button>
              </div>
            )}

            {/* Active live recording banner */}
            {isRecordingNote && (
              <div className="px-4 py-2 bg-rose-50/80 border-b border-rose-200 text-rose-800 text-xs flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-600 animate-ping"></span>
                  <span className="font-semibold text-[11px]">Microphone Active — Listening & transcribing live...</span>
                </div>
                <button
                  type="button"
                  onClick={stopVoiceRecording}
                  className="px-2 py-0.5 bg-rose-600 hover:bg-rose-700 text-white text-[10px] font-semibold rounded shadow-2xs cursor-pointer"
                >
                  Stop Recording
                </button>
              </div>
            )}

            {/* Notes List */}
            <div className="p-4 max-h-72 overflow-y-auto space-y-2 text-xs">
              {(notesModalCandidate.notes || []).length === 0 ? (
                <div className="text-center py-6 text-slate-400">
                  <Mic className="w-6 h-6 mx-auto mb-1 text-slate-300" />
                  <p className="font-medium text-slate-500">No notes recorded yet.</p>
                  <p className="text-[11px] text-slate-400 mt-1">
                    Click the microphone below to speak and transcribe, or type directly.
                  </p>
                </div>
              ) : (
                notesModalCandidate.notes?.map((n) => (
                  <div key={n.id} className="p-2.5 bg-slate-50 border border-slate-200 rounded">
                    <p className="text-slate-800">{n.text}</p>
                    <span className="text-[10px] text-slate-400 mt-1 block">
                      {n.author} • {formatTime(n.created_at)}
                    </span>
                  </div>
                ))
              )}
            </div>

            {/* Dictation & Note Input Footer */}
            <div className="p-3 border-t border-slate-100 bg-white">
              <div className="flex items-center gap-2">
                {/* Voice Record Toggle Button */}
                <button
                  type="button"
                  onClick={toggleVoiceRecording}
                  className={`p-2 rounded-lg border transition-all flex items-center justify-center cursor-pointer shrink-0 ${
                    isRecordingNote
                      ? "bg-rose-600 text-white border-rose-600 shadow-md animate-pulse"
                      : "bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-200 hover:text-slate-900"
                  }`}
                  title={isRecordingNote ? "Click to stop recording" : "Click to speak & transcribe note"}
                >
                  {isRecordingNote ? (
                    <Square className="w-4 h-4 fill-white" />
                  ) : (
                    <Mic className="w-4 h-4 text-rose-500" />
                  )}
                </button>

                {/* Input box */}
                <input
                  type="text"
                  placeholder={
                    isRecordingNote
                      ? "Listening... Speak your note now"
                      : "Type recruiter note or click mic to dictate..."
                  }
                  value={newNoteText}
                  onChange={(e) => setNewNoteText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      if (isRecordingNote) stopVoiceRecording();
                      handleAddNote(notesModalCandidate.id);
                    }
                  }}
                  className={`flex-1 px-3 py-1.5 text-xs border rounded focus:outline-none transition-colors ${
                    isRecordingNote
                      ? "border-rose-400 bg-rose-50/20 text-slate-900 focus:border-rose-500"
                      : "border-slate-200 bg-white text-slate-800 focus:border-slate-400"
                  }`}
                />

                {/* Submit button */}
                <button
                  onClick={() => {
                    if (isRecordingNote) stopVoiceRecording();
                    handleAddNote(notesModalCandidate.id);
                  }}
                  disabled={!newNoteText.trim() || isSubmittingNote}
                  className="px-3.5 py-1.5 bg-[#fca5a5] hover:bg-[#f87171] text-white rounded text-xs font-semibold disabled:opacity-50 transition-colors flex items-center gap-1 cursor-pointer shrink-0"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Add</span>
                </button>
              </div>

              {/* Sub-label helper */}
              <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-400 px-1">
                <span>
                  {isRecordingNote ? "🔴 Listening... Speak clearly into your mic" : "🎙️ Click mic to dictate live note"}
                </span>
                {newNoteText && (
                  <button
                    type="button"
                    onClick={() => setNewNoteText("")}
                    className="text-slate-400 hover:text-slate-600 underline cursor-pointer"
                  >
                    Clear text
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Team & User Provisioning Modal */}
      <TeamManagementModal
        isOpen={teamModalOpen}
        onClose={() => setTeamModalOpen(false)}
        token={session?.access_token}
        tenantId={profile?.tenant_id || "a0000000-0000-0000-0000-000000000001"}
        tenantName={profile?.tenant_name || "AT BiZ Workforce Solutions Ltd."}
        isDeveloper={isDeveloper}
        clients={allClientsList}
        onPermissionsUpdated={() => refreshProfile()}
      />

      {/* Change Password Modal */}
      {changePasswordModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-2xs">
          <div className="bg-white rounded-lg shadow-xl border border-slate-200 w-full max-w-sm overflow-hidden animate-in fade-in zoom-in-95">
            <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">Change Password</h3>
                <p className="text-[11px] text-slate-500 mt-0.5 truncate max-w-[240px]">
                  {user?.email}
                </p>
              </div>
              <button
                onClick={() => {
                  setChangePasswordModalOpen(false);
                  setPwdError(null);
                  setPwdSuccess(false);
                  setNewPassword("");
                  setConfirmPassword("");
                }}
                className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded transition cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5">
              {pwdSuccess ? (
                <div className="py-6 text-center">
                  <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto mb-2" />
                  <div className="text-xs font-semibold text-slate-900">Password Updated Successfully</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">Your account password has been changed.</div>
                </div>
              ) : (
                <form onSubmit={handleUpdatePassword} className="space-y-3.5">
                  {pwdError && (
                    <div className="p-2.5 bg-[#fce7e7] border border-[#fca5a5] text-[#991b1b] rounded text-xs flex items-center gap-2">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0 text-[#991b1b]" />
                      <span>{pwdError}</span>
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      New Password
                    </label>
                    <div className="relative">
                      <input
                        type={showNewPassword ? "text" : "password"}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="At least 6 characters"
                        required
                        className="w-full text-xs border border-slate-300 rounded px-3 py-1.5 pr-8 text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900"
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPassword(!showNewPassword)}
                        className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600"
                      >
                        {showNewPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Confirm New Password
                    </label>
                    <input
                      type={showNewPassword ? "text" : "password"}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="Repeat new password"
                      required
                      className="w-full text-xs border border-slate-300 rounded px-3 py-1.5 text-slate-900 focus:outline-none focus:border-slate-900 focus:ring-1 focus:ring-slate-900"
                    />
                  </div>

                  <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                    <button
                      type="button"
                      onClick={() => {
                        setChangePasswordModalOpen(false);
                        setPwdError(null);
                        setNewPassword("");
                        setConfirmPassword("");
                      }}
                      className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded transition cursor-pointer"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={pwdSubmitting}
                      className="px-3.5 py-1.5 text-xs font-semibold bg-slate-900 hover:bg-black text-white rounded transition shadow-2xs cursor-pointer disabled:opacity-50"
                    >
                      {pwdSubmitting ? "Updating..." : "Update Password"}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
