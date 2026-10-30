import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Chat } from "@/components/Chat";
import { ApiError } from "@/lib/api";
import { DONE, SOURCE, controlledAsk } from "./helpers";

const askMock = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ask: (...args: unknown[]) => askMock(...args),
}));

async function askQuestion(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByRole("textbox", { name: /câu hỏi/i }), text);
  await user.click(screen.getByRole("button", { name: /^hỏi$/i }));
}

beforeEach(() => {
  askMock.mockReset();
});

describe("Chat", () => {
  it("shows the answer as it streams and the sources once they arrive", async () => {
    const stream = controlledAsk();
    askMock.mockImplementation(stream.generate);
    render(<Chat />);

    await askQuestion("Bán đất chưa có sổ đỏ được không?");
    expect(askMock).toHaveBeenCalledWith("Bán đất chưa có sổ đỏ được không?", expect.any(AbortSignal));

    await stream.push({ type: "meta", data: { query_id: "q1", pipeline: "hybrid", intent: "topic_search" } });
    expect(screen.queryByRole("list", { name: /căn cứ/i })).not.toBeInTheDocument();

    await stream.push({ type: "sources", data: [SOURCE] });
    const sources = screen.getByRole("list", { name: /căn cứ/i });
    expect(within(sources).getByText(/Điều 188/)).toBeInTheDocument();

    await stream.push({ type: "token", data: { delta: "Không được, " } });
    const region = screen.getByRole("region", { name: /câu trả lời/i });
    expect(region).toHaveTextContent("Không được,");
    expect(region).toHaveAttribute("aria-busy", "true");

    await stream.push({ type: "token", data: { delta: "vì chưa có Giấy chứng nhận [1]." } });
    await stream.push({ type: "done", data: DONE });
    await stream.end();

    expect(region).toHaveTextContent("Không được, vì chưa có Giấy chứng nhận");
    expect(region).toHaveAttribute("aria-busy", "false");
    expect(within(region).getByRole("button", { name: /nguồn 1/i })).toBeInTheDocument();
    expect(screen.getByText(DONE.disclaimer)).toBeInTheDocument();
  });

  it("explains a rate limit with the waiting time", async () => {
    askMock.mockImplementation(async function* () {
      throw new ApiError("RATE_LIMITED", "Bạn đã hỏi quá nhiều", 429, 42);
    });
    render(<Chat />);

    await askQuestion("q");

    expect(await screen.findByRole("alert")).toHaveTextContent(/42 giây/);
  });

  it("shows the busy message sent by the server", async () => {
    const stream = controlledAsk();
    askMock.mockImplementation(stream.generate);
    render(<Chat />);

    await askQuestion("q");
    await stream.push({
      type: "error",
      data: { code: "BUSY", message: "Hệ thống đang bận, vui lòng thử lại sau ít phút." },
    });
    await stream.end();

    expect(screen.getByRole("alert")).toHaveTextContent("Hệ thống đang bận");
  });

  it("shows a network failure", async () => {
    askMock.mockImplementation(async function* () {
      throw new ApiError("NETWORK", "Không kết nối được máy chủ.");
    });
    render(<Chat />);

    await askQuestion("q");

    expect(await screen.findByRole("alert")).toHaveTextContent("Không kết nối được máy chủ");
  });

  it("a suggested question fills the box", async () => {
    render(<Chat />);

    await userEvent.setup().click(screen.getAllByRole("button", { name: /sổ đỏ/i })[0]);

    const box = screen.getByRole<HTMLTextAreaElement>("textbox", { name: /câu hỏi/i });
    expect(box.value).toMatch(/sổ đỏ/i);
    expect(box).toHaveFocus();
  });

  it("does not send an empty question", async () => {
    render(<Chat />);

    expect(screen.getByRole("button", { name: /^hỏi$/i })).toBeDisabled();
  });
});
