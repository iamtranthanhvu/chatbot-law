"use client";

import { ClipboardList, FileText, Hammer, House, Landmark, Sprout } from "lucide-react";

const SUGGESTIONS = [
  { icon: House, question: "Tôi muốn bán đất nhưng chưa có sổ đỏ thì có được không?" },
  { icon: Hammer, question: "Xây nhà trên đất trồng lúa có bị xử lý không?" },
  { icon: Landmark, question: "Nhà nước thu hồi đất của tôi thì có được bồi thường không?" },
  { icon: FileText, question: "Điều 100 Luật Đất đai 2013 quy định gì?" },
  { icon: ClipboardList, question: "Điều kiện thực hiện quyền chuyển nhượng quyền sử dụng đất" },
  { icon: Sprout, question: "Thời hạn sử dụng đất nông nghiệp của hộ gia đình, cá nhân" },
];

export function Suggestions({ onPick }: { onPick: (question: string) => void }) {
  return (
    <ul aria-label="Câu hỏi gợi ý" className="grid gap-2 sm:grid-cols-2">
      {SUGGESTIONS.map(({ icon: Icon, question }) => (
        <li key={question}>
          <button
            type="button"
            onClick={() => onPick(question)}
            className="flex h-full w-full items-start gap-2.5 rounded-lg border bg-card px-3 py-2.5 text-left text-sm transition-colors hover:border-primary/40 hover:bg-accent/60 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            <Icon aria-hidden className="mt-0.5 size-4 shrink-0 text-primary" />
            <span>{question}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
