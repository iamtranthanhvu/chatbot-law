# Thử nghiệm fine-tune retrieval tiếng Việt pháp lý

## Kết luận trước khi có thí nghiệm

Chưa có bằng chứng cho thấy fine-tune BGE-M3 hoặc BGE Reranker trên repo này sẽ tốt hơn model gốc.
`eval/datasets/seed.jsonl` hiện có 29 câu hỏi gắn căn cứ Luật Đất đai 2013; bộ này phù hợp để kiểm
tra retrieval, không đủ làm cả train và test mà vẫn kết luận đáng tin cậy. Không đưa câu hỏi test,
các cách diễn đạt sinh từ cùng câu test, hay điều khoản test vào dữ liệu huấn luyện.

## Chọn model để thử

- **Embedding BGE-M3**: phù hợp khi lỗi nằm ở bước tìm ứng viên ban đầu, nhất là câu hỏi đời thường
  như “sổ đỏ”, cách diễn đạt địa phương, hoặc câu hỏi nhiều ý. Fine-tune cần cặp query–điều khoản đúng
  và hard negatives. Model-server hiện lấy vector dense từ `BGEM3FlagModel`; checkpoint thay thế cần
  giữ tương thích với loader này và vector dimension 1024. BM25 là lexical index riêng, không dùng
  sparse head của BGE-M3.
- **Reranker**: phù hợp khi căn cứ đúng đã nằm trong top candidates nhưng bị xếp dưới đoạn ít liên
  quan hơn. Dữ liệu cần query cùng positive passage và các hard negative được chuyên gia rà soát.
  Bắt đầu với reranker thường dễ đánh giá hơn vì không cần tạo lại embedding toàn corpus.

FlagEmbedding cung cấp quy trình fine-tune embedder với `query`, `pos`, `neg` và quy trình fine-tune
reranker với hard negatives. BGE-M3 được huấn luyện đa ngôn ngữ và nhiều chức năng; fine-tune riêng
trên một tập nhỏ có thể làm giảm khả năng tổng quát hoặc làm hỏng một đầu ra nếu không kiểm tra đủ.
Tham khảo [hướng dẫn fine-tune embedder](https://github.com/FlagOpen/FlagEmbedding/tree/master/examples/finetune/embedder),
[hướng dẫn fine-tune reranker](https://github.com/FlagOpen/FlagEmbedding/tree/master/examples/finetune/reranker)
và [bài báo BGE-M3](https://arxiv.org/abs/2402.03216).

## Dữ liệu cần chuẩn bị

Mỗi ví dụ phải được người hiểu luật xác nhận:

1. Câu hỏi độc lập, giữ cả cách diễn đạt đời thường và thuật ngữ pháp lý.
2. Điều/Khoản/Điểm đúng theo phiên bản luật và ngày hiệu lực cụ thể.
3. Một hoặc nhiều passage đúng; không coi mọi đoạn khác là negative nếu chúng cũng có thể là căn cứ.
4. Hard negatives lấy từ kết quả BM25/hybrid/reranker hiện tại, ưu tiên đoạn cùng chủ đề hoặc cùng
   tên Điều ở văn bản khác.
5. Nhãn phân biệt bản luật, ngày tham chiếu, loại câu hỏi và nhóm người dùng.

Chia train/dev/test theo chủ đề pháp lý hoặc nhóm điều khoản, không chia ngẫu nhiên các câu gần giống
nhau. Giữ một bộ test do người duyệt khóa lại trước khi chạy tuning. Nên có hàng trăm đến hàng nghìn
cặp đã kiểm duyệt trước khi kỳ vọng fine-tune ổn định; con số này là mục tiêu thực nghiệm, không phải
ngưỡng bảo đảm kết quả.

## So sánh công bằng

1. Lưu kết quả model gốc trên cùng corpus và cùng câu hỏi.
2. Thay một model tại một thời điểm qua `.env`:

   ```dotenv
   MS_EMBED_MODEL=/đường/dẫn/tới/checkpoint-embedding
   # hoặc
   MS_RERANK_MODEL=/đường/dẫn/tới/checkpoint-reranker
   ```

3. Khởi động lại `model-server`. Khi đổi embedding, chạy `make reindex` để tạo lại vector cho toàn bộ
   corpus. Chỉ đổi reranker thì không cần reindex.
4. Chạy cùng lệnh eval, cùng ngày tham chiếu, cùng corpus và cấu hình retrieval. Với bộ seed hiện
   tại, lệnh baseline lịch sử là `make eval MODE=retrieval ARGS="--on 2024-07-31"`. So sánh Recall@5/10,
   MRR@10, nDCG@10, citation precision, citation recall, độ trễ và kết quả theo persona/intent.
5. Chỉ chọn checkpoint nếu cải thiện trên test chưa dùng khi huấn luyện và không làm giảm nhóm câu hỏi
   quan trọng. Giữ checkpoint gốc để rollback.

Với bộ 2013 hiện tại, đánh giá lịch sử trước 01/08/2024 bằng `--on 2024-07-31`. Cần tạo một bộ eval
riêng có nhãn theo Luật 2024 trước khi kết luận model nào tốt hơn cho câu hỏi hiện hành.
