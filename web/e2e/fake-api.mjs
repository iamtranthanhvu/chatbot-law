// Scripted stand-in for the FastAPI backend, speaking the same SSE contract.
import { createServer } from "node:http";

const PORT = Number(process.env.FAKE_API_PORT ?? 8100);
const DISCLAIMER = "Thông tin chỉ mang tính tham khảo, không thay thế tư vấn pháp lý.";

const SOURCE = {
  n: 1,
  chunk_id: "chunk-188",
  chunk_ids: ["chunk-188"],
  so_hieu: "45/2013/QH13",
  dieu: "188",
  khoan: "1",
  title: "Điều kiện thực hiện các quyền chuyển đổi, chuyển nhượng, cho thuê, tặng cho, thế chấp",
  snippet: "1. Người sử dụng đất được thực hiện các quyền chuyển đổi, chuyển nhượng…",
  score: 0.93,
};

const CHUNK = {
  id: "chunk-188",
  so_hieu: "45/2013/QH13",
  document_name: "Luật Đất đai",
  path: "dieu-188",
  chapter_number: "11",
  chapter_title: "QUYỀN VÀ NGHĨA VỤ CỦA NGƯỜI SỬ DỤNG ĐẤT",
  section_number: "4",
  section_title: "CHUYỂN ĐỔI, CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT",
  dieu: "188",
  article_title: SOURCE.title,
  khoan: [1],
  diem: ["1.a", "1.b", "1.c", "1.d"],
  location: "Chương 11 › Mục 4 › Điều 188",
  text: "1. Người sử dụng đất được thực hiện các quyền chuyển đổi, chuyển nhượng, cho thuê, cho thuê lại, thừa kế, tặng cho, thế chấp quyền sử dụng đất; góp vốn bằng quyền sử dụng đất khi có các điều kiện sau đây:\na) Có Giấy chứng nhận…",
  valid_from: "2014-07-01",
  valid_to: null,
};

const SITUATION = [
  "**Kết luận:** Không được, vì chuyển nhượng cần có Giấy chứng nhận [1].",
  "**Giải thích:** Người sử dụng đất chỉ được chuyển nhượng khi có Giấy chứng nhận [1].",
  "**Thông tin nên bổ sung:**",
  "- Đất có đang tranh chấp không",
  "**Căn cứ pháp lý:**",
  "- Điều 188, khoản 1 [1]",
].join("\n");

const send = (res, name, data) => res.write(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let counter = 0;

async function ask(question, res) {
  const id = `00000000-0000-4000-8000-${String(++counter).padStart(12, "0")}`;
  res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
  if (/thời tiết|bóng đá/i.test(question)) {
    send(res, "meta", { query_id: id, pipeline: "hybrid", intent: "out_of_scope" });
    send(res, "sources", []);
    send(res, "done", done("Hệ thống hiện chỉ hỗ trợ hỏi đáp về pháp luật đất đai. Câu hỏi của bạn nằm ngoài phạm vi này.", []));
    return res.end();
  }
  const situation = /tôi|mình/i.test(question);
  send(res, "meta", { query_id: id, pipeline: "hybrid", intent: situation ? "situation" : "topic_search" });
  await sleep(150);
  send(res, "sources", [SOURCE]);
  const answer = situation ? SITUATION : "Người sử dụng đất được chuyển nhượng khi có Giấy chứng nhận [1].";
  for (const piece of answer.match(/.{1,12}/gs)) {
    send(res, "token", { delta: piece });
    await sleep(30);
  }
  send(res, "done", done(answer, [1], situation ? ["Đất có đang tranh chấp không"] : []));
  res.end();
}

function done(answer, citations, missing = []) {
  return {
    answer,
    citations,
    invalid_citations: [],
    missing_facts: missing,
    usage: {},
    latency_ms: { total: 1 },
    model: "fake",
    disclaimer: DISCLAIMER,
    cached: false,
  };
}

createServer((req, res) => {
  let body = "";
  req.on("data", (chunk) => (body += chunk));
  req.on("end", () => {
    const json = (status, data) => {
      res.writeHead(status, { "content-type": "application/json" });
      res.end(JSON.stringify(data));
    };
    if (req.method === "POST" && req.url === "/api/v1/ask") return void ask(JSON.parse(body).question, res);
    if (req.method === "GET" && req.url === "/api/v1/chunks/chunk-188") return json(200, CHUNK);
    if (req.method === "POST" && /^\/api\/v1\/queries\/[^/]+\/feedback$/.test(req.url)) return json(200, { status: "ok" });
    if (req.url === "/api/v1/healthz") return json(200, { status: "ok" });
    json(404, { error: { code: "NOT_FOUND", message: "Không tìm thấy." } });
  });
}).listen(PORT, "127.0.0.1");
