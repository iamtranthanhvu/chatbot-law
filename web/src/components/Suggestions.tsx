"use client";

const GROUPS = [
  {
    title: "Tình huống thường gặp",
    questions: [
      "Tôi muốn bán đất nhưng chưa có sổ đỏ thì có được không?",
      "Xây nhà trên đất trồng lúa có bị xử lý không?",
      "Nhà nước thu hồi đất của tôi thì có được bồi thường không?",
    ],
  },
  {
    title: "Tra cứu quy định",
    questions: [
      "Điều 100 Luật Đất đai 2013 quy định gì?",
      "Điều kiện thực hiện quyền chuyển nhượng quyền sử dụng đất",
      "Thời hạn sử dụng đất nông nghiệp của hộ gia đình, cá nhân",
    ],
  },
];

export function Suggestions({ onPick }: { onPick: (question: string) => void }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {GROUPS.map((group) => (
        <section key={group.title} aria-label={group.title} className="space-y-2">
          <h2 className="text-sm font-semibold text-muted-foreground">{group.title}</h2>
          <ul className="space-y-2">
            {group.questions.map((question) => (
              <li key={question}>
                <button
                  type="button"
                  onClick={() => onPick(question)}
                  className="w-full rounded-lg border bg-card px-3 py-2 text-left text-sm transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {question}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
