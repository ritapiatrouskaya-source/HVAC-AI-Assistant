# ❄ HVAC Technical AI Assistant

> AI-powered assistant for HVAC technical documentation, equipment specifications, installation requirements, piping and troubleshooting.

The **HVAC Technical AI Assistant** is a Retrieval-Augmented Generation (RAG) application designed to help engineers and HVAC technicians work with technical manufacturer documentation.

The application combines structured equipment data, semantic document retrieval and an LLM to provide technical answers with references to the original documentation.

---

## 🚀 Features

### Equipment Search

Select an HVAC manufacturer, system family and model to access structured technical information.

The application provides information such as:

- Cooling capacity
- Heating capacity
- Pipe sizes
- Sound levels
- Other technical specifications

### 📄 Technical Documentation

The selected equipment can be linked directly to the corresponding page of the manufacturer's catalog.

This allows users to verify technical information against the original documentation.

### 🤖 AI Technical Assistant

Ask technical questions about the selected HVAC equipment.

The assistant uses Retrieval-Augmented Generation (RAG) to retrieve relevant information from technical documentation before generating an answer.

Example questions:

- What is the maximum interunit piping length?
- What refrigerant does this system use?
- What does error code U4 mean?
- What are the installation requirements?
- What is the operating temperature range?

### 📊 Structured Table Extraction

Technical tables in manufacturer PDFs can be difficult for conventional text-based RAG systems because PDF extraction may lose the original column relationships.

The application therefore uses table geometry and structured parsing to preserve the relationship between:

**Model → Technical Value**

This is especially important for equipment specification tables.

### 🔎 Source References

AI responses include the source document and page information used to generate the answer.

This makes the system easier to verify and more suitable for technical documentation.

---

## 🧠 How It Works

The application follows a Retrieval-Augmented Generation architecture:

```text
Manufacturer Documentation
          │
          ▼
     PDF Processing
          │
          ▼
       Chunking
          │
          ▼
   HuggingFace Embeddings
          │
          ▼
      Chroma Vector DB
          │
          ▼
     Semantic Retrieval
          │
          ├───────────────┐
          │               │
          ▼               ▼
  Selected Model      User Question
       Context             │
          │               │
          └───────┬───────┘
                  ▼
             LLM (Ollama)
                  │
                  ▼
          Technical Answer
                  │
                  ▼
          Source + Page

```

For model-specific questions, the system gives priority to the selected equipment model and its corresponding catalog page before falling back to semantic retrieval.

---

## 📚 Knowledge Base

The current knowledge base is based on Daikin technical documentation:

- General Catalog
- Engineering Data
- Installation Manual
- Service Manual

### Current Scope

The current application focuses on:

**Daikin Single-Split / Single-Zone systems**

Covered topics include:

- Equipment specifications
- Installation requirements
- Refrigerant and piping
- Operating conditions
- Technical parameters
- Error codes
- Troubleshooting information

---

## 🛠 Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application |
| Streamlit | Web interface |
| LangChain | RAG pipeline |
| Chroma | Vector database |
| HuggingFace Embeddings | Semantic embeddings |
| Ollama | Local LLM inference |
| Llama 3.1 | Language model |
| PyMuPDF | PDF processing |
| GitHub | Version control |

### Embedding Model

```text
BAAI/bge-small-en-v1.5
```

### Language Model

```text
Llama 3.1
```

running through:

```text
Ollama
```

---

## 📁 Project Structure

```text
HVAC-AI-Assistant/
│
├── app.py
├── README.md
├── requirements.txt
├── LICENSE
├── .gitignore
│
├── assets/
│   └── back.png
│
├── data/
│   └── indexes/
│       ├── catalog_index.json
│       └── equipment_database.json
│
├── search/
│   └── search_equipment.py
│
└── src/
    ├── chunking.py
    ├── config.py
    ├── embeddings.py
    ├── equipment.py
    ├── llm.py
    ├── loader.py
    ├── rag.py
    ├── retriever.py
    ├── table_parser.py
    └── vector_store.py
```
---

## 💬 Example

After selecting an HVAC model, users can ask questions such as:

```text
What does error U4 mean?
```

The system retrieves the relevant information from the technical documentation and provides an answer together with source references.

---

## 🔐 Data & Security

Manufacturer documentation is not included in this repository.

The repository contains the application source code, assets and structured index data used by the project.

Sensitive information such as API keys, environment files and local databases should never be committed to Git.

The `.gitignore` configuration excludes:

```text
.env
*.env
__pycache__/
data/vector_db/
```

---

## 🎯 Project Goals

The main goal of the project is to demonstrate how Retrieval-Augmented Generation can be applied to technical HVAC documentation.

The project combines:

- Information retrieval
- Natural Language Processing
- Vector databases
- Large Language Models
- PDF document processing
- Structured data extraction
- Technical knowledge retrieval
- Interactive web applications

---

## 🔮 Future Improvements

Possible future extensions include:

- HVAC equipment recommendation based on room parameters
- Installation and troubleshooting workflows
- Error-code diagnostic assistance
- Support for additional manufacturers
- Expanded equipment databases
- Improved document visualization
- Advanced filtering and comparison of equipment models

---

## 🔮 Streamlit-App (Screenshot)

<img width="906" height="535" alt="image" src="https://github.com/user-attachments/assets/6dee5db2-7baf-4443-b25c-6bf9873b37bf" />


## 👩‍💻 Author

**Rita Piatrouskaya**

Data Science / AI

[GitHub](https://github.com/ritapiatrouskaya-source)

---

## 📄 License

This project is licensed under the MIT License.

See the [LICENSE](LICENSE) file for details.
