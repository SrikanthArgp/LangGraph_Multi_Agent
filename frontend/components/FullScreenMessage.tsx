export function FullScreenMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">{children}</p>
    </div>
  );
}
