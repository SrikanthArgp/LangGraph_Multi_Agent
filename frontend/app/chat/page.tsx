// Landing spot behind the auth guard when no session is selected yet - the sidebar
// (rendered by app/chat/layout.tsx, shared with /chat/[sessionId]) owns session
// creation, so this is just an empty-state prompt pointing at it.
export default function ChatHomePage() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
      <p className="text-lg font-medium text-zinc-900 dark:text-zinc-50">No chat selected</p>
      <p className="max-w-sm text-sm text-zinc-500 dark:text-zinc-400">
        Pick a chat from the sidebar, or click “+ New” to start one.
      </p>
    </div>
  );
}
