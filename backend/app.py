from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from langchain_openai import OpenAIEmbeddings
# from langchain_community.llms import OpenAI
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader
import os
import tempfile
import faiss
import dotenv
from openai import OpenAI

dotenv.load_dotenv()

# Flask app setup
app = Flask(__name__)
CORS(app)

# OpenAI API key setup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OpenAI API key not found in environment variables.")

# Initialize embeddings and LLM
embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
client = OpenAI()

# Initialize vector_db as None initially
vector_db = None


@app.route('/upload-file', methods=['POST'])
def upload_file():
    global vector_db

    # Check if a file is part of the request
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Load the PDF into a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        file.save(temp_file.name)
        loader = PyPDFLoader(temp_file.name)
        documents = loader.load()

    # Create a new FAISS index or add to the existing one
    if vector_db is None:
        vector_db = FAISS.from_documents(documents, embeddings)  # Removed the index argument
    else:
        vector_db.add_documents(documents)

    return jsonify({"message": "File successfully processed and added to the vector database"}), 200



@app.route('/api/chat', methods=['POST'])
def chat():
    global vector_db

    data = request.json
    if not data or 'query' not in data:
        return jsonify({"error": "Missing 'query' in request body"}), 400

    query = data['query']
    try:
        message_history = data['message_history']
    except KeyError:
        message_history = []

    if vector_db is None:
        return jsonify({"error": "Vector database is empty. Please upload files first."}), 400

    # Search the vector database for relevant context
    results = vector_db.similarity_search(query, k=3)
    context = " ".join([doc.page_content for doc in results])

    print(context)

    def stream_response():
        try:
            messages = [
                {"role": "system", "content": f"Use the following context for answering: {context}"}
            ] + message_history + [
                {"role": "user", "content": query}
            ]

            stream = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                stream=True
            )

            for chunk in stream:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Error: {str(e)}"

    return Response(stream_response(), content_type="text/event-stream")


if __name__ == '__main__':
    app.run(debug=True, port=8000)
