import type { AgentStatus } from "../types/office";

interface AgentAvatarProps {
  agentId: string;
  size?: "sm" | "md" | "lg";
  status?: AgentStatus | string;
}

const SIZE_CLASS = {
  sm: "h-10 w-10",
  md: "h-14 w-14",
  lg: "h-20 w-20",
};

const STATUS_CLASS: Record<string, string> = {
  working: "bg-sky-400",
  terminando: "bg-violet-400",
  waiting_approval: "bg-amber-400",
  idle: "bg-emerald-400",
  offline: "bg-slate-500",
};

function AvatarArt({ id }: { id: string }) {
  if (id === "sara") {
    return (
      <>
        <circle cx="40" cy="28" r="13" fill="#FDE68A" />
        <path d="M24 27C24 16 32 11 40 11C49 11 56 17 56 28C53 22 47 19 40 19C33 19 27 22 24 27Z" fill="#7C3AED" />
        <circle cx="35" cy="29" r="2" fill="#1E1B4B" />
        <circle cx="45" cy="29" r="2" fill="#1E1B4B" />
        <path d="M36 35C38 37.5 42 37.5 44 35" stroke="#9F1239" strokeWidth="2" strokeLinecap="round" fill="none" />
        <path d="M20 66C22 52 30 46 40 46C50 46 58 52 60 66" fill="#6366F1" />
      </>
    );
  }
  if (id === "mateo") {
    return (
      <>
        <circle cx="40" cy="28" r="13" fill="#FCD34D" />
        <path d="M27 23C29 14 51 14 53 23C48 19 32 19 27 23Z" fill="#065F46" />
        <rect x="31" y="26" width="7" height="5" rx="1.5" stroke="#064E3B" strokeWidth="1.8" fill="none" />
        <rect x="42" y="26" width="7" height="5" rx="1.5" stroke="#064E3B" strokeWidth="1.8" fill="none" />
        <line x1="38" y1="28.5" x2="42" y2="28.5" stroke="#064E3B" strokeWidth="1.8" />
        <path d="M20 66C22 52 30 46 40 46C50 46 58 52 60 66" fill="#10B981" />
      </>
    );
  }
  if (id === "valeria") {
    return (
      <>
        <circle cx="40" cy="28" r="13" fill="#FDE68A" />
        <path d="M25 32C24 18 31 11 40 11C49 11 56 18 55 32" stroke="#D97706" strokeWidth="5" strokeLinecap="round" fill="none" />
        <circle cx="35" cy="29" r="2" fill="#1F2937" />
        <circle cx="45" cy="29" r="2" fill="#1F2937" />
        <path d="M36 35C38.5 37 41.5 37 44 35" stroke="#BE123C" strokeWidth="2" strokeLinecap="round" fill="none" />
        <path d="M20 66C22 52 30 46 40 46C50 46 58 52 60 66" fill="#F59E0B" />
      </>
    );
  }
  return (
    <>
      <circle cx="40" cy="28" r="13" fill="#FBBF24" />
      <path d="M27 24C29 14 51 14 53 24C47 20 33 20 27 24Z" fill="#0F172A" />
      <circle cx="35" cy="29" r="2" fill="#0F172A" />
      <circle cx="45" cy="29" r="2" fill="#0F172A" />
      <path d="M36 35.5H44" stroke="#0F172A" strokeWidth="2" strokeLinecap="round" />
      <path d="M20 66C22 52 30 46 40 46C50 46 58 52 60 66" fill="#0284C7" />
      <polygon points="40,48 37,56 40,65 43,56" fill="#E0F2FE" />
    </>
  );
}

export function AgentAvatar({ agentId, size = "md", status }: AgentAvatarProps) {
  const id = agentId.toLowerCase();
  return (
    <div className="relative shrink-0">
      <svg
        viewBox="0 0 80 80"
        aria-hidden="true"
        className={`${SIZE_CLASS[size]} rounded-2xl bg-slate-800/70 p-1.5 ring-1 ring-white/10`}
      >
        <AvatarArt id={id} />
      </svg>
      {status && (
        <span
          title={status}
          className={`absolute -bottom-1 -right-1 h-3.5 w-3.5 rounded-full border-2 border-slate-950 ${STATUS_CLASS[status] ?? "bg-slate-500"}`}
        />
      )}
    </div>
  );
}
