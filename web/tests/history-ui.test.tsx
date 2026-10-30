import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Chat } from "@/components/Chat";
import { clearHistory } from "@/lib/history";

import { DONE, SOURCE, controlledAsk } from "./helpers";

const askMock = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ask: (...args: unknown[]) => askMock(...args),
}));

async function ask(question: string) {
  const stream = controlledAsk();
  askMock.mockImplementationOnce(stream.generate);
  const user = userEvent.setup();
  const box = screen.getByRole("textbox", { name: /câu hỏi/i });
  await user.clear(box);
  await user.type(box, question);
  await user.click(screen.getByRole("button", { name: /^hỏi$/i }));
  await stream.push(
    { type: "meta", data: { query_id: `id-${question}`, pipeline: "hybrid", intent: "lookup" } },
    { type: "sources", data: [SOURCE] },
    { type: "done", data: { ...DONE, answer: `Trả lời cho ${question} [1].` } },
  );
  await stream.end();
  return user;
}

beforeEach(() => {
  askMock.mockReset();
  localStorage.clear();
  clearHistory();
});

describe("history sidebar", () => {
  it("lists answered questions and reopens one without asking again", async () => {
    render(<Chat />);
    await ask("Điều 100 quy định gì");
    const user = await ask("Điều 188 quy định gì");

    const history = screen.getByRole("navigation", { name: /lịch sử/i });
    const items = within(history).getAllByRole("button", { name: /quy định gì/ });
    expect(items.map((b) => b.textContent)).toEqual([
      expect.stringContaining("Điều 188"),
      expect.stringContaining("Điều 100"),
    ]);

    await user.click(items[1]);

    expect(askMock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("region", { name: /câu trả lời/i })).toHaveTextContent(
      "Trả lời cho Điều 100 quy định gì",
    );
  });

  it("is restored from storage on a new page load", async () => {
    const first = render(<Chat />);
    await ask("Điều 100 quy định gì");
    first.unmount();

    render(<Chat />);

    expect(
      within(screen.getByRole("navigation", { name: /lịch sử/i })).getByRole("button", {
        name: /Điều 100/,
      }),
    ).toBeInTheDocument();
  });

  it("can be cleared", async () => {
    render(<Chat />);
    const user = await ask("Điều 100 quy định gì");

    await user.click(screen.getByRole("button", { name: /xóa lịch sử/i }));

    expect(screen.getByRole("navigation", { name: /lịch sử/i })).toHaveTextContent(
      /chưa có câu hỏi/i,
    );
  });
});
