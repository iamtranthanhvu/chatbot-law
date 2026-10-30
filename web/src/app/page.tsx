import { Chat } from "@/components/Chat";
import { Footer } from "@/components/Footer";

export default function Home() {
  return (
    <>
      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8 sm:py-12">
        <header className="max-w-3xl space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
            Hỏi đáp Luật Đất đai
          </h1>
          <p className="text-sm text-muted-foreground">
            Mô tả tình huống của bạn hoặc tra cứu một Điều luật. Câu trả lời dựa trên Luật Đất đai
            2013 (45/2013/QH13) và luôn kèm căn cứ.
          </p>
        </header>
        <Chat />
      </main>
      <Footer />
    </>
  );
}
