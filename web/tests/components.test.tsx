import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Chat } from "@/components/Chat";
import { splitSituation } from "@/components/SituationAnswer";
import { ApiError } from "@/lib/api";
import type { ChunkDetail, DonePayload, Intent } from "@/lib/types";

import { DONE, SOURCE, controlledAsk } from "./helpers";

const askMock = vi.fn();
const getChunkMock = vi.fn();
const sendFeedbackMock = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ask: (...args: unknown[]) => askMock(...args),
  getChunk: (...args: unknown[]) => getChunkMock(...args),
  sendFeedback: (...args: unknown[]) => sendFeedbackMock(...args),
}));

const CHUNK: ChunkDetail = {
  id: "c1",
  so_hieu: "45/2013/QH13",
  document_name: "Luật Đất đai",
  path: "dieu-188",
  chapter_number: "11",
  chapter_title: "THỦ TỤC HÀNH CHÍNH VỀ ĐẤT ĐAI",
  section_number: null,
  section_title: null,
  dieu: "188",
  article_title: "Điều kiện thực hiện các quyền chuyển đổi, chuyển nhượng",
  khoan: [1],
  diem: [],
  location: "Chương 11. THỦ TỤC HÀNH CHÍNH VỀ ĐẤT ĐAI › Điều 188. Điều kiện thực hiện các quyền",
  text: "1. Người sử dụng đất được thực hiện các quyền chuyển nhượng khi có Giấy chứng nhận.",
  valid_from: "2014-07-01",
  valid_to: null,
};

const SITUATION_ANSWER = [
  "**Kết luận:** Không được bán khi chưa có Giấy chứng nhận [1].",
  "**Giải thích:** Luật yêu cầu phải có Giấy chứng nhận [1].",
  "**Thông tin nên bổ sung:**",
  "- Đất có đang tranh chấp không",
  "**Căn cứ pháp lý:**",
  "- Điều 188, khoản 1 [1]",
].join("\n");

async function answered(intent: Intent, done: Partial<DonePayload> = {}) {
  const stream = controlledAsk();
  askMock.mockImplementation(stream.generate);
  render(<Chat />);
  const user = userEvent.setup();
  await user.type(screen.getByRole("textbox", { name: /câu hỏi/i }), "q");
  await user.click(screen.getByRole("button", { name: /^hỏi$/i }));
  await stream.push(
    { type: "meta", data: { query_id: "q1", pipeline: "hybrid", intent } },
    { type: "sources", data: [SOURCE] },
    { type: "done", data: { ...DONE, ...done } },
  );
  await stream.end();
  return user;
}

beforeEach(() => {
  askMock.mockReset();
  getChunkMock.mockReset().mockResolvedValue(CHUNK);
  sendFeedbackMock.mockReset().mockResolvedValue(undefined);
});

describe("citation panel", () => {
  it("opens the cited article's verbatim text and closes with Escape", async () => {
    const user = await answered("topic_search");

    await user.click(screen.getByRole("button", { name: /xem nguồn 1/i }));

    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByRole("heading", { name: /Điều 188/ })).toBeInTheDocument();
    expect(within(panel).getByText(/Chương 11/)).toBeInTheDocument();
    expect(await within(panel).findByText(/có Giấy chứng nhận\./)).toBeInTheDocument();
    expect(getChunkMock).toHaveBeenCalledWith("c1", expect.any(AbortSignal));

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("opens from the sources list as well", async () => {
    const user = await answered("topic_search");

    await user.click(within(screen.getByRole("list", { name: /căn cứ/i })).getByRole("button"));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("says so when the text cannot be loaded", async () => {
    getChunkMock.mockRejectedValue(new ApiError("NETWORK", "Không kết nối được máy chủ."));
    const user = await answered("topic_search");

    await user.click(screen.getByRole("button", { name: /xem nguồn 1/i }));

    expect(await within(await screen.findByRole("dialog")).findByRole("alert")).toHaveTextContent(
      "Không kết nối được máy chủ",
    );
  });
});

describe("situation layout", () => {
  it("shows the conclusion and the facts to add as separate blocks", async () => {
    await answered("situation", {
      answer: SITUATION_ANSWER,
      missing_facts: ["Đất có đang tranh chấp không", "Đất sử dụng từ năm nào"],
    });

    const conclusion = screen.getByRole("region", { name: "Kết luận" });
    expect(conclusion).toHaveTextContent("Không được bán khi chưa có Giấy chứng nhận");
    const facts = screen.getByRole("region", { name: "Thông tin nên bổ sung" });
    expect(within(facts).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Đất có đang tranh chấp không",
      "Đất sử dụng từ năm nào",
    ]);
    const answer = screen.getByRole("region", { name: /câu trả lời/i });
    expect(answer).toHaveTextContent("Luật yêu cầu phải có Giấy chứng nhận");
    expect(within(answer).queryAllByText(/Thông tin nên bổ sung/)).toHaveLength(1);
  });

  it("a lookup answer has no extra blocks", async () => {
    await answered("lookup", { answer: "Điều 188 quy định: “...” [1]." });

    expect(screen.queryByRole("region", { name: "Kết luận" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Thông tin nên bổ sung" })).not.toBeInTheDocument();
  });

  it("splits a situation answer into conclusion, facts and the rest", () => {
    expect(splitSituation(SITUATION_ANSWER)).toEqual({
      conclusion: "Không được bán khi chưa có Giấy chứng nhận [1].",
      facts: ["Đất có đang tranh chấp không"],
      body: "**Giải thích:** Luật yêu cầu phải có Giấy chứng nhận [1].\n**Căn cứ pháp lý:**\n- Điều 188, khoản 1 [1]",
    });
    expect(splitSituation("Trả lời không theo khung [1].")).toBeNull();
  });
});

describe("feedback", () => {
  it("thanks the user after a thumbs up", async () => {
    const user = await answered("topic_search");

    await user.click(screen.getByRole("button", { name: /hữu ích/i }));

    expect(sendFeedbackMock).toHaveBeenCalledWith("q1", "up", undefined);
    expect(await screen.findByRole("status")).toHaveTextContent(/cảm ơn/i);
  });

  it("a thumbs down can carry a note", async () => {
    const user = await answered("topic_search");

    await user.click(screen.getByRole("button", { name: /chưa tốt/i }));
    await user.type(screen.getByRole("textbox", { name: /góp ý/i }), "Thiếu Điều 191");
    await user.click(screen.getByRole("button", { name: /gửi góp ý/i }));

    expect(sendFeedbackMock).toHaveBeenCalledWith("q1", "down", "Thiếu Điều 191");
    expect(await screen.findByRole("status")).toHaveTextContent(/cảm ơn/i);
  });

  it("reports a failed send and lets the user retry", async () => {
    sendFeedbackMock.mockRejectedValueOnce(new ApiError("NETWORK", "Không kết nối được máy chủ."));
    const user = await answered("topic_search");

    await user.click(screen.getByRole("button", { name: /hữu ích/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/chưa gửi được/i);
    await user.click(screen.getByRole("button", { name: /hữu ích/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/cảm ơn/i);
  });
});
