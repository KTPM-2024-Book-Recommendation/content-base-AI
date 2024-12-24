from flask import Flask, jsonify, request
import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor
from flask_cors import CORS, cross_origin
import os


app = Flask(__name__)
# Apply Flask CORS
CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"

# Thông tin kết nối đến cơ sở dữ liệu
DB_HOST = os.environ.get("DB_HOST", "default_host")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_USER = os.environ.get("DB_USER", "default_user")
DB_PASS = os.environ.get("DB_PASS", "default_password")
DB_NAME = os.environ.get("DB_NAME", "default_database")

# Load ma trận tương đồng từ file .npy
cos_sim = np.load(
    "./top_similar_books.npy",
    allow_pickle=True,
)


# Hàm kết nối đến cơ sở dữ liệu và thực hiện truy vấn
def query_db(query, params=None):
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, dbname=DB_NAME
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(query, params)
    if query.strip().lower().startswith("select"):
        results = cursor.fetchall()
    else:
        conn.commit()  # Commit the transaction for non-select queries
        results = None
    cursor.close()
    conn.close()
    return results


# Content-based recommendation
def get_recommended_book_ids(book_id, source_id):
    # find the index of the book
    book_index = np.where(
        (cos_sim[:, 0, 0] == book_id) & (cos_sim[:, 0, 1] == source_id)
    )
    if len(book_index[0]) == 0:
        return []
    # get the top 10 similar books
    recommended_books = cos_sim[book_index, 1:11, 0:2][0][0]
    return list(recommended_books)


# API để trả về danh sách sách dựa trên danh sách id
@app.route("/content-based-recommend/<string:book_source>", methods=["GET"])
@cross_origin(origin="*")  # Fix to current web domain
def get_books(book_source):
    if not book_source:
        return jsonify({"error": "No book ID provided"}), 400
    try:
        book_id, source_id = book_source.split("-")
    except ValueError:
        return jsonify({"error": "Invalid book ID format"}), 400

    # recommend_books = [[book1_id, source1_id], [book2_id, source2_id], ...]
    recommend_books = get_recommended_book_ids(book_id, int(source_id))
    if not recommend_books:
        return jsonify({"data": []})

    # Tạo danh sách các giá trị (book_id, source_id) để sử dụng trong câu lệnh SQL
    recommend_books_str = ", ".join([f"('{b[0]}', {b[1]})" for b in recommend_books])

    # Tạo mệnh đề ORDER BY theo thứ tự của recommend_books
    order_by_case = "CASE"
    for index, b in enumerate(recommend_books):
        order_by_case += f" WHEN b.id = '{b[0]}' AND b.source_id = {b[1]} THEN {index}"
    order_by_case += " END"

    # Truy vấn thông tin sách và tác giả từ cơ sở dữ liệu
    books_query = (
        """
        SELECT
            b.id,
            b.title,
            b.book_cover AS "bookCover",
            b.language,
            b.image_url AS "imageUrl",
            b.release_date AS "releaseDate",
            b.price,
            b.average_rating AS "averageRating",
            b.number_of_ratings AS "numberOfRatings",
            b.source_id,
            json_agg(
                json_build_object(
                    'author', json_build_object(
                        'id', a.id,
                        'name', a.name,
                        'avatar', a.avatar
                    )
                )
            ) AS authors
        FROM book b
        LEFT JOIN author_to_book atb ON b.id = atb.book_id
        LEFT JOIN author a ON atb.author_id = a.id
        WHERE (b.id, b.source_id) IN ("""
        + recommend_books_str
        + ")GROUP BY b.id  ORDER BY "
        + order_by_case
    )
    books = query_db(books_query)

    # Truy vấn thông tin nguồn từ cơ sở dữ liệu
    source_ids = [book["source_id"] for book in books]
    sources_query = """
        SELECT id, name
        FROM source
        WHERE id = ANY(%s)
    """
    sources = {
        source["id"]: source for source in query_db(sources_query, (source_ids,))
    }

    # Kết hợp thông tin nguồn và interactions vào dữ liệu sách
    for book in books:
        book["source"] = sources.get(
            book["source_id"], {"id": book["source_id"], "name": "Unknown"}
        )
        book["interactions"] = []

    token = request.headers.get("Authorization")
    if token:
        count_query = """
            SELECT mr.count
            FROM model_request mr
            WHERE mr.model_type = 'CONTENT_BASED'
        """
        current_count = query_db(count_query)[0].get("count")
        update_query = """
            UPDATE model_request
            SET count = %s
            WHERE model_type = 'CONTENT_BASED'
        """
        query_db(update_query, (current_count + 1,))

    return jsonify({"data": books})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
