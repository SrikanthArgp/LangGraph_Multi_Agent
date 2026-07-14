import { GlobeIcon } from "@/components/icons";

export interface ChatMessageData {
  id: string;
  role: string;
  content: string;
  createdAt?: string;
  webSearch?: boolean;
  pending?: boolean;
}

// Content is rendered as plain text only - never parsed as markdown/HTML. The CRAG
// pipeline's web-search fallback pulls in untrusted content that ends up in `content`
// here, and React's default text-node escaping is what keeps that safe (see plan.md's
// noted XSS risk for this exact rendering path).
export function ChatMessage({
  role,
  content,
  createdAt,
  webSearch,
  pending,
  username,
}: ChatMessageData & { username?: string }) {
  const isUser = role === "user";
  const initial = isUser ? username?.trim().charAt(0).toUpperCase() || "U" : "C";

  return (
    <div
      data-testid="chat-message"
      data-role={role}
      className={`flex items-end gap-2 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          isUser
            ? "bg-zinc-300 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200"
            : "bg-emerald-600 text-white"
        }`}
      >
        {initial}
      </div>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap shadow-sm ${
          isUser
            ? "rounded-br-sm bg-emerald-600 text-white"
            : "rounded-bl-sm bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50"
        }`}
      >
        {content}
        {pending && <span className="ml-0.5 animate-pulse">▋</span>}
        {(webSearch || createdAt) && (
          <div
            className={`mt-1 flex items-center gap-1 text-xs ${isUser ? "text-emerald-100/80" : "text-zinc-500 dark:text-zinc-400"}`}
          >
            {webSearch && (
              <>
                <GlobeIcon className="h-3 w-3" />
                <span>Web search</span>
                {createdAt && <span>·</span>}
              </>
            )}
            {createdAt && (
              <span>
                {new Date(createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
