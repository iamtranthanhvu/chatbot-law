"use client";

import { Trash2 } from "lucide-react";
import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import {
  type HistoryEntry,
  clearHistory,
  getHistory,
  getServerHistory,
  subscribeHistory,
} from "@/lib/history";

function groupByDay(entries: HistoryEntry[]): [string, HistoryEntry[]][] {
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const weekAgo = startOfToday.getTime() - 6 * 86_400_000;
  const groups = new Map<string, HistoryEntry[]>();
  for (const entry of entries) {
    const time = new Date(entry.askedAt).getTime();
    const label =
      time >= startOfToday.getTime() ? "Hôm nay" : time >= weekAgo ? "7 ngày qua" : "Cũ hơn";
    groups.set(label, [...(groups.get(label) ?? []), entry]);
  }
  return [...groups];
}

export function History({
  activeId,
  onOpen,
}: {
  activeId: string | null;
  onOpen: (entry: HistoryEntry) => void;
}) {
  const entries = useSyncExternalStore(subscribeHistory, getHistory, getServerHistory);

  return (
    <nav aria-label="Lịch sử câu hỏi" className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-2 pb-1">
        <h2 className="text-xs font-medium text-muted-foreground">Lịch sử câu hỏi</h2>
        {entries.length > 0 && (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-label="Xóa lịch sử"
            title="Xóa lịch sử"
            onClick={clearHistory}
          >
            <Trash2 aria-hidden />
          </Button>
        )}
      </div>
      {entries.length === 0 ? (
        <p className="px-2 py-1 text-sm text-muted-foreground">Chưa có câu hỏi nào.</p>
      ) : (
        <div className="-mx-1 min-h-0 flex-1 space-y-3 overflow-y-auto px-1">
          {groupByDay(entries).map(([label, group]) => (
            <div key={label}>
              <h3 className="px-2 pt-1 pb-0.5 text-[11px] font-medium text-muted-foreground">
                {label}
              </h3>
              <ul>
                {group.map((entry) => (
                  <li key={entry.id}>
                    <button
                      type="button"
                      onClick={() => onOpen(entry)}
                      aria-current={entry.id === activeId ? "true" : undefined}
                      title={entry.question}
                      className="w-full truncate rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none aria-[current=true]:bg-sidebar-accent aria-[current=true]:font-medium"
                    >
                      {entry.question}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </nav>
  );
}
