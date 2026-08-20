/**
 * The palette's visual layer — lazy-loaded by CommandPalette.tsx.
 *
 * Split out because cmdk + the Radix-style overlay chrome are ~28 KB gzip and
 * are only reachable via an explicit user gesture (Cmd+K or the header
 * button). Keeping them out of the entry chunk is what lets the app stay under
 * the <120 KB initial-JS budget.
 */
import { Command } from "cmdk";
import { AnimatePresence, motion } from "framer-motion";
import { spring } from "@/lib/motion";
import type { CommandItem } from "@/components/CommandPalette";

export default function CommandPaletteOverlay({
  groups,
  onClose,
}: {
  groups: { group: string; items: CommandItem[] }[];
  onClose: () => void;
}) {
  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-[200] flex items-start justify-center bg-black/25 p-4 pt-[12vh] backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, y: -12, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -8, scale: 0.98 }}
          transition={spring}
          className="w-full max-w-lg overflow-hidden rounded-2xl bg-[var(--color-surface)] shadow-[var(--shadow-float)]"
          onClick={(e) => e.stopPropagation()}
        >
          <Command label="Command palette" loop onKeyDown={(e) => e.key === "Escape" && onClose()}>
            <div className="flex items-center gap-3 border-b border-[var(--color-line)] px-4">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true" className="shrink-0 text-[var(--color-faint)]">
                <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
                <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <Command.Input
                autoFocus
                placeholder="Search commands…"
                className="h-12 w-full bg-transparent text-sm text-[var(--color-ink)] outline-none placeholder:text-[var(--color-faint)]"
              />
              <kbd className="shrink-0 rounded border border-[var(--color-line)] px-1.5 py-0.5 text-[10px] text-[var(--color-faint)]">
                ESC
              </kbd>
            </div>
            <Command.List className="max-h-80 overflow-y-auto p-2">
              <Command.Empty className="px-3 py-8 text-center text-sm text-[var(--color-muted)]">
                No matching command.
              </Command.Empty>
              {groups.map(({ group, items }) => (
                <Command.Group
                  key={group}
                  heading={group}
                  className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-[11px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-[var(--color-faint)]"
                >
                  {items.map((c) => (
                    <Command.Item
                      key={c.id}
                      value={`${c.label} ${c.keywords ?? ""}`}
                      onSelect={() => {
                        onClose();
                        c.run();
                      }}
                      className="flex cursor-pointer items-center justify-between rounded-xl px-3 py-2.5 text-sm text-[var(--color-ink)] data-[selected=true]:bg-[var(--color-line)]"
                    >
                      <span>{c.label}</span>
                      {c.shortcut && (
                        <kbd className="rounded border border-[var(--color-line)] px-1.5 py-0.5 text-[10px] text-[var(--color-faint)]">
                          {c.shortcut}
                        </kbd>
                      )}
                    </Command.Item>
                  ))}
                </Command.Group>
              ))}
            </Command.List>
          </Command>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
