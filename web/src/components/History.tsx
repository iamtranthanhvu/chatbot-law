"use client";

import { useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import {
  type HistoryEntry,
  clearHistory,
  getHistory,
  getServerHistory,
  subscribeHistory,
} from "@/lib/history";

const TIME = new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" });

export function History({
  activeId,
  onOpen,
}: {
  activeId: string | null;
  onOpen: (entry: HistoryEntry) => void;
}) {
  const entries = useSyncExternalStore(subscribeHistory, getHistory, getServerHistory);

  return (
    <nav aria-label="Lịch sử câu hỏi" className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Lịch sử câu hỏi</h2>
        {entries.length > 0 && (
          <Button type="button" variant="ghost" size="sm" onClick={clearHistory}>
            Xóa lịch sử
          </Button>
        )}
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">Chưa có câu hỏi nào.</p>
      ) : (
        <ul className="space-y-1">
          {entries.map((entry) => (
            <li key={entry.id}>
              <button
                type="button"
                onClick={() => onOpen(entry)}
                aria-current={entry.id === activeId ? "true" : undefined}
                className="w-full rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none aria-[current=true]:bg-muted"
              >
                <span className="line-clamp-2">{entry.question}</span>
                <span className="block text-xs text-muted-foreground">
                  {TIME.format(new Date(entry.askedAt))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted-foreground">Chỉ lưu trên trình duyệt này.</p>
    </nav>
  );
}
