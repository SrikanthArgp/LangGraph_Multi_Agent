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
export function ChatMessage({ role, content, createdAt, webSearch, pending }: ChatMessageData) {
  const isUser = role === "user";

  return (
    <div
      data-testid="chat-message"
      data-role={role}
      className={`flex ${isUser ? "justify-end" : "justify-start"}`}
    >
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
          isUser
            ? "bg-emerald-600 text-white"
            : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-50"
        }`}
      >
        {content}
        {pending && <span className="ml-0.5 animate-pulse">▋</span>}
        {(webSearch || createdAt) && (
          <div
            className={`mt-1 text-xs ${isUser ? "text-emerald-100/80" : "text-zinc-500 dark:text-zinc-400"}`}
          >
            {webSearch && "🌐 web search · "}
            {createdAt && new Date(createdAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </div>
        )}
      </div>
    </div>
  );
}
