"use client";

import { Check, Copy, Volume2, VolumeX } from "lucide-react";
import { useState } from "react";

import { FeedbackButtons, FeedbackDetails, useFeedback } from "@/components/Feedback";
import { Button } from "@/components/ui/button";

export function MessageActions({ queryId, answer }: { queryId: string; answer: string }) {
  const feedback = useFeedback(queryId);
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard blocked: nothing to do, the text stays selectable
    }
  }

  function toggleSpeech() {
    if (!("speechSynthesis" in window)) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(answer);
    utterance.lang = "vi-VN";
    const vietnameseVoice = window.speechSynthesis
      .getVoices()
      .find((voice) => voice.lang.toLowerCase().startsWith("vi"));
    if (vietnameseVoice) utterance.voice = vietnameseVoice;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }

  return (
    <div>
      <div className="-ml-2 flex items-center gap-0.5">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={copied ? "Đã sao chép" : "Sao chép câu trả lời"}
          title="Sao chép"
          onClick={() => void copy()}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={speaking ? "Dừng đọc câu trả lời" : "Đọc câu trả lời thành tiếng"}
          aria-pressed={speaking}
          title={speaking ? "Dừng đọc" : "Đọc câu trả lời"}
          onClick={toggleSpeech}
        >
          {speaking ? <VolumeX aria-hidden /> : <Volume2 aria-hidden />}
        </Button>
        <FeedbackButtons feedback={feedback} />
      </div>
      <FeedbackDetails feedback={feedback} queryId={queryId} />
    </div>
  );
}
