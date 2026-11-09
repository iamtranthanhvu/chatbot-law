"use client";

import { Scale, SquarePen } from "lucide-react";

import { History } from "@/components/History";
import { Button } from "@/components/ui/button";
import type { HistoryEntry } from "@/lib/history";

export function Brand() {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight">
      <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <Scale aria-hidden className="size-4" />
      </span>
      Hỏi đáp Đất đai
    </span>
  );
}

export function AboutData() {
  return (
    <div className="space-y-2 text-[11px] leading-relaxed text-muted-foreground">
      <p>
        <span className="font-medium text-foreground">Kho dữ liệu:</span> Luật Đất đai số
        31/2024/QH15, Luật sửa đổi số 43/2024/QH15, Nghị quyết 254/2025/QH15 và Luật 45/2013/QH13
        để tra cứu lịch sử. Chưa đầy đủ nghị định, thông tư và văn bản địa phương.
      </p>
      <p>
        <span className="font-medium text-foreground">Miễn trừ:</span> Thông tin chỉ mang tính
        tham khảo, không thay thế tư vấn pháp lý.
      </p>
      <p>
        <span className="font-medium text-foreground">Quyền riêng tư:</span> Câu hỏi được lưu ẩn
        danh, không lưu địa chỉ IP. Lịch sử chỉ lưu trên trình duyệt này.
      </p>
    </div>
  );
}

export function Sidebar({
  activeId,
  onNew,
  onOpen,
}: {
  activeId: string | null;
  onNew: () => void;
  onOpen: (entry: HistoryEntry) => void;
}) {
  return (
    <div className="flex h-full flex-col gap-4 p-3">
      <div className="px-1 pt-1">
        <Brand />
      </div>
      <Button type="button" variant="outline" className="justify-start gap-2" onClick={onNew}>
        <SquarePen aria-hidden />
        Câu hỏi mới
      </Button>
      <History activeId={activeId} onOpen={onOpen} />
      <div className="border-t px-1 pt-3">
        <AboutData />
      </div>
    </div>
  );
}
