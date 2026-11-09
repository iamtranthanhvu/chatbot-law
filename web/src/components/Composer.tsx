"use client";

import { ArrowUp, LoaderCircle, Mic, MicOff, Square, Upload } from "lucide-react";
import { type ChangeEvent, type Ref, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { transcribeAudio } from "@/lib/api";

export const MAX_QUESTION_CHARS = 1000;
const MAX_AUDIO_BYTES = 20 * 1024 * 1024;

export function Composer({
  busy,
  onAsk,
  onStop,
  inputRef,
}: {
  busy: boolean;
  onAsk: (question: string) => void;
  onStop: () => void;
  inputRef?: Ref<HTMLTextAreaElement>;
}) {
  const [question, setQuestion] = useState("");
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const audioFileRef = useRef<HTMLInputElement>(null);
  const trimmed = question.trim();
  const nearLimit = question.length > MAX_QUESTION_CHARS * 0.8;

  function submit() {
    if (!trimmed || busy) return;
    onAsk(trimmed);
    setQuestion("");
  }

  function appendTranscript(transcript: string) {
    setQuestion((current) =>
      `${current}${current.trim() ? " " : ""}${transcript}`.slice(0, MAX_QUESTION_CHARS),
    );
  }

  async function transcribe(audio: Blob) {
    setAudioError(null);
    setTranscribing(true);
    try {
      const transcript = await transcribeAudio(audio);
      if (!transcript.trim()) throw new Error("Không nhận dạng được lời nói trong audio.");
      appendTranscript(transcript);
    } catch (error) {
      setAudioError(error instanceof Error ? error.message : "Không nhận dạng được audio.");
    } finally {
      setTranscribing(false);
    }
  }

  function handleAudioFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file) return;
    setAudioError(null);
    if (file.size > MAX_AUDIO_BYTES) {
      setAudioError("File audio vượt quá giới hạn 20 MB.");
      return;
    }
    const inferredType = audioTypeFromName(file.name);
    const contentType = file.type.startsWith("audio/") ? file.type : inferredType;
    if (!contentType) {
      setAudioError("Hãy chọn file audio như MP3, WAV, M4A, OGG hoặc WebM.");
      return;
    }
    void transcribe(new Blob([file], { type: contentType }));
  }

  async function toggleRecording() {
    setAudioError(null);
    if (recorderRef.current?.state === "recording") {
      recorderRef.current.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setAudioError("Trình duyệt này chưa hỗ trợ ghi âm.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredType = ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      const recorder = preferredType
        ? new MediaRecorder(stream, { mimeType: preferredType })
        : new MediaRecorder(stream);
      const parts: BlobPart[] = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) parts.push(event.data);
      };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        recorderRef.current = null;
        setRecording(false);
        if (parts.length === 0) return;
        const audio = new Blob(parts, { type: recorder.mimeType || "audio/webm" });
        void transcribe(audio);
      };
      recorder.onerror = () => {
        stream.getTracks().forEach((track) => track.stop());
        recorderRef.current = null;
        setRecording(false);
        setAudioError("Không ghi âm được. Hãy kiểm tra quyền dùng microphone.");
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setAudioError("Không mở được microphone. Hãy cho phép trình duyệt sử dụng microphone.");
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="rounded-xl border bg-card shadow-sm transition-colors focus-within:border-primary/50 focus-within:ring-3 focus-within:ring-ring/20"
    >
      <input
        ref={audioFileRef}
        type="file"
        accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg,.opus,.webm,.flac"
        className="sr-only"
        aria-label="Chọn file audio để chuyển thành văn bản"
        onChange={handleAudioFile}
      />
      <label htmlFor="question" className="sr-only">
        Câu hỏi của bạn
      </label>
      <textarea
        id="question"
        ref={inputRef}
        value={question}
        maxLength={MAX_QUESTION_CHARS}
        rows={1}
        placeholder="Hỏi về đất đai, ví dụ: Tách thửa đất ở cần điều kiện gì?"
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
        aria-describedby="question-hint audio-hint"
        className="field-sizing-content block max-h-52 min-h-14 w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-base outline-none placeholder:text-muted-foreground"
      />
      <div className="flex items-center justify-between gap-3 px-3 pb-2.5">
        <p id="question-hint" className="text-xs text-muted-foreground">
          <span className="hidden sm:inline">Enter để gửi · Shift + Enter xuống dòng</span>
          {nearLimit && (
            <span>
              {" "}
              · {question.length}/{MAX_QUESTION_CHARS.toLocaleString("vi-VN")} ký tự
            </span>
          )}
        </p>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="rounded-full"
            aria-label="Tải file audio"
            title="Tải file audio để chuyển thành văn bản"
            disabled={busy || recording || transcribing}
            onClick={() => audioFileRef.current?.click()}
          >
            {transcribing ? (
              <LoaderCircle aria-hidden className="animate-spin" />
            ) : (
              <Upload aria-hidden />
            )}
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="rounded-full"
            aria-label={recording ? "Dừng ghi âm" : "Nhập câu hỏi bằng giọng nói"}
            title={recording ? "Dừng ghi âm" : "Ghi câu hỏi bằng giọng nói"}
            aria-pressed={recording}
            disabled={busy || transcribing}
            onClick={() => void toggleRecording()}
          >
            {transcribing ? (
              <LoaderCircle aria-hidden className="animate-spin" />
            ) : recording ? (
              <MicOff aria-hidden />
            ) : (
              <Mic aria-hidden />
            )}
          </Button>
          {busy ? (
            <Button
              type="button"
              size="icon"
              variant="outline"
              className="rounded-full"
              aria-label="Dừng"
              title="Dừng trả lời"
              onClick={onStop}
            >
              <Square aria-hidden className="size-3 fill-current" />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon"
              className="rounded-full"
              aria-label="Hỏi"
              title="Gửi câu hỏi"
              disabled={!trimmed || recording || transcribing}
            >
              <ArrowUp aria-hidden />
            </Button>
          )}
        </div>
      </div>
      {audioError && (
        <p role="alert" className="px-4 pb-2 text-xs text-destructive">
          {audioError}
        </p>
      )}
      <p id="audio-hint" className="px-4 pb-2 text-[11px] text-muted-foreground">
        Ghi âm hoặc tải file audio (tối đa 20 MB); bản chữ sẽ hiện ở đây để bạn sửa trước khi gửi.
      </p>
    </form>
  );
}

function audioTypeFromName(name: string): string | null {
  const extension = name.split(".").at(-1)?.toLowerCase();
  const types: Record<string, string> = {
    aac: "audio/aac",
    flac: "audio/flac",
    m4a: "audio/mp4",
    mp3: "audio/mpeg",
    ogg: "audio/ogg",
    opus: "audio/ogg",
    wav: "audio/wav",
    webm: "audio/webm",
  };
  return extension ? (types[extension] ?? null) : null;
}
